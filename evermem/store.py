"""SQLite-backed claim store with temporal validity windows.

Four memory layers, modeled on biological memory systems:
- semantic memory  -> `claims` table (support, trust, last_seen),
- conflict memory  -> active claims sharing (subject, predicate) with different values,
- episodic memory  -> `episodes` table,
- working memory   -> `turns` table,
plus temporal validity windows: an exclusive claim supersedes the previous
value instead of overwriting it, so history ("lived in Minsk, then moved to
Warsaw") is never lost.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import time
from pathlib import Path

from .embeddings import cosine, embed, split_chunks
from .events import MemoryEvent
from .types import Claim, ClaimDraft, ConflictHint, Episode, EpisodeTouch, Turn

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    value TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'fact',
    exclusive INTEGER NOT NULL DEFAULT 0,
    support INTEGER NOT NULL DEFAULT 1,
    trust REAL NOT NULL DEFAULT 0.6,
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    valid_from REAL NOT NULL,
    invalid_from REAL,
    superseded_by INTEGER,
    source TEXT NOT NULL DEFAULT 'user',
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_claims_lookup ON claims(user_id, subject, predicate);
CREATE INDEX IF NOT EXISTS idx_claims_active ON claims(user_id, invalid_from);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at REAL NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);

CREATE TABLE IF NOT EXISTS turn_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_user ON turn_chunks(user_id);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    first_at REAL NOT NULL,
    last_at REAL NOT NULL,
    turns INTEGER NOT NULL DEFAULT 1,
    topic TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id, id);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    turn_id INTEGER,
    role TEXT NOT NULL,
    label TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'event',
    happened_at REAL NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_events_user ON memory_events(user_id, happened_at);
CREATE INDEX IF NOT EXISTS idx_events_session ON memory_events(session_id);
"""

