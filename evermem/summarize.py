"""Episode summarization: optional LLM, deterministic fallback."""

from __future__ import annotations

from .types import Turn

EPISODE_SUMMARY_SYSTEM = (
    "Summarize this conversation episode in 1-2 short sentences. "
    "Keep names, dates, decisions and numbers. No preamble."
)


def summarize_episode(
    turns: list[Turn],
    *,
    topic: str = "",
    llm=None,
    max_chars: int = 320,
) -> str:
    if not turns:
        return topic.strip()

    lines = [f"{turn.role}: {turn.text}" for turn in turns[-12:]]
    transcript = "\n".join(lines)

    if llm is not None:
        try:
            from .llm import LLMUnavailable

            user = f"Topic: {topic or 'general'}\n\nTranscript:\n{transcript}"
            summary = llm.complete(EPISODE_SUMMARY_SYSTEM, user).strip()
            if summary:
                return summary[:max_chars]
        except Exception:
            pass

    return _rule_summary(turns, topic=topic, max_chars=max_chars)


def _rule_summary(turns: list[Turn], *, topic: str, max_chars: int) -> str:
    parts: list[str] = []
    if topic:
        parts.append(f"Topic: {topic}.")
    for turn in turns[:6]:
        snippet = turn.text.strip().replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:119] + "\u2026"
        parts.append(f"{turn.role}: {snippet}")
    text = " ".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 1] + "\u2026"
    return text
