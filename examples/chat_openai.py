"""Memory-augmented chat with any OpenAI-compatible API.

Works with OpenAI, OpenRouter, Groq, vLLM, LM Studio, llama.cpp server - any
endpoint that speaks the /chat/completions protocol.

Run:
    set OPENAI_API_KEY=sk-...          (or your provider key)
    python examples/chat_openai.py

Memory still lives in a local SQLite file; only the chat completion goes to
the API. Swap BASE_URL to point at a local server for a fully offline setup.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evermem import EverMem, LLMUnavailable, OpenAICompatLLM  # noqa: E402

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DB_PATH = Path(__file__).with_name("chat_memory.db")

SYSTEM = (
    "You are a helpful assistant with long-term memory. A [MEMORY] block with "
    "facts and past conversation excerpts may precede the user message. Treat "
    "it as your own recollection; never mention the block itself."
)


def main() -> None:
    llm = OpenAICompatLLM(MODEL, base_url=BASE_URL, api_key=os.environ.get("OPENAI_API_KEY", ""))
    mem = EverMem(DB_PATH, llm=llm)
    print(f"model: {MODEL} via {BASE_URL}; memory: {DB_PATH}. Ctrl+C to quit.")

    session = "cli-chat"
    try:
        while True:
            user_text = input("\nyou > ").strip()
            if not user_text:
                continue
            pack = mem.recall(user_text, session_id=session)
            prompt = pack.as_prompt(budget_chars=4000) + "\n\n" + user_text
            try:
                answer = llm.complete(SYSTEM, prompt)
            except LLMUnavailable as exc:
                print(f"[api error: {exc}]")
                continue
            print(f"bot > {answer}")
            mem.observe(user_text, session_id=session, role="user")
            mem.observe(answer, session_id=session, role="assistant")
    except (KeyboardInterrupt, EOFError):
        print("\nbye - memory saved.")
    finally:
        mem.close()


if __name__ == "__main__":
    main()
