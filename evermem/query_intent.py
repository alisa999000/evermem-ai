"""Lightweight query intent helpers (stdlib only)."""

from __future__ import annotations

import re

_COUNT_MARKERS = (
    r"\bhow many times\b",
    r"\bhow often\b",
    r"\bhow many\b",
    r"\bcount of\b",
    r"\bnumber of times\b",
    r"\bсколько раз\b",
    r"\bколичество раз\b",
)

_COUNT_RE = re.compile("|".join(_COUNT_MARKERS), re.IGNORECASE)

# Strip count boilerplate so aggregate() embeds the activity, not the question frame.
_STRIP_PREFIX = re.compile(
    r"^(?:"
    r"how many times did (?:i|we|you|the user)\s+"
    r"|how often did (?:i|we|you|the user)\s+"
    r"|how many times (?:have|has) (?:i|we|you|the user)\s+"
    r"|сколько раз (?:я|мы|пользователь)\s+"
    r"|how many\s+"
    r")",
    re.IGNORECASE,
)
_STRIP_SUFFIX = re.compile(r"\s*\??\s*$")


def looks_like_count_query(query: str) -> bool:
    return bool(_COUNT_RE.search(query))


def count_topic_from_query(query: str) -> str:
    """Semantic topic for aggregate() after removing count framing."""
    topic = _STRIP_PREFIX.sub("", query.strip())
    topic = _STRIP_SUFFIX.sub("", topic)
    return topic.strip() or query.strip()


_RECOMMEND_RE = re.compile(
    r"\b(?:recommend|suggest|what\s+.+\s+should\s+i|resources?\s+(?:for|where)|"
    r"interesting\s+.+\s+(?:for me|happening)|hotel\s+for|publications?|conferences?|"
    r"посоветуй|порекомендуй|что\s+почитать)\b",
    re.IGNORECASE,
)

_ORDER_RE = re.compile(
    r"\b(?:which\s+.+\s+first|which\s+came\s+first|which\s+did\s+i\s+.+\s+first|"
    r"attend\s+first|got\s+first|take\s+care\s+of\s+first|before\s+the|earlier|"
    r"что\s+раньше|какой\s+.+\s+первым)\b",
    re.IGNORECASE,
)


def looks_like_recommend_query(query: str) -> bool:
    return bool(_RECOMMEND_RE.search(query))


def looks_like_order_query(query: str) -> bool:
    return bool(_ORDER_RE.search(query))


_TEMPORAL_RE = re.compile(
    r"\b(?:how many days|how long|how much time|days between|days before|days after|"
    r"days passed|days did it take|weeks did it take|months did it take|"
    r"before the|after the|since the|until the|between the|"
    r"сколько дней|сколько времени|между)\b",
    re.IGNORECASE,
)

_STRIP_TEMPORAL = re.compile(
    r"^(?:how many days|how long|how much time did it take|how much time|"
    r"how many weeks did it take|days between|days before|days after|"
    r"days passed between|days did it take for me to|"
    r"how many days had passed between|how many days before|how many days after)\s+",
    re.IGNORECASE,
)


def looks_like_temporal_query(query: str) -> bool:
    return bool(_TEMPORAL_RE.search(query))


def temporal_topic_from_query(query: str) -> str:
    topic = _STRIP_TEMPORAL.sub("", query.strip())
    topic = _STRIP_SUFFIX.sub("", topic)
    return topic.strip() or query.strip()


def query_profile(query: str) -> str:
    """Coarse intent bucket used by recall() routing."""
    if looks_like_temporal_query(query):
        return "temporal"
    if looks_like_count_query(query):
        return "count"
    if looks_like_order_query(query):
        return "order"
    if looks_like_recommend_query(query):
        return "recommend"
    return "general"
