"""Minimal LLM clients (stdlib-only HTTP): Ollama and OpenAI-compatible.

The memory engine never *requires* an LLM - extraction falls back to rules -
but with a local model (Ollama) claim extraction becomes far richer.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator


class LLMUnavailable(RuntimeError):
    pass


class OllamaLLM:
    def __init__(
        self,
        model: str = "qwen2.5:7b",
        *,
        base_url: str = "http://127.0.0.1:11434",
        timeout: float = 120.0,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "options": {"temperature": self.temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = _post_json(f"{self.base_url}/api/chat", payload, timeout=self.timeout)
        message = data.get("message", {})
        return str(message.get("content", ""))

    def stream_complete(self, system: str, user: str) -> Iterator[str]:
        payload = {
            "model": self.model,
            "stream": True,
            "options": {"temperature": self.temperature},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                for raw in response:
                    line = raw.decode("utf-8").strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    chunk = str(data.get("message", {}).get("content", ""))
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(f"LLM stream to {self.base_url}/api/chat failed: {exc}") from exc


class OpenAICompatLLM:
    """Works with OpenAI, OpenRouter, vLLM, LM Studio - anything /v1-compatible."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        timeout: float = 120.0,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = _post_json(
            f"{self.base_url}/chat/completions", payload, timeout=self.timeout, headers=headers
        )
        choices = data.get("choices", [])
        if not choices:
            raise LLMUnavailable("Empty response from LLM.")
        return str(choices[0].get("message", {}).get("content", ""))


def _post_json(url: str, payload: dict, *, timeout: float, headers: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(f"LLM call to {url} failed: {exc}") from exc
