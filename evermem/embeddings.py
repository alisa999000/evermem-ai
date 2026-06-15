"""Deterministic, dependency-free text embeddings.

Built from three signals:
- token keys (light RU/EN stemming, handles morphology: "нобелевскую" ~ "нобелевская"),
- char trigrams for fuzzy/typo robustness,
- counter-mode SHA-256 expansion into a fixed-dimension vector.

Uses numpy transparently when available (10-50x faster ingest); falls back to
pure stdlib otherwise. Swappable for real embedding models (Ollama
/api/embeddings) via the same `embed(text) -> list[float]` interface.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

try:  # optional acceleration, not a hard dependency
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

DIM = 256
MAX_TRIGRAMS = 512
TRIGRAM_WEIGHT = 0.5

_RU_SUFFIXES = (
    "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими",
    "ует", "уют", "ила", "ило", "или", "ешь", "ете", "ишь", "ите",
    "ая", "яя", "ое", "ее", "ые", "ие", "ой", "ей", "ую", "юю",
    "ов", "ев", "ам", "ям", "ом", "ем", "ах", "ях", "ут", "ют",
    "ит", "ат", "ят", "ть", "ы", "и", "а", "я", "о", "е", "у", "ю", "ь",
)
_EN_SUFFIXES = ("ing", "edly", "ed", "es", "ly", "s")


def normalize(text: str) -> str:
    raw = str(text).strip().casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", raw)


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", normalize(text), flags=re.UNICODE)


def token_key(token: str) -> str:
    """Light stemmer: cuts one inflection suffix, keeps a stable stem."""
    tok = token.strip().casefold().replace("ё", "е")
    if len(tok) <= 4:
        return tok
    suffixes = _RU_SUFFIXES if re.search(r"[а-я]", tok) else _EN_SUFFIXES
    for suffix in suffixes:
        if tok.endswith(suffix) and len(tok) - len(suffix) >= 4:
            return tok[: len(tok) - len(suffix)]
    return tok


def _hash_bytes(key: str) -> bytes:
    out = bytearray()
    block = 0
    data = key.encode("utf-8", errors="ignore")
    while len(out) < DIM:
        out.extend(hashlib.sha256(data + block.to_bytes(2, "little")).digest())
        block += 1
    return bytes(out[:DIM])


if _np is not None:

    @lru_cache(maxsize=200_000)
    def _hash_vector(key: str):
        raw = _np.frombuffer(_hash_bytes(key), dtype=_np.uint8)
        return raw.astype(_np.float32) / 127.5 - 1.0

else:

    @lru_cache(maxsize=200_000)
    def _hash_vector(key: str):
        return tuple(byte / 127.5 - 1.0 for byte in _hash_bytes(key))


def _feature_keys(text: str) -> tuple[list[str], list[str]]:
    norm_text = normalize(text)
    token_keys = ["t:" + token_key(tok) for tok in tokens(norm_text) if tok]
    compact = re.sub(r"\s", "_", norm_text)
    trigrams = ["g:" + compact[i : i + 3] for i in range(max(0, len(compact) - 2))]
    if len(trigrams) > MAX_TRIGRAMS:
        trigrams = trigrams[:MAX_TRIGRAMS]
    return token_keys, trigrams


def embed(text: str) -> list[float]:
    """Embed text as a normalized sum of token-key and trigram hash vectors."""
    token_keys, trigrams = _feature_keys(text)

    if _np is not None:
        acc = _np.zeros(DIM, dtype=_np.float32)
        for key in token_keys:
            acc += _hash_vector(key)
        for key in trigrams:
            acc += TRIGRAM_WEIGHT * _hash_vector(key)
        norm = float(_np.linalg.norm(acc))
        if norm <= 1e-9:
            return acc.tolist()
        return (acc / norm).tolist()

    vec = [0.0] * DIM
    for key in token_keys:
        hv = _hash_vector(key)
        for i in range(DIM):
            vec[i] += hv[i]
    for key in trigrams:
        hv = _hash_vector(key)
        for i in range(DIM):
            vec[i] += TRIGRAM_WEIGHT * hv[i]
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-9:
        return vec
    return [v / norm for v in vec]


def split_chunks(text: str, *, max_chars: int = 300) -> list[str]:
    """Split text into sentence-aligned chunks of up to `max_chars`.

    Long turns embedded as a single vector get diluted and stop matching
    specific facts inside them; chunk-level embeddings fix that.
    """
    clean = " ".join(str(text).split())
    if len(clean) <= max_chars:
        return [clean] if clean else []
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        while len(sentence) > max_chars:
            head, sentence = sentence[:max_chars], sentence[max_chars:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    if _np is not None:
        va = _np.asarray(a, dtype=_np.float32)
        vb = _np.asarray(b, dtype=_np.float32)
        na = float(_np.linalg.norm(va))
        nb = float(_np.linalg.norm(vb))
        if na <= 1e-9 or nb <= 1e-9:
            return 0.0
        return float(va @ vb) / (na * nb)
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 1e-9 or nb <= 1e-9:
        return 0.0
    return dot / (na * nb)
