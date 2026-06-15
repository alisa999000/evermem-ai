"""Smoke-test DeepSeek API connectivity for the benchmark harness.

Usage:
    set DEEPSEEK_API_KEY=sk-...
    python bench/test_deepseek.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_backends import build_qa_llm


def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not set.")
        print("Get a key at https://platform.deepseek.com and run:")
        print('  set DEEPSEEK_API_KEY=sk-...')
        print("  python bench/test_deepseek.py")
        return 1
    llm = build_qa_llm(backend="deepseek", model="deepseek-chat")
    answer = llm.complete(
        "Reply with exactly one word.",
        "What is 2+2? Answer with the digit only.",
    )
    print("deepseek-chat OK:", answer.strip()[:80])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
