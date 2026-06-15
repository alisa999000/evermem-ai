"""Demo: eternal memory across sessions, supersede, conflicts, feedback.

Runs fully offline with the rule extractor. If Ollama is up and
EVERMEM_MODEL is set (e.g. qwen2.5:7b), extraction goes through the LLM.

    python demo.py
"""

import os

from evermem import EverMem, OllamaLLM


def main() -> None:
    model = os.environ.get("EVERMEM_MODEL", "").strip()
    llm = OllamaLLM(model) if model else None
    mem = EverMem("demo_memory.db", llm=llm)

    print("=== Session 1: getting to know the user ===")
    for line in [
        "Привет! Меня зовут Алекс, я живу в Минске",
        "я люблю чёрный кофе",
        "мой любимый язык - питон",
    ]:
        report = mem.observe(line, session_id="session-1")
        print(f"  user: {line}")
        print(f"    -> +{report.claims_added} new, {report.claims_reinforced} reinforced")

    print("\n=== Session 2 (next day): life changed ===")
    report = mem.observe("я переехал в Варшаву", session_id="session-2")
    print("  user: я переехал в Варшаву")
    print(f"    -> superseded: {report.claims_superseded}")

    print("\n=== Session 3: a fresh chat asks the LLM about the user ===")
    pack = mem.recall("где живет пользователь и что он любит?", session_id="session-3")
    print(pack.as_prompt())

    print("\n=== Location history (validity windows) ===")
    for claim in mem.history("user", "location"):
        status = "active" if claim.active else "superseded"
        print(f"  {claim.value}: {status}")

    print("\n=== Feedback loop ===")
    touched = mem.feedback(True, session_id="session-3")
    print(f"  reinforced {touched} claims and their retrieval paths")

    print("\n=== Stats ===")
    print(" ", mem.stats())
    mem.close()


if __name__ == "__main__":
    main()
