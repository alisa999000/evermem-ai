"""LangChain adapter for evermem.

Install:
    pip install "evermem-ai[langchain]"

Example:
    from evermem import EverMem
    from evermem.integrations.langchain import EverMemChatHistory

    mem = EverMem("memory.db")
    history = EverMemChatHistory(mem, session_id="chat-1")
    history.add_user_message("I live in Minsk")
    pack = mem.recall("where do I live?", session_id="chat-1")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ..memory import EverMem

try:
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
except ImportError as exc:
    raise ImportError(
        'LangChain support requires: pip install "evermem-ai[langchain]"'
    ) from exc


class EverMemChatHistory(BaseChatMessageHistory):
    """Chat message history backed by evermem turns + claims."""

    def __init__(
        self,
        memory: EverMem,
        *,
        session_id: str = "default",
        user_id: str | None = None,
    ) -> None:
        self._mem = memory
        self.session_id = session_id
        self.user_id = user_id

    @property
    def messages(self) -> list[BaseMessage]:
        turns = self._mem.store.recent_turns(self.session_id, limit=50)
        out: list[BaseMessage] = []
        for turn in turns:
            if turn.role == "assistant":
                out.append(AIMessage(content=turn.text))
            else:
                out.append(HumanMessage(content=turn.text))
        return out

    def add_message(self, message: BaseMessage) -> None:
        role = "assistant" if message.type == "ai" else "user"
        self._mem.observe(
            str(message.content),
            session_id=self.session_id,
            user_id=self.user_id,
            role=role,
        )

    def add_user_message(self, text: str) -> None:
        self._mem.observe(text, session_id=self.session_id, user_id=self.user_id, role="user")

    def add_ai_message(self, text: str) -> None:
        self._mem.observe(text, session_id=self.session_id, user_id=self.user_id, role="assistant")

    def clear(self) -> None:
        pass  # evermem has no session-scoped clear in core; use mem.purge() if needed


class EverMemRetriever:
    """Return a MemoryPack prompt string for a query (Runnable-friendly)."""

    def __init__(
        self,
        memory: EverMem,
        *,
        session_id: str = "default",
        user_id: str | None = None,
        budget_chars: int = 4000,
    ) -> None:
        self._mem = memory
        self.session_id = session_id
        self.user_id = user_id
        self.budget_chars = budget_chars

    def invoke(self, query: str) -> str:
        pack = self._mem.recall(
            query,
            session_id=self.session_id,
            user_id=self.user_id,
        )
        return pack.as_prompt(budget_chars=self.budget_chars)

    def batch(self, queries: Sequence[str]) -> list[str]:
        return [self.invoke(query) for query in queries]