TRUST_REINFORCE_TARGET = 0.95
TRUST_REINFORCE_ETA = 0.25
TRUST_CONTRADICTION_PENALTY = 0.10
EPISODE_GAP_SECONDS = 1800.0
SCHEMA_VERSION = 3


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _unpack(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


class ClaimStore:
    def __init__(self, path: str | Path = ":memory:", *, embed_fn=None) -> None:
        self.path = str(path)
        self._embed = embed_fn or embed
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        version = self.load_meta("schema_version")
        if not isinstance(version, int):
            version = 1
        if version < 2:
            for statement in (
                "ALTER TABLE claims ADD COLUMN source_turn_id INTEGER",
                "ALTER TABLE claims ADD COLUMN source_session TEXT",
            ):
                try:
                    self._conn.execute(statement)
                except sqlite3.OperationalError:
                    pass
            self.save_meta("schema_version", 2)
            version = 2
        if version < 3:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    turn_id INTEGER,
                    role TEXT NOT NULL,
                    label TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'event',
                    happened_at REAL NOT NULL,
                    embedding BLOB
                );
                CREATE INDEX IF NOT EXISTS idx_events_user ON memory_events(user_id, happened_at);
                CREATE INDEX IF NOT EXISTS idx_events_session ON memory_events(session_id);
                """
            )
            self.save_meta("schema_version", 3)

    # ----------------------------------------------------------- claims

    def upsert_claim(
        self,
        user_id: str,
        draft: ClaimDraft,
        *,
        source: str = "user",
        source_turn_id: int | None = None,
        source_session: str | None = None,
        now: float | None = None,
    ) -> tuple[Claim, str]:
        """Insert or reinforce a claim. Returns (claim, outcome).

        outcome: "added" | "reinforced" | "superseded" (added + closed old value).
        """
        now = time.time() if now is None else now
        subject = draft.subject.strip().casefold()
        predicate = draft.predicate.strip().casefold()
        value = draft.value.strip().casefold()
        if not subject or not predicate or not value:
            raise ValueError("Claim needs non-empty subject, predicate and value.")

        rows = self._conn.execute(
            "SELECT * FROM claims WHERE user_id=? AND subject=? AND predicate=? AND invalid_from IS NULL",
            (user_id, subject, predicate),
        ).fetchall()

        same = next((row for row in rows if row["value"] == value), None)
        if same is not None:
            trust = float(same["trust"])
            trust = trust + TRUST_REINFORCE_ETA * (TRUST_REINFORCE_TARGET - trust)
            self._conn.execute(
                "UPDATE claims SET support=support+1, trust=?, last_seen=? WHERE id=?",
                (trust, now, same["id"]),
            )
            self._conn.commit()
            return self.get_claim(int(same["id"])), "reinforced"

        outcome = "added"
        others = [row for row in rows if row["value"] != value]
        if draft.exclusive and others:
            outcome = "superseded"
        elif others:
            # Non-exclusive contradiction: keep both, but lower trust slightly
            # so repeated confirmation has to win the conflict.
            for row in others:
                trust = max(0.05, float(row["trust"]) - TRUST_CONTRADICTION_PENALTY)
                self._conn.execute("UPDATE claims SET trust=? WHERE id=?", (trust, row["id"]))

        cursor = self._conn.execute(
            """
            INSERT INTO claims
                (user_id, subject, predicate, value, kind, exclusive, support, trust,
                 created_at, last_seen, valid_from, invalid_from, superseded_by, source,
                 source_turn_id, source_session, embedding)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, ?)
            """,
            (
                user_id,
                subject,
                predicate,
                value,
                draft.kind,
                1 if draft.exclusive else 0,
                max(0.05, min(0.95, float(draft.confidence))),
                now,
                now,
                now,
                source,
                source_turn_id,
                source_session,
                _pack(self._embed(f"{subject} {predicate} {value}")),
            ),
        )
        new_id = int(cursor.lastrowid or 0)

        if draft.exclusive and others:
            for row in others:
                self._conn.execute(
                    "UPDATE claims SET invalid_from=?, superseded_by=? WHERE id=?",
                    (now, new_id, row["id"]),
                )
        self._conn.commit()
        return self.get_claim(new_id), outcome

    def get_claim(self, claim_id: int) -> Claim:
        row = self._conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if row is None:
            raise KeyError(f"Claim {claim_id} not found.")
        return self._claim_from_row(row)

    def active_claims(self, user_id: str, *, subject: str | None = None, predicate: str | None = None) -> list[Claim]:
        query = "SELECT * FROM claims WHERE user_id=? AND invalid_from IS NULL"
        args: list[object] = [user_id]
        if subject is not None:
            query += " AND subject=?"
            args.append(subject.strip().casefold())
        if predicate is not None:
            query += " AND predicate=?"
            args.append(predicate.strip().casefold())
        rows = self._conn.execute(query + " ORDER BY last_seen DESC", args).fetchall()
        return [self._claim_from_row(row) for row in rows]

    def claim_history(self, user_id: str, subject: str, predicate: str) -> list[Claim]:
        rows = self._conn.execute(
            "SELECT * FROM claims WHERE user_id=? AND subject=? AND predicate=? ORDER BY valid_from",
            (user_id, subject.strip().casefold(), predicate.strip().casefold()),
        ).fetchall()
        return [self._claim_from_row(row) for row in rows]

    def conflicts(self, user_id: str) -> list[ConflictHint]:
        rows = self._conn.execute(
            """
            SELECT subject, predicate, GROUP_CONCAT(value, '\u0001') AS vals
            FROM claims
            WHERE user_id=? AND invalid_from IS NULL
            GROUP BY subject, predicate
            HAVING COUNT(DISTINCT value) > 1
            """,
            (user_id,),
        ).fetchall()
        out: list[ConflictHint] = []
        for row in rows:
            values = sorted(set(str(row["vals"]).split("\u0001")))
            out.append(ConflictHint(subject=row["subject"], predicate=row["predicate"], values=values))
        return out

    def search_claims(self, user_id: str, query: str, *, limit: int = 16) -> list[tuple[Claim, float]]:
        """Semantic search over active claims (cosine over hash embeddings)."""
        q_vec = self._embed(query)
        rows = self._conn.execute(
            "SELECT * FROM claims WHERE user_id=? AND invalid_from IS NULL",
            (user_id,),
        ).fetchall()
        scored: list[tuple[Claim, float]] = []
        for row in rows:
            sim = cosine(q_vec, _unpack(row["embedding"]))
            scored.append((self._claim_from_row(row), sim))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[: max(1, limit)]

    def adjust_trust(self, claim_id: int, delta: float) -> None:
        row = self._conn.execute("SELECT trust FROM claims WHERE id=?", (claim_id,)).fetchone()
        if row is None:
            return
        trust = max(0.05, min(0.99, float(row["trust"]) + delta))
        self._conn.execute("UPDATE claims SET trust=? WHERE id=?", (trust, claim_id))
        self._conn.commit()

    def invalidate_claim(self, claim_id: int, *, now: float | None = None) -> bool:
        """Soft-delete a fact (validity window closes; history kept)."""
        now = time.time() if now is None else now
        cursor = self._conn.execute(
            "UPDATE claims SET invalid_from=? WHERE id=? AND invalid_from IS NULL",
            (now, claim_id),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def invalidate_claims(
        self,
        user_id: str,
        subject: str,
        predicate: str,
        *,
        value: str | None = None,
        now: float | None = None,
    ) -> int:
        now = time.time() if now is None else now
        subject = subject.strip().casefold()
        predicate = predicate.strip().casefold()
        if value is not None:
            cursor = self._conn.execute(
                """
                UPDATE claims SET invalid_from=?
                WHERE user_id=? AND subject=? AND predicate=? AND value=? AND invalid_from IS NULL
                """,
                (now, user_id, subject, predicate, value.strip().casefold()),
            )
        else:
            cursor = self._conn.execute(
                """
                UPDATE claims SET invalid_from=?
                WHERE user_id=? AND subject=? AND predicate=? AND invalid_from IS NULL
                """,
                (now, user_id, subject, predicate),
            )
        self._conn.commit()
        return int(cursor.rowcount)

    def delete_turn(self, turn_id: int) -> bool:
        self._conn.execute("DELETE FROM turn_chunks WHERE turn_id=?", (turn_id,))
        cursor = self._conn.execute("DELETE FROM turns WHERE id=?", (turn_id,))
        self._conn.commit()
        return cursor.rowcount > 0

    def purge_user(self, user_id: str) -> dict[str, int]:
        """Erase every memory row for one user_id."""
        counts = {
            "claims": self._conn.execute(
                "DELETE FROM claims WHERE user_id=?", (user_id,)
            ).rowcount,
            "turns": self._conn.execute(
                "DELETE FROM turns WHERE user_id=?", (user_id,)
            ).rowcount,
            "chunks": self._conn.execute(
                "DELETE FROM turn_chunks WHERE user_id=?", (user_id,)
            ).rowcount,
            "episodes": self._conn.execute(
                "DELETE FROM episodes WHERE user_id=?", (user_id,)
            ).rowcount,
        }
        self._conn.commit()
        return counts

    def count_matching_turns(
        self,
        user_id: str,
        query: str,
        *,
        min_similarity: float = 0.12,
    ) -> tuple[int, int, list[str]]:
        """Return (matching_turns, matching_sessions, session_ids)."""
        q_vec = self._embed(query)
        rows = self._conn.execute(
            "SELECT turn_id, session_id, embedding FROM turn_chunks WHERE user_id=?",
            (user_id,),
        ).fetchall()
        best: dict[int, float] = {}
        session_for_turn: dict[int, str] = {}
        for row in rows:
            turn_id = int(row["turn_id"])
            sim = cosine(q_vec, _unpack(row["embedding"]))
            session_for_turn[turn_id] = row["session_id"]
            if sim > best.get(turn_id, 0.0):
                best[turn_id] = sim
        matched = {tid for tid, sim in best.items() if sim >= min_similarity}
        sessions = sorted({session_for_turn[tid] for tid in matched})
        return len(matched), len(sessions), sessions

    # ------------------------------------------------------------ turns

    def add_turn(self, session_id: str, user_id: str, role: str, text: str, *, now: float | None = None) -> int:
        now = time.time() if now is None else now
        cursor = self._conn.execute(
            "INSERT INTO turns (session_id, user_id, role, text, created_at, embedding) VALUES (?, ?, ?, ?, ?, NULL)",
            (session_id, user_id, role, text.strip(), now),
        )
        turn_id = int(cursor.lastrowid or 0)
        for chunk in split_chunks(text):
            self._conn.execute(
                "INSERT INTO turn_chunks (turn_id, user_id, session_id, text, embedding) VALUES (?, ?, ?, ?, ?)",
                (turn_id, user_id, session_id, chunk, _pack(self._embed(chunk))),
            )
        self._conn.commit()
        return turn_id

    def search_turns(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 6,
        exclude_session: str | None = None,
    ) -> list[tuple[Turn, float]]:
        """Semantic search over turn chunks; a turn scores as its best chunk."""
        q_vec = self._embed(query)
        rows = self._conn.execute(
            "SELECT turn_id, session_id, embedding FROM turn_chunks WHERE user_id=?",
            (user_id,),
        ).fetchall()
        best: dict[int, float] = {}
        for row in rows:
            if exclude_session and row["session_id"] == exclude_session:
                continue
            sim = cosine(q_vec, _unpack(row["embedding"]))
            if sim <= 0.02:
                continue
            turn_id = int(row["turn_id"])
            if sim > best.get(turn_id, 0.0):
                best[turn_id] = sim

        ranked = sorted(best.items(), key=lambda pair: pair[1], reverse=True)[: max(1, limit)]
        out: list[tuple[Turn, float]] = []
        for turn_id, sim in ranked:
            row = self._conn.execute("SELECT * FROM turns WHERE id=?", (turn_id,)).fetchone()
            if row is None:
                continue
            out.append(
                (
                    Turn(
                        id=int(row["id"]),
                        session_id=row["session_id"],
                        user_id=row["user_id"],
                        role=row["role"],
                        text=row["text"],
                        created_at=float(row["created_at"]),
                    ),
                    sim,
                )
            )
        return out

    # --------------------------------------------------------- events

    def add_memory_event(
        self,
        user_id: str,
        session_id: str,
        *,
        turn_id: int | None,
        role: str,
        label: str,
        category: str = "event",
        happened_at: float | None = None,
    ) -> int:
        now = time.time() if happened_at is None else happened_at
        label = " ".join(str(label).split()).strip()
        if not label:
            raise ValueError("Event label must be non-empty.")
        cursor = self._conn.execute(
            """
            INSERT INTO memory_events
                (user_id, session_id, turn_id, role, label, category, happened_at, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                session_id,
                turn_id,
                role,
                label,
                category,
                now,
                _pack(self._embed(label)),
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid or 0)

    def search_memory_events(
        self,
        user_id: str,
        query: str,
        *,
        limit: int = 24,
        exclude_session: str | None = None,
        reference_before: float | None = None,
    ) -> list[MemoryEvent]:
        q_vec = self._embed(query)
        rows = self._conn.execute(
            "SELECT * FROM memory_events WHERE user_id=? ORDER BY happened_at",
            (user_id,),
        ).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            if exclude_session and row["session_id"] == exclude_session:
                continue
            happened_at = float(row["happened_at"])
            if reference_before is not None and happened_at > reference_before + 86400:
                continue
            sim = cosine(q_vec, _unpack(row["embedding"]))
            if query.strip() and sim <= 0.05:
                continue
            scored.append((sim, row))
        if not scored and rows:
            for row in rows:
                if exclude_session and row["session_id"] == exclude_session:
                    continue
                happened_at = float(row["happened_at"])
                if reference_before is not None and happened_at > reference_before + 86400:
                    continue
                scored.append((0.0, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        out: list[MemoryEvent] = []
        for _, row in scored[: max(1, limit * 2)]:
            out.append(self._event_from_row(row))
        return out[: max(1, limit)]

    def list_memory_events(
        self,
        user_id: str,
        *,
        exclude_session: str | None = None,
        reference_before: float | None = None,
        limit: int = 200,
    ) -> list[MemoryEvent]:
        rows = self._conn.execute(
            "SELECT * FROM memory_events WHERE user_id=? ORDER BY happened_at",
            (user_id,),
        ).fetchall()
        out: list[MemoryEvent] = []
        for row in rows:
            if exclude_session and row["session_id"] == exclude_session:
                continue
            happened_at = float(row["happened_at"])
            if reference_before is not None and happened_at > reference_before + 86400:
                continue
            out.append(self._event_from_row(row))
            if len(out) >= limit:
                break
        return out

    def recent_turns(self, session_id: str, *, limit: int = 8) -> list[Turn]:
        rows = self._conn.execute(
            "SELECT * FROM turns WHERE session_id=? ORDER BY id DESC LIMIT ?",
            (session_id, max(1, limit)),
        ).fetchall()
        turns = [
            Turn(
                id=int(row["id"]),
                session_id=row["session_id"],
                user_id=row["user_id"],
                role=row["role"],
                text=row["text"],
                created_at=float(row["created_at"]),
            )
            for row in rows
        ]
        turns.reverse()
        return turns

    # --------------------------------------------------------- episodes

    def touch_episode(
        self, session_id: str, user_id: str, topic: str, *, now: float | None = None
    ) -> EpisodeTouch:
        """Extend the current episode or open a new one (gap-based merge)."""
        now = time.time() if now is None else now
        row = self._conn.execute(
            "SELECT * FROM episodes WHERE session_id=? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row is not None and now - float(row["last_at"]) <= EPISODE_GAP_SECONDS and int(row["turns"]) < 50:
            new_topic = topic.strip() or str(row["topic"])
            self._conn.execute(
                "UPDATE episodes SET last_at=?, turns=turns+1, topic=?, embedding=? WHERE id=?",
                (now, new_topic, _pack(self._embed(new_topic)) if new_topic else row["embedding"], row["id"]),
            )
            self._conn.commit()
            return EpisodeTouch(episode_id=int(row["id"]))

        closed_id: int | None = None
        if row is not None and int(row["turns"]) >= 2 and not str(row["summary"] or "").strip():
            closed_id = int(row["id"])

        cursor = self._conn.execute(
            "INSERT INTO episodes (session_id, user_id, first_at, last_at, turns, topic, summary, embedding)"
            " VALUES (?, ?, ?, ?, 1, ?, '', ?)",
            (session_id, user_id, now, now, topic.strip(), _pack(self._embed(topic)) if topic.strip() else None),
        )
        self._conn.commit()
        return EpisodeTouch(episode_id=int(cursor.lastrowid or 0), closed_episode_id=closed_id)

    def get_episode(self, episode_id: int) -> Episode | None:
        row = self._conn.execute("SELECT * FROM episodes WHERE id=?", (episode_id,)).fetchone()
        if row is None:
            return None
        return Episode(
            id=int(row["id"]),
            session_id=row["session_id"],
            user_id=row["user_id"],
            first_at=float(row["first_at"]),
            last_at=float(row["last_at"]),
            turns=int(row["turns"]),
            topic=row["topic"],
            summary=row["summary"] or "",
        )

    def turns_in_episode(self, episode_id: int) -> list[Turn]:
        episode = self.get_episode(episode_id)
        if episode is None:
            return []
        rows = self._conn.execute(
            """
            SELECT * FROM turns
            WHERE session_id=? AND created_at >= ? AND created_at <= ?
            ORDER BY id
            """,
            (episode.session_id, episode.first_at, episode.last_at),
        ).fetchall()
        return [
            Turn(
                id=int(row["id"]),
                session_id=row["session_id"],
                user_id=row["user_id"],
                role=row["role"],
                text=row["text"],
                created_at=float(row["created_at"]),
            )
            for row in rows
        ]

    def set_episode_summary(self, episode_id: int, summary: str) -> None:
        summary = summary.strip()
        if not summary:
            return
        row = self._conn.execute("SELECT topic FROM episodes WHERE id=?", (episode_id,)).fetchone()
        topic = row["topic"] if row else ""
        self._conn.execute(
            "UPDATE episodes SET summary=?, embedding=? WHERE id=?",
            (summary, _pack(self._embed(f"{topic} {summary}")), episode_id),
        )
        self._conn.commit()

    def list_episodes_needing_summary(
        self, user_id: str, *, session_id: str | None = None, min_turns: int = 2
    ) -> list[int]:
        query = (
            "SELECT id FROM episodes WHERE user_id=? AND turns >= ?"
            " AND (summary IS NULL OR summary='')"
        )
        args: list[object] = [user_id, min_turns]
        if session_id:
            query += " AND session_id=?"
            args.append(session_id)
        query += " ORDER BY id"
        rows = self._conn.execute(query, args).fetchall()
        return [int(row["id"]) for row in rows]

    def search_episodes(self, user_id: str, query: str, *, limit: int = 3, exclude_session: str | None = None) -> list[Episode]:
        q_vec = self._embed(query)
        rows = self._conn.execute("SELECT * FROM episodes WHERE user_id=?", (user_id,)).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            if exclude_session and row["session_id"] == exclude_session:
                continue
            sim = cosine(q_vec, _unpack(row["embedding"]))
            if sim > 0.05:
                scored.append((sim, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            Episode(
                id=int(row["id"]),
                session_id=row["session_id"],
                user_id=row["user_id"],
                first_at=float(row["first_at"]),
                last_at=float(row["last_at"]),
                turns=int(row["turns"]),
                topic=row["topic"],
                summary=row["summary"],
            )
            for _, row in scored[: max(1, limit)]
        ]

    # ------------------------------------------------------------- meta

    def save_meta(self, key: str, payload: object) -> None:
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def load_meta(self, key: str) -> object | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return None
        return json.loads(row["value"])

    def stats(self) -> dict[str, int]:
        def count(query: str) -> int:
            return int(self._conn.execute(query).fetchone()[0])

        return {
            "claims_total": count("SELECT COUNT(*) FROM claims"),
            "claims_active": count("SELECT COUNT(*) FROM claims WHERE invalid_from IS NULL"),
            "turns": count("SELECT COUNT(*) FROM turns"),
            "episodes": count("SELECT COUNT(*) FROM episodes"),
            "memory_events": count("SELECT COUNT(*) FROM memory_events"),
        }

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> MemoryEvent:
        return MemoryEvent(
            id=int(row["id"]),
            user_id=row["user_id"],
            session_id=row["session_id"],
            turn_id=(None if row["turn_id"] is None else int(row["turn_id"])),
            role=row["role"],
            label=row["label"],
            category=row["category"],
            happened_at=float(row["happened_at"]),
        )

    # ---------------------------------------------------------- private

    @staticmethod
    def _claim_from_row(row: sqlite3.Row) -> Claim:
        keys = row.keys()
        return Claim(
            id=int(row["id"]),
            user_id=row["user_id"],
            subject=row["subject"],
            predicate=row["predicate"],
            value=row["value"],
            kind=row["kind"],
            exclusive=bool(row["exclusive"]),
            support=int(row["support"]),
            trust=float(row["trust"]),
            created_at=float(row["created_at"]),
            last_seen=float(row["last_seen"]),
            valid_from=float(row["valid_from"]),
            invalid_from=(None if row["invalid_from"] is None else float(row["invalid_from"])),
            superseded_by=(None if row["superseded_by"] is None else int(row["superseded_by"])),
            source=row["source"],
            source_turn_id=(
                None if "source_turn_id" not in keys or row["source_turn_id"] is None else int(row["source_turn_id"])
            ),
            source_session=(
                None if "source_session" not in keys else row["source_session"]
            ),
        )
