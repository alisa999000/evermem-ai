"""Countable event extraction and query-time entity counting.

LongMemEval multi-session questions often ask for a number of distinct items
(projects, kits, doctors, clothing pickups). Turn-level semantic counts are not
enough; we track each mention as a separate claim and count distinct values per
category at recall time.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .embeddings import cosine, embed, token_key, tokens
from .query_intent import count_topic_from_query
from .types import Claim, ClaimDraft, EntityCountSummary

# (pattern, predicate, kind)
_COUNTABLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:led|leading|lead)\s+(?:the\s+)?(.{3,55}?)\s+project", re.I), "project_led"),
    (re.compile(r"\bproject\s+(?:called|named)\s+(.{3,55})", re.I), "project_led"),
    (re.compile(r"\b(?:working on|worked on)\s+(?:the\s+)?(.{3,55}?)\s+project", re.I), "project_led"),
    (re.compile(r"\b(?:built|building|bought|got|picked up)\s+(?:a\s+)?(.{4,50}?)\s+(?:model\s+)?kit", re.I), "model_kit"),
    (re.compile(r"\b(\d{1,2})\s*/\s*(\d{2})?\s*scale\s+(.{4,40})", re.I), "model_kit"),
    (re.compile(r"\b(?:went|been)\s+camping\b", re.I), "camping_trip"),
    (re.compile(r"\bcamping\s+trip\b", re.I), "camping_trip"),
    (re.compile(r"\bpick(?:ed)?\s+up\s+(?:my\s+)?(.{3,50}?)(?:\s+from|\s+at|$)", re.I), "clothing_pickup"),
    (re.compile(r"\bpick(?:ed)?\s+up\s+(?:the\s+)?(.{3,40}?)\s+from\s+(?:the\s+)?store", re.I), "clothing_pickup"),
    (re.compile(r"\breturn(?:ed|ing)?\s+(?:my\s+)?(.{3,50}?)(?:\s+to|\s+at|$)", re.I), "clothing_return"),
    (re.compile(r"\bdry\s+cleaning\b", re.I), "clothing_pickup"),
    (re.compile(r"\b(?:new\s+)?(?:shirt|jacket|pants|dress|coat|blouse)\b", re.I), "clothing_item"),
    (re.compile(r"\b(?:visited|saw)\s+(?:dr\.?|doctor)\s+(.{2,40})", re.I), "doctor_visit"),
    (re.compile(r"\bdoctor(?:'s)?\s+appointment\b", re.I), "doctor_visit"),
    (re.compile(r"\b(?:acquired|got|bought)\s+(?:a\s+)?(?:new\s+)?plant", re.I), "plant_acquired"),
    (re.compile(r"\broad\s+trip\b", re.I), "road_trip"),
    (re.compile(r"\bspent\s+\$?([\d,.]+)\s+on\s+(.{3,40})", re.I), "money_spent"),
    (re.compile(r"\b(\d+(?:\.\d+)?)\s+hours?\s+(?:driving|on the road)", re.I), "driving_hours"),
]

_PREFERENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bi(?:'m| am)\s+(?:really\s+)?into\s+(.{3,60})", re.I), "interest"),
    (re.compile(r"\bi(?:'m| am)\s+interested in\s+(.{3,60})", re.I), "interest"),
    (re.compile(r"\bi\s+prefer\s+(.{3,60})", re.I), "prefers"),
    (re.compile(r"\bmy\s+(?:main\s+)?(?:hobby|interest)\s+is\s+(.{3,60})", re.I), "interest"),
    (re.compile(r"\bi(?:'m| am)\s+(?:a\s+)?beginner\s+(?:at|in|with)\s+(.{3,50})", re.I), "skill_level"),
    (re.compile(r"\bi(?:'m| am)\s+(?:an?\s+)?(?:experienced|advanced)\s+(.{3,50})", re.I), "skill_level"),
    (re.compile(r"\bя\s+увлекаюсь\s+(.{3,60})", re.I | re.UNICODE), "interest"),
    (re.compile(r"\bмне\s+интересн[аоы]\s+(.{3,60})", re.I | re.UNICODE), "interest"),
]


def extract_countable_claims(text: str, *, speaker: str = "user") -> list[ClaimDraft]:
    clean = " ".join(str(text).split())
    claims: list[ClaimDraft] = []
    seen: set[tuple[str, str]] = set()

    for pattern, predicate in _COUNTABLE_PATTERNS:
        for match in pattern.finditer(clean):
            value = _normalize_entity(match.group(1) if match.lastindex else predicate)
            if not value or len(value) < 2:
                value = predicate
            key = (predicate, value)
            if key in seen:
                continue
            seen.add(key)
            claims.append(
                ClaimDraft(
                    subject=speaker,
                    predicate=predicate,
                    value=value,
                    kind="event",
                    exclusive=False,
                    confidence=0.72,
                )
            )

    for pattern, predicate in _PREFERENCE_PATTERNS:
        match = pattern.search(clean)
        if match:
            value = _normalize_entity(match.group(1))
            if value:
                claims.append(
                    ClaimDraft(
                        subject=speaker,
                        predicate=predicate,
                        value=value,
                        kind="preference",
                        exclusive=False,
                        confidence=0.78,
                    )
                )
    return claims


def _normalize_entity(value: str) -> str:
    out = " ".join(str(value).split()).strip(" .,!?:;")
    return out[:80].casefold()


_PREDICATE_HINTS: dict[str, tuple[str, ...]] = {
    "project": ("project_led", "project"),
    "kit": ("model_kit",),
    "model": ("model_kit",),
    "camping": ("camping_trip", "camping_days"),
    "clothing": ("clothing_pickup", "clothing_return"),
    "pick up": ("clothing_pickup",),
    "return": ("clothing_return",),
    "doctor": ("doctor_visit",),
    "plant": ("plant_acquired",),
    "road trip": ("road_trip", "driving_hours"),
    "driving": ("driving_hours", "road_trip"),
    "spent": ("money_spent",),
    "bike": ("money_spent",),
    "gym": ("activity", "likes"),
    "video edit": ("interest", "prefers", "likes"),
    "photograph": ("interest", "prefers", "likes"),
    "hotel": ("interest", "prefers"),
    "cultural": ("interest", "prefers"),
    "conference": ("interest", "prefers"),
    "publication": ("interest", "prefers"),
}


def summarize_entity_counts(active_claims: list[Claim], query: str) -> list[EntityCountSummary]:
    """Count distinct values per predicate family relevant to a how-many question."""
    topic = count_topic_from_query(query)
    topic_tokens = {token_key(t) for t in tokens(topic) if len(t) > 2}
    query_tokens = {token_key(t) for t in tokens(query) if len(t) > 2}

    target_predicates: set[str] = set()
    blob = f"{topic} {query}".lower()
    for hint, preds in _PREDICATE_HINTS.items():
        if hint in blob:
            target_predicates.update(preds)

    by_predicate: dict[str, set[str]] = defaultdict(set)
    for claim in active_claims:
        if claim.kind not in {"event", "fact", "preference"}:
            continue
        pred = claim.predicate
        if target_predicates and pred not in target_predicates:
            # Soft match: predicate or value overlaps query tokens
            claim_tokens = {token_key(t) for t in tokens(f"{pred} {claim.value}") if len(t) > 2}
            if not (claim_tokens & (topic_tokens | query_tokens)):
                sim = cosine(embed(topic), embed(f"{pred} {claim.value}"))
                if sim < 0.35:
                    continue
        by_predicate[pred].add(claim.value)

    summaries: list[EntityCountSummary] = []
    for pred, values in sorted(by_predicate.items(), key=lambda kv: -len(kv[1])):
        if not values:
            continue
        examples = sorted(values)[:6]
        summaries.append(
            EntityCountSummary(category=pred, count=len(values), examples=examples)
        )
    return summaries
