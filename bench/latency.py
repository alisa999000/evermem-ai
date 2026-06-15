"""Latency micro-benchmark: observe and recall timings on a growing store.

Usage:
    python bench/latency.py                  # hash embeddings (zero-dep mode)
    python bench/latency.py --turns 5000
    python bench/latency.py --embed-model nomic-embed-text   # Ollama embeddings

Cloud memory services answer recall in seconds (Zep ~4s, Mem0 ~7s per
independent 2026 reviews). This script shows what staying local buys.
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evermem import EverMem  # noqa: E402

TOPICS = [
    "я люблю {x}",
    "мой любимый цвет - {x}",
    "вчера я ходил в {x}",
    "надо не забыть про {x}",
    "мы обсуждали проект {x}",
    "I really enjoy {x}",
    "yesterday I visited {x}",
    "remember to buy {x}",
]
WORDS = [
    "кофе", "горы", "минск", "варшаву", "книги", "бег", "шахматы", "гитару",
    "the gym", "tokyo", "a laptop", "groceries", "the report", "chess",
]
QUERIES = [
    "что я люблю?",
    "куда я ходил вчера?",
    "what do I enjoy?",
    "что надо купить?",
    "какой мой любимый цвет?",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=int, default=2000)
    parser.add_argument("--queries", type=int, default=50)
    parser.add_argument("--embed-model", default="")
    args = parser.parse_args()

    embedder = None
    if args.embed_model:
        from evermem import OllamaEmbedder

        embedder = OllamaEmbedder(args.embed_model)

    rng = random.Random(42)
    mem = EverMem(embedder=embedder)

    observe_times: list[float] = []
    for i in range(args.turns):
        text = rng.choice(TOPICS).format(x=rng.choice(WORDS)) + f" #{i}"
        start = time.perf_counter()
        mem.observe(text, session_id=f"s{i % 50}")
        observe_times.append((time.perf_counter() - start) * 1000)

    recall_times: list[float] = []
    for i in range(args.queries):
        query = rng.choice(QUERIES)
        start = time.perf_counter()
        mem.recall(query, session_id="bench-query")
        recall_times.append((time.perf_counter() - start) * 1000)

    def pct(values: list[float], q: float) -> float:
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    mode = args.embed_model or "hash (zero-dep)"
    print(f"embeddings: {mode}; store size: {args.turns} turns")
    print(
        f"observe : mean {statistics.mean(observe_times):7.2f} ms"
        f"  p50 {pct(observe_times, 0.50):7.2f}  p95 {pct(observe_times, 0.95):7.2f}"
    )
    print(
        f"recall  : mean {statistics.mean(recall_times):7.2f} ms"
        f"  p50 {pct(recall_times, 0.50):7.2f}  p95 {pct(recall_times, 0.95):7.2f}"
        f"  (over {args.queries} queries against {args.turns} stored turns)"
    )
    mem.close()


if __name__ == "__main__":
    main()
