"""EverMem facade: observe / recall / feedback.

The loop:
1. `observe(text)`   store the turn, extract claims, update episodes and plasticity.
2. `recall(query)`   hybrid retrieval (semantic + recency + trust + learned paths)
                       returns a MemoryPack ready to inject into any LLM prompt.
3. `feedback(bool)`  reinforce or punish the claims and paths used in the last
                       recall; memory literally gets better with use.
"""

from __future__ import annotations

import datetime as _dt
import time
from pathlib import Path

from .corrections import extract_rule_purchase_claims, prepare_observe_drafts
from .extractor import LLMExtractor, RuleExtractor
from .plasticity import PathPlasticity
from .counters import extract_countable_claims, summarize_entity_counts
from .events import build_temporal_gaps, extract_assistant_claims, extract_memory_events
from .query_intent import (
    count_topic_from_query,
    looks_like_count_query,
    looks_like_order_query,
    looks_like_recommend_query,
    looks_like_temporal_query,
    query_profile,
    temporal_topic_from_query,
)
from .store import ClaimStore
from .summarize import summarize_episode
from .types import (
    AggregateResult,
    Claim,
    ConflictHint,
    MemoryEventSummary,
    MemoryPack,
    ObserveReport,
    ScoredClaim,
    SessionPrimer,
)

W_SIMILARITY = 0.55
W_RECENCY = 0.15
W_TRUST = 0.20
W_PATH = 0.10
RECENCY_HALFLIFE_SECONDS = 86400.0 * 7
MIN_CLAIM_SCORE = 0.08
MIN_TRUST_RECALL = 0.15
STALE_CLAIM_DAYS = 90


