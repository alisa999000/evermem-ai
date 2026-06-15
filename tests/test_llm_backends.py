import pytest

from evermem.llm import LLMUnavailable


def test_deepseek_requires_api_key(monkeypatch):
    from bench.llm_backends import build_qa_llm

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(LLMUnavailable, match="DEEPSEEK_API_KEY"):
        build_qa_llm(backend="deepseek", model="deepseek-chat", api_key="")


def test_ollama_backend_builds():
    from bench.llm_backends import build_qa_llm, describe_backend

    llm = build_qa_llm(backend="ollama", model="qwen2.5:7b")
    assert hasattr(llm, "complete")
    assert describe_backend("deepseek", "deepseek-chat") == "deepseek/deepseek-chat"
