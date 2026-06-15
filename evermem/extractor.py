"""Claim extraction: turn raw dialogue text into structured claims.

Two extractors behind one interface:
- `LLMExtractor`: any local/remote LLM produces strict JSON claims (rich path),
- `RuleExtractor`: deterministic RU/EN patterns (zero-setup fallback, tests, CI).

No hand-grown intent parsing: the LLM does the open-ended understanding and
the engine stays general; the rule path only covers common self-descriptions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .embeddings import normalize, token_key, tokens
from .llm import LLMUnavailable
from .types import ClaimDraft


@dataclass
class ExtractionResult:
    claims: list[ClaimDraft] = field(default_factory=list)
    topic: str = ""


EXTRACTION_SYSTEM_PROMPT = """You extract long-term memory claims from one message of a dialogue.
Return STRICT JSON only, no prose, in this schema:
{"claims": [{"subject": str, "predicate": str, "value": str, "kind": "fact"|"preference"|"event", "exclusive": bool}], "topic": str}

Rules:
- "subject": who/what the claim is about. Use "user" for the speaker.
- "predicate": short snake_case relation (name, age, location, job, likes, dislikes, has_pet, favorite_language, ...).
- "exclusive": true when a new value REPLACES the old one (name, age, location, job); false when values accumulate (likes, skills, events).
- Only durable facts worth remembering for weeks. Skip greetings, questions, chit-chat.
- Emit kind=event for countable items (projects led, kits, trips, doctor visits, pickups).
- Emit kind=preference for hobbies, interests, skill level, tools and formats.
- Keep values short. Same language as the message.
- "topic": 2-4 words naming what the message is about.
- If nothing is worth remembering: {"claims": [], "topic": ""}.
"""


class RuleExtractor:
    """Deterministic extraction for common RU/EN self-statements."""

    _EXCLUSIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bменя зовут\s+([\w\- ]{2,40})", re.IGNORECASE | re.UNICODE), "name"),
        (re.compile(r"\bmy name is\s+([\w\- ]{2,40})", re.IGNORECASE), "name"),
        (re.compile(r"\bмне\s+(\d{1,3})\s+(?:лет|года|год)\b", re.IGNORECASE | re.UNICODE), "age"),
        (re.compile(r"\bi am\s+(\d{1,3})\s+years old\b", re.IGNORECASE), "age"),
        (re.compile(r"\bя\s+(?:живу|переехал[а]?)\s+в[о]?\s+([\w\- ]{2,40})", re.IGNORECASE | re.UNICODE), "location"),
        (re.compile(r"\bi (?:live|moved to)\s+(?:in\s+)?([\w\- ]{2,40})", re.IGNORECASE), "location"),
        (re.compile(r"\bя\s+работаю\s+([\w\- ]{2,60})", re.IGNORECASE | re.UNICODE), "job"),
        (re.compile(r"\bi work (?:as|at)\s+([\w\- ]{2,60})", re.IGNORECASE), "job"),
    ]

    _ACCUMULATIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bя\s+(?:люблю|обожаю)\s+(.{2,60})", re.IGNORECASE | re.UNICODE), "likes"),
        (re.compile(r"\bмне\s+нравится\s+(.{2,60})", re.IGNORECASE | re.UNICODE), "likes"),
        (re.compile(r"\bi (?:like|love|enjoy)\s+(.{2,60})", re.IGNORECASE), "likes"),
        (re.compile(r"\bя\s+ненавижу\s+(.{2,60})", re.IGNORECASE | re.UNICODE), "dislikes"),
        (re.compile(r"\bi hate\s+(.{2,60})", re.IGNORECASE), "dislikes"),
        (re.compile(r"\bу меня есть\s+(.{2,60})", re.IGNORECASE | re.UNICODE), "has"),
        (re.compile(r"\bi have\s+(?:a|an)\s+(.{2,60})", re.IGNORECASE), "has"),
    ]

    # "мой любимый язык - питон" / "my favorite editor is vim"
    _POSSESSIVE_DASH = re.compile(
        r"\bмо[йяеи]\s+([\w ]{2,40}?)\s*[-:]\s*(.{2,60})", re.IGNORECASE | re.UNICODE
    )
    _POSSESSIVE_IS = re.compile(
        r"\bmy\s+([\w ]{2,40}?)\s+is\s+(.{2,60})", re.IGNORECASE
    )
    # generic "X - Y" definition for non-first-person sentences
    _DEFINITION = re.compile(
        r"^([\w][\w\- ]{1,40}?)\s+(?:-|это|is)\s+(.{3,80})$", re.IGNORECASE | re.UNICODE
    )

    def extract(self, text: str, *, speaker: str = "user") -> ExtractionResult:
        clean = " ".join(str(text).split())
        claims: list[ClaimDraft] = []

        for pattern, predicate in self._EXCLUSIVE_PATTERNS:
            match = pattern.search(clean)
            if match:
                claims.append(
                    ClaimDraft(
                        subject=speaker,
                        predicate=predicate,
                        value=_trim_value(match.group(1)),
                        kind="fact",
                        exclusive=True,
                        confidence=0.85,
                    )
                )

        for pattern, predicate in self._ACCUMULATIVE_PATTERNS:
            match = pattern.search(clean)
            if match:
                claims.append(
                    ClaimDraft(
                        subject=speaker,
                        predicate=predicate,
                        value=_trim_value(match.group(1)),
                        kind="preference",
                        exclusive=False,
                        confidence=0.75,
                    )
                )

        match = self._POSSESSIVE_DASH.search(clean) or self._POSSESSIVE_IS.search(clean)
        if match:
            predicate = "_".join(token_key(tok) for tok in tokens(match.group(1)))
            if predicate:
                claims.append(
                    ClaimDraft(
                        subject=speaker,
                        predicate=predicate,
                        value=_trim_value(match.group(2)),
                        kind="preference",
                        exclusive=True,
                        confidence=0.7,
                    )
                )

        if not claims and "?" not in clean:
            match = self._DEFINITION.match(clean)
            if match:
                claims.append(
                    ClaimDraft(
                        subject=match.group(1),
                        predicate="is",
                        value=_trim_value(match.group(2)),
                        kind="fact",
                        exclusive=False,
                        confidence=0.6,
                    )
                )

        topic = ""
        if claims:
            topic = f"{claims[0].subject} {claims[0].predicate}"
        else:
            toks = tokens(clean)[:4]
            topic = " ".join(toks)
        return ExtractionResult(claims=claims, topic=topic)


class LLMExtractor:
    """LLM-powered extraction with rule-based fallback."""

    def __init__(self, llm, *, fallback: RuleExtractor | None = None) -> None:
        self.llm = llm
        self.fallback = fallback or RuleExtractor()

    def extract(self, text: str, *, speaker: str = "user") -> ExtractionResult:
        try:
            raw = self.llm.complete(EXTRACTION_SYSTEM_PROMPT, str(text))
            result = self._parse(raw, speaker=speaker)
            if result is not None:
                return result
        except LLMUnavailable:
            pass
        return self.fallback.extract(text, speaker=speaker)

    @staticmethod
    def _parse(raw: str, *, speaker: str) -> ExtractionResult | None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        claims: list[ClaimDraft] = []
        for row in data.get("claims", []) or []:
            if not isinstance(row, dict):
                continue
            subject = normalize(str(row.get("subject", "")))
            predicate = normalize(str(row.get("predicate", ""))).replace(" ", "_")
            value = _trim_value(str(row.get("value", "")))
            if not subject or not predicate or not value:
                continue
            if subject in {"speaker", "me", "i", "я"}:
                subject = speaker
            kind = str(row.get("kind", "fact"))
            if kind not in {"fact", "preference", "event"}:
                kind = "fact"
            claims.append(
                ClaimDraft(
                    subject=subject,
                    predicate=predicate,
                    value=value,
                    kind=kind,
                    exclusive=bool(row.get("exclusive", False)),
                    confidence=0.8,
                )
            )
        topic = " ".join(str(data.get("topic", "")).split())[:60]
        return ExtractionResult(claims=claims, topic=topic)


def _trim_value(value: str) -> str:
    out = " ".join(str(value).split()).strip(" .,!;:")
    return out[:80]
