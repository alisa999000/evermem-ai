"""Portable JSON export/import for backup and migration."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path

from .memory import EverMem
from .types import ClaimDraft


def export_json(path: str | Path, *, user_id: str | None = None) -> dict:
    """Dump claims, turns and meta to a JSON-serializable dict."""
    db_path = str(path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    out: dict = {"version": 1, "users": {}}

    user_filter = ""
    args: list = []
    if user_id:
        user_filter = " WHERE user_id=?"
        args = [user_id]

    claims = conn.execute(f"SELECT * FROM claims{user_filter} ORDER BY id", args).fetchall()
    turns = conn.execute(f"SELECT * FROM turns{user_filter} ORDER BY id", args).fetchall()
    meta_rows = conn.execute("SELECT key, value FROM meta").fetchall()

    users: dict[str, dict] = {}
    for row in claims:
        uid = row["user_id"]
        users.setdefault(uid, {"claims": [], "turns": []})
        users[uid]["claims"].append({key: row[key] for key in row.keys()})

    for row in turns:
        uid = row["user_id"]
        users.setdefault(uid, {"claims": [], "turns": []})
        users[uid]["turns"].append({key: row[key] for key in row.keys()})

    out["users"] = users
    out["meta"] = {row["key"]: json.loads(row["value"]) for row in meta_rows}
    conn.close()
    return out


def write_export(mem_path: str | Path, out_path: str | Path, *, user_id: str | None = None) -> None:
    payload = export_json(mem_path, user_id=user_id)
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def import_json(mem: EverMem, payload: dict, *, user_id: str | None = None) -> dict[str, int]:
    """Restore claims and turns from an export payload into an open EverMem."""
    counts = {"claims": 0, "turns": 0}
    users = payload.get("users", {})
    target_users = [user_id] if user_id else list(users.keys())
    for uid in target_users:
        block = users.get(uid, {})
        for turn in block.get("turns", []):
            mem.store.add_turn(
                turn["session_id"],
                uid,
                turn["role"],
                turn["text"],
                now=float(turn.get("created_at") or 0) or None,
            )
            counts["turns"] += 1
        for claim in block.get("claims", []):
            if claim.get("invalid_from") is not None:
                continue
            mem.store.upsert_claim(
                uid,
                ClaimDraft(
                    subject=claim["subject"],
                    predicate=claim["predicate"],
                    value=claim["value"],
                    kind=claim.get("kind", "fact"),
                    exclusive=bool(claim.get("exclusive")),
                ),
                source=claim.get("source", "import"),
                source_session=claim.get("source_session"),
            )
            counts["claims"] += 1
    plasticity = payload.get("meta", {}).get("plasticity")
    if isinstance(plasticity, list):
        mem.plasticity.load_state(plasticity)
        mem._persist_plasticity()
    return counts
