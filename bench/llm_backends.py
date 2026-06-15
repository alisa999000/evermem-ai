"""LLM backends for LongMemEval QA stage (Ollama local or cloud APIs)."""

from __future__ import annotations

import os

from evermem.llm import LLMUnavailable, OllamaLLM, OpenAICompatLLM

DEEPSEEK_DEFAULT_URL = "https://api.deepseek.com/v1"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"


def build_qa_llm(
    *,
    backend: str,
    model: str,
    base_url: str = "",
    api_key: str = "",
    timeout: float = 300.0,
):
    """Return a client with .complete(system, user) for the QA/judge stage."""
    backend = (backend or "ollama").strip().lower()
    model = model.strip()

    if backend == "ollama":
        if not model:
            model = "qwen2.5:7b"
        return OllamaLLM(model, timeout=timeout)

    if backend == "deepseek":
        if not model:
            model = DEEPSEEK_DEFAULT_MODEL
        key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        if not key:
            raise LLMUnavailable(
                "DeepSeek backend needs DEEPSEEK_API_KEY env var or --api-key."
            )
        url = base_url or os.environ.get("DEEPSEEK_BASE_URL", DEEPSEEK_DEFAULT_URL)
        return OpenAICompatLLM(model, base_url=url, api_key=key, timeout=timeout)

    if backend in {"openai", "openai_compat", "openai-compat"}:
        if not model:
            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise LLMUnavailable(
                "OpenAI-compatible backend needs OPENAI_API_KEY or --api-key."
            )
        url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        return OpenAICompatLLM(model, base_url=url, api_key=key, timeout=timeout)

    raise LLMUnavailable(f"Unknown QA backend: {backend!r}. Use ollama, deepseek, or openai.")


def describe_backend(backend: str, model: str) -> str:
    backend = (backend or "ollama").strip().lower()
    if backend == "ollama":
        return f"ollama/{model or 'qwen2.5:7b'}"
    if backend == "deepseek":
        return f"deepseek/{model or DEEPSEEK_DEFAULT_MODEL}"
    return f"{backend}/{model or 'default'}"
