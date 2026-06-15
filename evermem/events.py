"""Temporal memory events: ingest-time indexing for date math and ordering.

Events are short labels tied to `happened_at` timestamps. At recall time we
search the full event index (not just retrieved turn snippets) and pre-compute
day gaps so weak reader models do not have to do calendar arithmetic.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass

from .embeddings import cosine, embed, token_key, tokens
from .query_intent import temporal_topic_from_query
from .types import ClaimDraft, TemporalGapSummary

_EVENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:attended|went to|visited|joined)\s+(?:the\s+)?(.{4,70})", re.I), "attended"),
    (re.compile(r"\b(?:finished|completed|read|watched)\s+(?:the\s+)?(.{4,70})", re.I), "finished"),
    (re.compile(r"\b(?:started|began|signed up for)\s+(?:the\s+)?(.{4,70})", re.I), "started"),
    (re.compile(r"\b(?:bought|purchased|picked up|got)\s+(?:the\s+)?(.{4,70})", re.I), "acquired"),
    (re.compile(r"\b(?:met|saw)\s+(?:with\s+)?(.{4,50})", re.I), "met"),
    (re.compile(r"\b(?:moved to|relocated to)\s+(.{4,50})", re.I), "moved"),
    (re.compile(r"\b(?:adopted|gave birth to)\s+(?:a\s+)?(.{4,50})", re.I), "family"),
    (re.compile(r"\b(?:charity|fundraising|volunteer)\s+(.{4,60})", re.I), "charity"),
    (re.compile(r"\b(?:mass|service|festival|webinar|workshop|conference)\b.{0,40}", re.I), "event"),
    (re.compile(r"\b(?:free trial|subscribed to|started using)\s+(.{4,50})", re.I), "subscription"),
]


@dataclass
class EventDraft:
    label: str
    category: str = "event"


@dataclass
class MemoryEvent:
    id: int
    user_id: str
    session_id: str
    turn_id: int | None
    role: str
    label: str
    category: str
    happened_at: float


def extract_memory_events(text: str) -> list[EventDraft]:
    """Turn user/assistant prose into searchable dated event labels."""
    clean = " ".join(str(text).split())
    if len(clean) < 8:
        return []
    drafts: list[EventDraft] = []
    seen: set[str] = set()
    for pattern, category in _EVENT_PATTERNS:
        for match in pattern.finditer(clean):
            label = _normalize_label(match.group(0))
            if not label or label in seen:
                continue
            seen.add(label)
            drafts.append(EventDraft(label=label[:120], category=category))
            if len(drafts) >= 6:
                return drafts
    if not drafts and len(tokens(clean)) >= 4 and "?" not in clean[:40]:
        short = clean[:100]
        key = token_key(short)
        if key and key not in seen:
            drafts.append(EventDraft(label=short, category="mention"))
    return drafts


def extract_assistant_claims(text: str) -> list[ClaimDraft]:
    """Structured claims from assistant recommendations (preference questions)."""
    clean = " ".join(str(text).split())
    claims: list[ClaimDraft] = []
    patterns: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bI(?:'d| would) recommend\s+(.{4,80})", re.I), "recommendation"),
        (re.compile(r"\bYou (?:might|should|could) (?:try|check out|read|watch)\s+(.{4,80})", re.I), "recommendation"),
        (re.compile(r"\bHere are (?:some|a few)\s+(.{4,80})", re.I), "recommendation"),
        (re.compile(r"\b(?:great|good|excellent) (?:choice|option)s?\s+(?:for you|would be)\s+(.{4,80})", re.I), "recommendation"),
        (re.compile(r"\b(?:suggest|recommend)(?:ing|ation)?\s+(.{4,80})", re.I), "recommendation"),
    ]
    for pattern, predicate in patterns:
        match = pattern.search(clean)
        if not match:
            continue
        value = _normalize_label(match.group(1))
        if value:
            claims.append(
                ClaimDraft(
                    subject="user",
                    predicate=predicate,
                    value=value,
                    kind="preference",
                    exclusive=False,
                    confidence=0.74,
                )
            )
    return claims


def build_temporal_gaps(
    events: list[MemoryEvent],
    *,
    reference_ts: float | None,
    query: str = "",
    limit_pairs: int = 15,
) -> tuple[list[MemoryEvent], list[TemporalGapSummary]]:
    """Pick query-relevant events and compute day gaps between their dates."""
    if not events:
        return [], []

    topic = temporal_topic_from_query(query) if query else ""
    topic_vec = embed(topic) if topic else []
    scored: list[tuple[float, MemoryEvent]] = []
    for event in events:
        if reference_ts is not None and event.happened_at > reference_ts + 86400:
            continue
        sim = cosine(topic_vec, embed(event.label)) if topic_vec else 0.25
        if topic and sim < 0.12:
            blob = f"{event.label} {event.category}".lower()
            if not any(t in blob for t in tokens(topic) if len(t) > 3):
                continue
        scored.append((sim, event))

    if not scored:
        scored = [(0.0, event) for event in events]

    scored.sort(key=lambda pair: pair[0], reverse=True)
    picked: list[MemoryEvent] = []
    seen_ids: set[int] = set()
    for _, event in scored:
        if event.id in seen_ids:
            continue
        seen_ids.add(event.id)
        picked.append(event)
        if len(picked) >= 12:
            break
    picked.sort(key=lambda event: event.happened_at)

    dates = [
        (_dt.date.fromtimestamp(event.happened_at), event)
        for event in picked
        if event.happened_at > 0
    ]
    if len(dates) < 2:
        return picked, []

    gaps: list[TemporalGapSummary] = []
    if len(dates) <= 6:
        for i in range(len(dates)):
            for j in range(i + 1, len(dates)):
                first_date, first_event = dates[i]
                second_date, second_event = dates[j]
                gaps.append(
                    TemporalGapSummary(
                        earlier_label=first_event.label,
                        later_label=second_event.label,
                        earlier_date=first_date.isoformat(),
                        later_date=second_date.isoformat(),
                        days=(second_date - first_date).days,
                    )
                )
    else:
        for i in range(len(dates) - 1):
            first_date, first_event = dates[i]
            second_date, second_event = dates[i + 1]
            gaps.append(
                TemporalGapSummary(
                    earlier_label=first_event.label,
                    later_label=second_event.label,
                    earlier_date=first_date.isoformat(),
                    later_date=second_date.isoformat(),
                    days=(second_date - first_date).days,
                )
            )
    return picked, gaps[:limit_pairs]


def _normalize_label(value: str) -> str:
    out = " ".join(str(value).split()).strip(" .,!?:;\"'")
    return out[:120]
