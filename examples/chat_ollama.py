"""Memory-augmented chat with a local Ollama model.

Run:
    ollama pull qwen2.5:7b
    ollama pull nomic-embed-text   # optional, better recall
    python examples/chat_ollama.py

Everything stays on your machine: the model, the embeddings and the memory
file (chat_memory.db next to this script). Restart the script and it still
remembers you.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evermem import EverMem, LLMUnavailable, OllamaEmbedder, OllamaLLM  # noqa: E402

CHAT_MODEL = "qwen2.5:7b"
EMBED_MODEL = "nomic-embed-text"  # set to "" to run with zero-dep hash embeddings
DB_PATH = Path(__file__).with_name("chat_memory.db")

SYSTEM = (
    "You are a helpful assistant with long-term memory. A [MEMORY] block with "
    "facts and past conversation excerpts may precede the user message. Treat "
    "it as your own recollection; never mention the block itself."
)


def main() -> None:
    llm = OllamaLLM(CHAT_MODEL)
    embedder = OllamaEmbedder(EMBED_MODEL) if EMBED_MODEL else None
    mem = EverMem(DB_PATH, llm=llm, embedder=embedder)
    print(f"memory: {DB_PATH} ({mem.stats()['turns']} turns so far). Ctrl+C to quit.")

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
                print(f"[ollama error: {exc}]")
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
