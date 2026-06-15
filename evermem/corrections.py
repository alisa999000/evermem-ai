"""Auto-correction and quantity-fact lifecycle.

User corrections ("9, not 10") must supersede stale counts without manual
`correct`. Purchase/quantity claims are exclusive and grouped by entity topic.
Assistant echo replies must not be stored as ground-truth purchases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .embeddings import token_key, tokens
from .types import ClaimDraft

PURCHASE_PREDICATES: frozenset[str] = frozenset(
    {
        "has_bought",
        "bought",
        "purchased",
        "acquired",
        "ordered",
        "purchase_count",
        "item_count",
    }
)

PREDICATE_ALIASES: dict[str, str] = {
    "bought": "has_bought",
    "purchased": "has_bought",
    "acquired": "has_bought",
    "ordered": "has_bought",
    "purchase_count": "has_bought",
    "item_count": "has_bought",
}

_CORRECTION_MARKER = re.compile(
    r"перепутал|ошибся|ошибка|на\s+самом\s+деле|исправ|"
    r"wrong|actually|i\s+meant|correction|not\s+\d|"
    r"а\s+не\s+\d|\d+\s+а\s+не",
    re.IGNORECASE | re.UNICODE,
)

# new quantity first, old second — "9 а не 10", "9 мячей а не 10", "9 balls not 10"
_QTY_NEW_NOT_OLD = re.compile(
    r"(\d{1,4})(?:\s+\S+){0,8}?\s*(?:а\s+не|not)\s*(\d{1,4})\b",
    re.IGNORECASE | re.UNICODE,
)

# old first — "не 10, а 9", "not 10 but 9"
_QTY_OLD_NOT_NEW = re.compile(
    r"не\s*(\d{1,4})\s*[,]?\s*а\s*(\d{1,4})|"
    r"not\s*(\d{1,4})\s*(?:,|but)\s*(\d{1,4})",
    re.IGNORECASE | re.UNICODE,
)

_PURCHASE_IN_TEXT = re.compile(
    r"(?:^|\s)(?:я\s+)?(?:купил[а]?|приобрел[а]?|заказал[а]?|bought|purchased|ordered)\s+"
    r"(\d{1,4})\s+(.{2,80}?)(?:\s+а\s+не|\s+not|$|[,.!?])",
    re.IGNORECASE | re.UNICODE,
)

_QUANTITY_IN_VALUE = re.compile(r"\b(\d{1,4})\b")

_ENTITY_STOP = frozenset(
    {
        "the",
        "a",
        "an",
        "и",
        "в",
        "на",
        "я",
        "вы",
        "user",
        "шт",
        "штук",
        "штуки",
        "piece",
        "pieces",
    }
)

_ASSISTANT_ECHO = re.compile(
    r"^(?:понял|understood|you bought|вы купил|вы купили|it was|that was|correct)",
    re.IGNORECASE | re.UNICODE,
)


@dataclass
class CorrectionHint:
    is_correction: bool = False
    new_quantity: int | None = None
    old_quantity: int | None = None
    entity_tokens: set[str] = field(default_factory=set)
    canonical_value: str = ""


def detect_correction(text: str) -> CorrectionHint:
    clean = " ".join(str(text).split())
    if not clean:
        return CorrectionHint()

    is_corr = bool(_CORRECTION_MARKER.search(clean))
    new_q = old_q = None
    entity: set[str] = set()

    match = _QTY_NEW_NOT_OLD.search(clean)
    if match:
        new_q, old_q = int(match.group(1)), int(match.group(2))
        is_corr = True
    else:
        match = _QTY_OLD_NOT_NEW.search(clean)
        if match:
            if match.group(1) and match.group(2):
                old_q, new_q = int(match.group(1)), int(match.group(2))
            else:
                old_q, new_q = int(match.group(3)), int(match.group(4))
            is_corr = True

    purchase = _PURCHASE_IN_TEXT.search(clean)
    if purchase:
        qty = int(purchase.group(1))
        entity = entity_tokens_from_phrase(purchase.group(2))
        if new_q is None:
            new_q = qty
        if not is_corr and old_q is not None:
            is_corr = True

    if not entity:
        entity = entity_tokens_from_phrase(clean)

    canonical = ""
    if new_q is not None and entity:
        canonical = canonical_quantity_value(new_q, entity)
    elif new_q is not None:
        canonical = str(new_q)

    return CorrectionHint(
        is_correction=is_corr,
        new_quantity=new_q,
        old_quantity=old_q,
        entity_tokens=entity,
        canonical_value=canonical,
    )


def entity_tokens_from_phrase(text: str) -> set[str]:
    out: set[str] = set()
    for tok in tokens(text):
        key = token_key(tok)
        if len(key) < 3 or key in _ENTITY_STOP:
            continue
        out.add(key)
        if len(key) > 5:
            out.add(key[:5])
    return out


def canonical_quantity_value(quantity: int, entity_tokens: set[str]) -> str:
    if not entity_tokens:
        return str(quantity)
    # Prefer the longest token as the head noun stem.
    head = max(entity_tokens, key=len)
    return f"{quantity} {head}"


def parse_quantity_value(value: str) -> tuple[int | None, set[str]]:
    match = _QUANTITY_IN_VALUE.search(value)
    qty = int(match.group(1)) if match else None
    rest = value[match.end() :].strip() if match else value
    entity = entity_tokens_from_phrase(rest) or entity_tokens_from_phrase(value)
    return qty, entity


def entities_overlap(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return True
    if a & b:
        return True
    expanded_a = _expand_entity_tokens(a)
    expanded_b = _expand_entity_tokens(b)
    if expanded_a & expanded_b:
        return True
    for x in expanded_a:
        for y in expanded_b:
            if x.startswith(y) or y.startswith(x):
                return True
    return False


def _expand_entity_tokens(tokens: set[str]) -> set[str]:
    out = set(tokens)
    for tok in tokens:
        if tok.startswith("мяч") or tok.startswith("ball") or "basket" in tok:
            out.update({"ball", "balls", "basketball", "basketballs", "мяч", "мячей", "баскет"})
    return out


def is_quantity_claim(draft: ClaimDraft) -> bool:
    pred = normalize_predicate(draft.predicate)
    if pred in PURCHASE_PREDICATES:
        return True
    return bool(_QUANTITY_IN_VALUE.search(draft.value))


def normalize_predicate(predicate: str) -> str:
    key = predicate.strip().casefold().replace(" ", "_")
    return PREDICATE_ALIASES.get(key, key)


def normalize_draft(draft: ClaimDraft) -> ClaimDraft:
    draft.predicate = normalize_predicate(draft.predicate)
    if is_quantity_claim(draft):
        draft.exclusive = True
        qty, entity = parse_quantity_value(draft.value)
        if qty is not None and entity:
            draft.value = canonical_quantity_value(qty, entity)
    return draft


def dedupe_quantity_drafts(drafts: list[ClaimDraft]) -> list[ClaimDraft]:
    """Keep one has_bought draft per (subject, quantity, entity topic)."""
    best: dict[tuple[str, str, int], ClaimDraft] = {}
    rest: list[ClaimDraft] = []
    for draft in drafts:
        if not is_quantity_claim(draft):
            rest.append(draft)
            continue
        qty, entity = parse_quantity_value(draft.value)
        if qty is None:
            rest.append(draft)
            continue
        key = (draft.subject.casefold(), draft.predicate, qty)
        prev = best.get(key)
        if prev is None or len(draft.value) > len(prev.value):
            best[key] = draft
    return rest + list(best.values())


def filter_assistant_drafts(drafts: list[ClaimDraft], text: str) -> list[ClaimDraft]:
    """Drop purchase/count claims echoed from assistant replies."""
    if not drafts:
        return drafts
    echo = bool(_ASSISTANT_ECHO.search(text.strip()))
    out: list[ClaimDraft] = []
    for draft in drafts:
        if draft.predicate in PURCHASE_PREDICATES or is_quantity_claim(draft):
            if echo or draft.predicate in PURCHASE_PREDICATES:
                continue
        out.append(draft)
    return out


def apply_correction_to_store(
    store,
    user_id: str,
    hint: CorrectionHint,
    *,
    now: float | None = None,
) -> int:
    """Invalidate stale quantity claims for the same entity topic."""
    if not hint.is_correction:
        return 0
    invalidated = 0
    for claim in store.active_claims(user_id):
        if claim.predicate not in PURCHASE_PREDICATES:
            continue
        qty, entity = parse_quantity_value(claim.value)
        if hint.old_quantity is not None and qty == hint.old_quantity:
            if store.invalidate_claim(claim.id, now=now):
                invalidated += 1
            continue
        if hint.new_quantity is not None and qty == hint.new_quantity:
            continue
        if hint.entity_tokens and entities_overlap(hint.entity_tokens, entity):
            if store.invalidate_claim(claim.id, now=now):
                invalidated += 1
    return invalidated


def prepare_observe_drafts(
    text: str,
    role: str,
    drafts: list[ClaimDraft],
    *,
    store,
    user_id: str,
    now: float | None = None,
) -> list[ClaimDraft]:
    """Normalize, dedupe, and apply correction supersede before upsert."""
    if role == "assistant":
        return filter_assistant_drafts(drafts, text)

    hint = detect_correction(text)
    normalized = [normalize_draft(d) for d in drafts]

    if hint.is_correction and hint.new_quantity is not None:
        apply_correction_to_store(store, user_id, hint, now=now)
        has_bought = any(d.predicate in PURCHASE_PREDICATES for d in normalized)
        if not has_bought:
            normalized.append(
                ClaimDraft(
                    subject="user",
                    predicate="has_bought",
                    value=hint.canonical_value or str(hint.new_quantity),
                    kind="fact",
                    exclusive=True,
                    confidence=0.88,
                )
            )

    for draft in normalized:
        if is_quantity_claim(draft):
            draft.exclusive = True

    return dedupe_quantity_drafts(normalized)


def extract_rule_purchase_claims(text: str, *, speaker: str = "user") -> list[ClaimDraft]:
    """Deterministic purchase extraction (RU/EN) for zero-LLM setups."""
    clean = " ".join(str(text).split())
    claims: list[ClaimDraft] = []
    for match in _PURCHASE_IN_TEXT.finditer(clean):
        qty = int(match.group(1))
        entity = entity_tokens_from_phrase(match.group(2))
        value = canonical_quantity_value(qty, entity) if entity else f"{qty} {match.group(2).strip()}"
        claims.append(
            ClaimDraft(
                subject=speaker,
                predicate="has_bought",
                value=value[:80],
                kind="fact",
                exclusive=True,
                confidence=0.82,
            )
        )
    return claims
