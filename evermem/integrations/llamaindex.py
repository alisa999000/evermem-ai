"""LlamaIndex memory block for evermem.

Install:
    pip install "evermem-ai[llamaindex]"

Example:
    from evermem import EverMem
    from evermem.integrations.llamaindex import EverMemMemoryBlock

    mem = EverMem("memory.db")
    block = EverMemMemoryBlock(mem, session_id="chat-1")
    context = block.get("what did we decide about pricing?")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..memory import EverMem

def _require_llamaindex() -> None:
    try:
        import llama_index.core  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            'LlamaIndex support requires: pip install "evermem-ai[llamaindex]"'
        ) from exc


class EverMemMemoryBlock:
    """Inject evermem recall packs into LlamaIndex agents (get/put interface)."""

    def __init__(
        self,
        memory: EverMem,
        *,
        session_id: str = "default",
        user_id: str | None = None,
        budget_chars: int = 4000,
        name: str = "evermem",
    ) -> None:
        _require_llamaindex()
        self.name = name
        self._mem = memory
        self.session_id = session_id
        self.user_id = user_id
        self.budget_chars = budget_chars

    def get(self, input: str | None = None, **kwargs: Any) -> str:
        query = input or kwargs.get("query") or ""
        if not query.strip():
            primer = self._mem.bootstrap(user_id=self.user_id)
            return primer.as_prompt(budget_chars=self.budget_chars)
        pack = self._mem.recall(query, session_id=self.session_id, user_id=self.user_id)
        return pack.as_prompt(budget_chars=self.budget_chars)

    def put(self, message: dict[str, Any] | str) -> None:
        if isinstance(message, str):
            text, role = message, "user"
        else:
            text = str(message.get("content") or message.get("text") or "")
            role = str(message.get("role") or "user")
        if text.strip():
            self._mem.observe(text, session_id=self.session_id, user_id=self.user_id, role=role)
