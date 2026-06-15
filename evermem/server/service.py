"""Shared EverMem instance for the HTTP server."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from pathlib import Path

from ..embed_backends import OllamaEmbedder
from ..llm import OllamaLLM
from ..memory import EverMem
from ..types import MemoryPack
from .config import ServerConfig

CHAT_SYSTEM = (
    "You are a helpful assistant with long-term memory. A [MEMORY] block with "
    "facts and past conversation excerpts may precede the user message. Use it "
    "as your own recollection. Answer concisely. Never mention the [MEMORY] block."
)


def pack_sources(pack: MemoryPack, *, limit: int = 12) -> list[dict]:
    """Structured memory citations for the web UI."""
    out: list[dict] = []
    idx = 1

    for item in pack.claims:
        if idx > limit:
            break
        claim = item.claim
        out.append(
            {
                "id": idx,
                "type": "claim",
                "title": f"{claim.subject} · {claim.predicate}",
                "snippet": claim.value,
                "session_id": claim.source_session or "",
                "score": round(item.score, 3),
            }
        )
        idx += 1

    for turn in pack.history:
        if idx > limit:
            break
        snippet = turn.text.strip()
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        out.append(
            {
                "id": idx,
                "type": "turn",
                "title": f"Диалог · {turn.session_id}",
                "snippet": snippet,
                "session_id": turn.session_id,
            }
        )
        idx += 1

    for episode in pack.episodes:
        if idx > limit:
            break
        snippet = (episode.summary or episode.topic or "").strip()
        if len(snippet) > 220:
            snippet = snippet[:217] + "..."
        out.append(
            {
                "id": idx,
                "type": "episode",
                "title": episode.topic or "Эпизод",
                "snippet": snippet,
                "session_id": episode.session_id,
            }
        )
        idx += 1

    for event in pack.timeline_events:
        if idx > limit:
            break
        out.append(
            {
                "id": idx,
                "type": "event",
                "title": event.date_iso,
                "snippet": event.label,
                "session_id": "",
            }
        )
        idx += 1

    return out


def recall_only_answer(sources: list[dict]) -> str:
    if not sources:
        return "В памяти ничего релевантного не найдено."
    lines = ["Ответ на основе памяти (без LLM):"]
    for src in sources[:6]:
        lines.append(f"- **{src['title']}**: {src['snippet']}")
    return "\n".join(lines)


class MemoryService:
    def __init__(self, config: ServerConfig) -> None:
        self.config = config
        self._lock = threading.Lock()
        self._mem = self._open()

    def _open(self) -> EverMem:
        path = self.config.db_path
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        llm = None
        extract_model = self.config.extract_model or self.config.chat_model
        if extract_model:
            llm = OllamaLLM(extract_model, base_url=self.config.ollama_url)
        embedder = None
        if self.config.embed_model:
            embedder = OllamaEmbedder(
                self.config.embed_model,
                base_url=self.config.ollama_url,
            )
        return EverMem(
            path,
            llm=llm,
            embedder=embedder,
            user_id=self.config.default_user,
        )

    def close(self) -> None:
        with self._lock:
            self._mem.close()

    def stats(self) -> dict:
        with self._lock:
            return self._mem.stats()

    def profile(self) -> list[dict]:
        with self._lock:
            claims = self._mem.profile()
        return [
            {
                "subject": c.subject,
                "predicate": c.predicate,
                "value": c.value,
                "kind": c.kind,
                "trust": round(c.trust, 3),
                "support": c.support,
            }
            for c in claims[:50]
        ]

    def observe(self, text: str, *, session_id: str, role: str = "user") -> dict:
        with self._lock:
            report = self._mem.observe(text, session_id=session_id, role=role)
        return {
            "turn_id": report.turn_id,
            "claims_added": report.claims_added,
            "claims_reinforced": report.claims_reinforced,
            "claims_superseded": report.claims_superseded,
            "events_added": report.events_added,
        }

    def import_file(self, path: Path, *, session_id: str) -> dict:
        with self._lock:
            report = self._mem.observe_file(
                path,
                session_id=session_id,
                extract_claims=bool(self.config.extract_model or self.config.chat_model),
            )
        return {
            "path": report.path,
            "blocks": report.blocks,
            "characters": report.characters,
            "claims_added": report.claims_added,
        }

    def _recall(self, message: str, *, session_id: str) -> tuple[MemoryPack, str, list[dict]]:
        with self._lock:
            pack = self._mem.recall(message, session_id=session_id)
        memory_prompt = pack.as_prompt(budget_chars=6000)
        sources = pack_sources(pack)
        return pack, memory_prompt, sources

    def chat(
        self,
        message: str,
        *,
        session_id: str,
        use_llm: bool = True,
    ) -> dict:
        pack, memory_prompt, sources = self._recall(message, session_id=session_id)
        answer = ""
        llm_error = ""
        if use_llm and self.config.chat_model:
            chat_llm = OllamaLLM(
                self.config.chat_model,
                base_url=self.config.ollama_url,
            )
            prompt = memory_prompt + "\n\nUser: " + message
            try:
                answer = chat_llm.complete(CHAT_SYSTEM, prompt).strip()
            except Exception as exc:  # LLMUnavailable or network
                llm_error = str(exc)
        elif not use_llm:
            answer = recall_only_answer(sources)
        elif memory_prompt:
            answer = memory_prompt

        if answer and use_llm and self.config.chat_model and not llm_error:
            with self._lock:
                self._mem.observe(message, session_id=session_id, role="user")
                self._mem.observe(answer, session_id=session_id, role="assistant")

        return {
            "answer": answer,
            "memory_prompt": memory_prompt,
            "query_profile": pack.query_profile,
            "sources": sources,
            "llm_error": llm_error,
        }

    def chat_stream(
        self,
        message: str,
        *,
        session_id: str,
        use_llm: bool = True,
    ) -> Iterator[dict]:
        pack, memory_prompt, sources = self._recall(message, session_id=session_id)
        yield {
            "type": "meta",
            "memory_prompt": memory_prompt,
            "query_profile": pack.query_profile,
            "sources": sources,
        }

        answer_parts: list[str] = []
        llm_error = ""

        if use_llm and self.config.chat_model:
            chat_llm = OllamaLLM(
                self.config.chat_model,
                base_url=self.config.ollama_url,
            )
            prompt = memory_prompt + "\n\nUser: " + message
            try:
                for token in chat_llm.stream_complete(CHAT_SYSTEM, prompt):
                    answer_parts.append(token)
                    yield {"type": "token", "content": token}
            except Exception as exc:
                llm_error = str(exc)
                yield {"type": "error", "message": llm_error}
        elif not use_llm:
            text = recall_only_answer(sources)
            answer_parts.append(text)
            yield {"type": "token", "content": text}
        else:
            fallback = memory_prompt or "LLM не настроен."
            answer_parts.append(fallback)
            yield {"type": "token", "content": fallback}

        answer = "".join(answer_parts).strip()
        if answer and use_llm and self.config.chat_model and not llm_error:
            with self._lock:
                self._mem.observe(message, session_id=session_id, role="user")
                self._mem.observe(answer, session_id=session_id, role="assistant")

        yield {
            "type": "done",
            "answer": answer,
            "llm_error": llm_error,
        }

    def feedback(self, helpful: bool, *, session_id: str) -> int:
        with self._lock:
            return self._mem.feedback(helpful, session_id=session_id)