class EverMem:
    def __init__(
        self,
        path: str | Path = ":memory:",
        *,
        llm=None,
        extractor=None,
        embedder=None,
        user_id: str = "default",
    ) -> None:
        self.store = ClaimStore(path, embed_fn=embedder)
        self.default_user = user_id
        if extractor is not None:
            self.extractor = extractor
        elif llm is not None:
            self.extractor = LLMExtractor(llm)
        else:
            self.extractor = RuleExtractor()
        self._llm = llm
        self.plasticity = PathPlasticity()
        saved = self.store.load_meta("plasticity")
        if isinstance(saved, list):
            self.plasticity.load_state(saved)
        self._last_recall: dict[tuple[str, str], list[Claim]] = {}

    def close(self) -> None:
        self._persist_plasticity()
        self.store.close()

    # ------------------------------------------------------------ write

    def observe(
        self,
        text: str,
        *,
        session_id: str = "default",
        user_id: str | None = None,
        role: str = "user",
        happened_at: float | None = None,
    ) -> ObserveReport:
        uid = user_id or self.default_user
        turn_id = self.store.add_turn(session_id, uid, role, text, now=happened_at)

        added = reinforced = superseded = events_added = 0
        topic = ""
        all_drafts: list = []
        if role == "user":
            result = self.extractor.extract(text, speaker="user")
            topic = result.topic
            all_drafts.extend(result.claims)
            all_drafts.extend(extract_rule_purchase_claims(text, speaker="user"))
            all_drafts.extend(extract_countable_claims(text, speaker="user"))
        elif role == "assistant":
            from .extractor import ExtractionResult

            assistant_result = self.extractor.extract(text, speaker="user")
            topic = assistant_result.topic or "assistant"
            all_drafts.extend(extract_assistant_claims(text))
            all_drafts.extend(assistant_result.claims)
            all_drafts.extend(extract_countable_claims(text, speaker="user"))
        else:
            from .extractor import ExtractionResult

            result = ExtractionResult(claims=[], topic="")
            topic = role

        event_at = happened_at if happened_at is not None else time.time()
        for draft in extract_memory_events(text):
            try:
                self.store.add_memory_event(
                    uid,
                    session_id,
                    turn_id=turn_id,
                    role=role,
                    label=draft.label,
                    category=draft.category,
                    happened_at=event_at,
                )
                events_added += 1
            except ValueError:
                continue

        all_drafts = prepare_observe_drafts(
            text,
            role,
            all_drafts,
            store=self.store,
            user_id=uid,
            now=happened_at,
        )

        for draft in all_drafts:
            try:
                claim, outcome = self.store.upsert_claim(
                    uid,
                    draft,
                    source=role,
                    source_turn_id=turn_id,
                    source_session=session_id,
                    now=happened_at,
                )
            except ValueError:
                continue
            if outcome == "added":
                added += 1
            elif outcome == "reinforced":
                reinforced += 1
            else:
                superseded += 1
                added += 1
            self.plasticity.update_path(
                self._claim_path(uid, claim),
                reward=0.6,
                confidence=draft.confidence,
            )

        topic = topic or (all_drafts[0].predicate if all_drafts else "")
        touch = self.store.touch_episode(session_id, uid, topic, now=happened_at)
        if touch.closed_episode_id is not None:
            self._summarize_episode(touch.closed_episode_id)
        self._persist_plasticity()
        return ObserveReport(
            turn_id=turn_id,
            claims_added=added,
            claims_reinforced=reinforced,
            claims_superseded=superseded,
            topic=topic,
            events_added=events_added,
        )

    def observe_file(
        self,
        path: str | Path,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        extract_claims: bool = False,
        block_chars: int = 1000,
    ):
        """Ingest a document (PDF/DOCX/HTML/Markdown/text) into memory.

        Each paragraph-aligned block becomes a searchable turn with role
        "document", so recall() can quote the exact matching passage. With
        extract_claims=True every block also goes through the extractor
        (useful with an LLM extractor; rule patterns rarely fire on prose).
        """
        from .ingest import IngestReport, extract_text, split_blocks

        file = Path(path)
        text = extract_text(file)
        blocks = split_blocks(text, max_chars=block_chars)
        uid = user_id or self.default_user
        sid = session_id or f"file:{file.resolve()}"
        happened_at = file.stat().st_mtime

        claims_added = 0
        for block in blocks:
            self.store.add_turn(sid, uid, "document", block, now=happened_at)
            if extract_claims:
                result = self.extractor.extract(block, speaker="document")
                for draft in result.claims:
                    try:
                        _, outcome = self.store.upsert_claim(
                            uid, draft, source="document", now=happened_at
                        )
                    except ValueError:
                        continue
                    if outcome in ("added", "superseded"):
                        claims_added += 1
        touch = self.store.touch_episode(sid, uid, file.stem, now=happened_at)
        if touch.closed_episode_id is not None:
            self._summarize_episode(touch.closed_episode_id)
        return IngestReport(
            path=str(file),
            session_id=sid,
            blocks=len(blocks),
            characters=len(text),
            claims_added=claims_added,
        )

    def remember(
        self,
        subject: str,
        predicate: str,
        value: str,
        *,
        exclusive: bool = False,
        user_id: str | None = None,
    ) -> Claim:
        """Direct structured write, bypassing extraction."""
        from .types import ClaimDraft

        uid = user_id or self.default_user
        claim, _ = self.store.upsert_claim(
            uid,
            ClaimDraft(subject=subject, predicate=predicate, value=value, exclusive=exclusive),
            source="api",
        )
        return claim

    # ------------------------------------------------------------- read

    def recall(
        self,
        query: str,
        *,
        session_id: str = "default",
        user_id: str | None = None,
        claims_limit: int = 8,
        turns_limit: int = 6,
        history_limit: int = 6,
        episodes_limit: int = 2,
        reference_time: float | None = None,
        max_per_session: int = 2,
        min_trust: float = MIN_TRUST_RECALL,
    ) -> MemoryPack:
        uid = user_id or self.default_user
        now = reference_time if reference_time is not None else time.time()
        profile = query_profile(query)
        effective_history_limit = history_limit
        effective_max_per_session = max_per_session
        if profile in {"count", "temporal", "order"}:
            effective_history_limit = max(history_limit, 16)
            effective_max_per_session = max(max_per_session, 4)

        candidates = self.store.search_claims(uid, query, limit=max(24, claims_limit * 4))
        scored: list[ScoredClaim] = []
        seen_claim_ids: set[int] = set()
        for claim, sim in candidates:
            if claim.trust < min_trust:
                continue
            age = max(0.0, now - claim.last_seen)
            recency = 1.0 / (1.0 + age / RECENCY_HALFLIFE_SECONDS)
            path = self.plasticity.path_score(self._claim_path(uid, claim))
            path_norm = min(1.0, path / 1.6)
            score = W_SIMILARITY * sim + W_RECENCY * recency + W_TRUST * claim.trust + W_PATH * path_norm
            if sim <= 0.0 and score < 0.25:
                continue
            scored.append(ScoredClaim(claim=claim, score=score))
            seen_claim_ids.add(claim.id)

        if looks_like_recommend_query(query):
            for claim in self.store.active_claims(uid):
                if claim.id in seen_claim_ids:
                    continue
                if claim.kind != "preference" and claim.predicate not in {
                    "likes",
                    "interest",
                    "prefers",
                    "skill_level",
                }:
                    continue
                scored.append(ScoredClaim(claim=claim, score=0.55 + claim.trust * 0.3))
                seen_claim_ids.add(claim.id)

        scored.sort(key=lambda item: item.score, reverse=True)
        top = [item for item in scored if item.score >= MIN_CLAIM_SCORE][: max(1, claims_limit)]

        retrieved_keys = {(item.claim.subject, item.claim.predicate) for item in top}
        conflicts = [
            hint
            for hint in self.store.conflicts(uid)
            if (hint.subject, hint.predicate) in retrieved_keys
        ]

        # Fetch extra candidates, then cap per session so multi-session
        # questions see breadth instead of one conversation dominating.
        candidates_turns = self.store.search_turns(
            uid,
            query,
            limit=max(effective_history_limit * 3, effective_history_limit),
            exclude_session=session_id,
        )
        history: list = []
        per_session: dict[str, int] = {}
        for turn, _score in candidates_turns:
            if per_session.get(turn.session_id, 0) >= max(1, effective_max_per_session):
                continue
            history.append(turn)
            per_session[turn.session_id] = per_session.get(turn.session_id, 0) + 1
            if len(history) >= effective_history_limit:
                break

        aggregation = None
        entity_counts: list = []
        if looks_like_count_query(query):
            aggregation = self.aggregate(count_topic_from_query(query), user_id=uid)
            entity_counts = summarize_entity_counts(self.store.active_claims(uid), query)

        chronology: list = []
        if looks_like_order_query(query):
            order_candidates = self.store.search_turns(
                uid,
                query,
                limit=max(effective_history_limit * 4, 16),
                exclude_session=session_id,
            )
            chronology = [turn for turn, _ in sorted(order_candidates, key=lambda pair: pair[0].created_at)]

        timeline_events: list[MemoryEventSummary] = []
        temporal_gaps: list = []
        if profile in {"temporal", "order"} or looks_like_temporal_query(query):
            event_query = query if profile == "temporal" else temporal_topic_from_query(query) or query
            event_pool = self.store.search_memory_events(
                uid,
                event_query,
                limit=32,
                exclude_session=session_id,
                reference_before=now,
            )
            if len(event_pool) < 4:
                event_pool = self.store.list_memory_events(
                    uid,
                    exclude_session=session_id,
                    reference_before=now,
                    limit=120,
                )
            picked_events, temporal_gaps = build_temporal_gaps(
                event_pool,
                reference_ts=now,
                query=query,
            )
            for event in picked_events:
                if event.happened_at <= 0:
                    continue
                date_iso = _dt.date.fromtimestamp(event.happened_at).isoformat()
                days_before = max(0, round((now - event.happened_at) / 86400.0))
                timeline_events.append(
                    MemoryEventSummary(
                        label=event.label,
                        date_iso=date_iso,
                        days_before_question=days_before,
                        category=event.category,
                    )
                )

        pack = MemoryPack(
            query=query,
            claims=top,
            turns=self.store.recent_turns(session_id, limit=turns_limit),
            history=history,
            episodes=self.store.search_episodes(
                uid, query, limit=episodes_limit, exclude_session=session_id
            ),
            conflicts=conflicts,
            aggregation=aggregation,
            entity_counts=entity_counts,
            chronology=chronology,
            timeline_events=timeline_events,
            temporal_gaps=temporal_gaps,
            query_profile=profile,
            reference_ts=reference_time,
        )
        self._last_recall[(uid, session_id)] = [item.claim for item in top]
        return pack

    def bootstrap(
        self,
        *,
        user_id: str | None = None,
        max_claims: int = 20,
        stale_days: int = STALE_CLAIM_DAYS,
    ) -> SessionPrimer:
        """Session primer: call at the start of every agent session.

        Surfaces durable facts, open conflicts and possibly stale items so the
        agent does not act on ghosts or contradictions from prior sessions.
        """
        uid = user_id or self.default_user
        now = time.time()
        claims = sorted(
            self.store.active_claims(uid),
            key=lambda claim: (claim.trust, claim.last_seen),
            reverse=True,
        )
        stale = [
            claim
            for claim in claims
            if now - claim.last_seen > stale_days * 86400.0 and claim.trust < 0.85
        ]
        stale_ids = {claim.id for claim in stale}
        fresh = [claim for claim in claims if claim.id not in stale_ids]
        stats = self.store.stats()
        return SessionPrimer(
            user_id=uid,
            claims=fresh[:max_claims],
            conflicts=self.store.conflicts(uid),
            stale_claims=stale[:10],
            stats=stats,
        )

    def aggregate(
        self,
        query: str,
        *,
        user_id: str | None = None,
        min_similarity: float = 0.12,
    ) -> AggregateResult:
        """Count how many turns/sessions match a topic (e.g. 'how many times did I...')."""
        uid = user_id or self.default_user
        turns, sessions, session_ids = self.store.count_matching_turns(
            uid, query, min_similarity=min_similarity
        )
        return AggregateResult(
            query=query,
            matching_turns=turns,
            matching_sessions=sessions,
            session_ids=session_ids,
        )

    def profile(self, user_id: str | None = None) -> list[Claim]:
        return self.store.active_claims(user_id or self.default_user)

    def conflicts(self, user_id: str | None = None) -> list[ConflictHint]:
        return self.store.conflicts(user_id or self.default_user)

    def history(self, subject: str, predicate: str, *, user_id: str | None = None) -> list[Claim]:
        return self.store.claim_history(user_id or self.default_user, subject, predicate)

    # ------------------------------------------------------- lifecycle

    def forget_claim(self, claim_id: int) -> bool:
        """Invalidate one fact by id (history preserved, no longer recalled)."""
        return self.store.invalidate_claim(claim_id)

    def forget(
        self,
        subject: str,
        predicate: str,
        *,
        value: str | None = None,
        user_id: str | None = None,
    ) -> int:
        """Invalidate active fact(s) matching subject/predicate[/value]."""
        return self.store.invalidate_claims(
            user_id or self.default_user, subject, predicate, value=value
        )

    def correct(
        self,
        subject: str,
        predicate: str,
        new_value: str,
        *,
        user_id: str | None = None,
        source_session: str | None = None,
    ) -> Claim:
        """Supersede the current value and write the corrected fact."""
        from .types import ClaimDraft

        uid = user_id or self.default_user
        claim, _ = self.store.upsert_claim(
            uid,
            ClaimDraft(subject=subject, predicate=predicate, value=new_value, exclusive=True),
            source="correction",
            source_session=source_session,
        )
        return claim

    def purge(self, user_id: str | None = None) -> dict[str, int]:
        """Erase all memory for one user (GDPR-style erasure)."""
        return self.store.purge_user(user_id or self.default_user)

    def consolidate(self, *, session_id: str | None = None, user_id: str | None = None) -> int:
        """Summarize episodes that have turns but no summary yet (sleep-time compute)."""
        uid = user_id or self.default_user
        ids = self.store.list_episodes_needing_summary(uid, session_id=session_id)
        for episode_id in ids:
            self._summarize_episode(episode_id)
        return len(ids)

    # --------------------------------------------------------- feedback

    def feedback(
        self,
        helpful: bool,
        *,
        session_id: str = "default",
        user_id: str | None = None,
    ) -> int:
        """Reward or punish the claims used in the previous recall()."""
        uid = user_id or self.default_user
        claims = self._last_recall.get((uid, session_id), [])
        for claim in claims:
            nodes = self._claim_path(uid, claim)
            if helpful:
                self.plasticity.update_path(nodes, reward=0.9, confidence=0.8)
                self.store.adjust_trust(claim.id, +0.05)
            else:
                self.plasticity.update_path(nodes, reward=0.0, confidence=0.8, contradiction=0.8)
                self.store.adjust_trust(claim.id, -0.08)
        self._persist_plasticity()
        return len(claims)

    def stats(self) -> dict[str, int]:
        out = self.store.stats()
        out["plasticity_edges"] = self.plasticity.edge_count()
        return out

    # ---------------------------------------------------------- private

    @staticmethod
    def _claim_path(user_id: str, claim: Claim) -> list[str]:
        return [
            f"u:{user_id}",
            f"s:{claim.subject}",
            f"p:{claim.predicate}",
            f"v:{claim.value}",
        ]

    def _persist_plasticity(self) -> None:
        self.store.save_meta("plasticity", self.plasticity.export_state())

    def _summarize_episode(self, episode_id: int) -> None:
        episode = self.store.get_episode(episode_id)
        if episode is None or episode.summary.strip():
            return
        turns = self.store.turns_in_episode(episode_id)
        if len(turns) < 2:
            return
        summary = summarize_episode(turns, topic=episode.topic, llm=self._llm)
        self.store.set_episode_summary(episode_id, summary)
