"""Pluggable embedding backends.

The default backend is the dependency-free hash embedder in `embeddings.py`.
For higher retrieval quality, plug a real model - any callable
`(text: str) -> list[float]` works:

    from evermem import EverMem, OllamaEmbedder
    mem = EverMem("memory.db", embedder=OllamaEmbedder("nomic-embed-text"))

Embeddings of any dimension are supported; vectors are stored as float32
blobs and compared by cosine.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .llm import LLMUnavailable


class OllamaEmbedder:
    """Embeddings via a local Ollama server (CPU-friendly, fully offline)."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 300.0,
        cache_size: int = 100_000,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._cache: dict[str, list[float]] = {}
        self._cache_size = max(0, cache_size)

    def __call__(self, text: str) -> list[float]:
        key = str(text).strip()
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        vec = self._embed_remote([key])[0]
        self._cache_put(key, vec)
        return vec

    def prewarm(self, texts: list[str], *, batch_size: int = 64) -> int:
        """Embed many texts in batched requests, filling the cache.

        Dramatically faster than per-text calls (one HTTP round-trip per
        batch). Returns the number of newly embedded texts.
        """
        seen: set[str] = set()
        missing: list[str] = []
        for text in texts:
            key = str(text).strip()
            if key and key not in self._cache and key not in seen:
                seen.add(key)
                missing.append(key)
        for start in range(0, len(missing), max(1, batch_size)):
            chunk = missing[start : start + batch_size]
            try:
                vectors = self._embed_remote(chunk)
            except LLMUnavailable:
                # Retry once in small sub-batches (CPU contention can make a
                # big batch exceed the timeout while another model generates).
                vectors = []
                for tiny_start in range(0, len(chunk), 8):
                    tiny = chunk[tiny_start : tiny_start + 8]
                    vectors.extend(self._embed_remote(tiny))
            for key, vec in zip(chunk, vectors):
                self._cache_put(key, vec)
        return len(missing)

    def clear_cache(self) -> None:
        """Drop cached vectors (frees memory; useful between independent corpora)."""
        self._cache.clear()

    def _cache_put(self, key: str, vec: list[float]) -> None:
        if self._cache_size and len(self._cache) < self._cache_size:
            self._cache[key] = vec

    def _embed_remote(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": texts}
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/embed", data=body, method="POST"
        )
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(f"Ollama embed call failed: {exc}") from exc
        embeddings = data.get("embeddings") or []
        if len(embeddings) != len(texts) or any(not e for e in embeddings):
            raise LLMUnavailable("Ollama returned empty/mismatched embeddings.")
        return [[float(x) for x in vec] for vec in embeddings]
