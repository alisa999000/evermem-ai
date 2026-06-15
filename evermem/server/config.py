"""Server configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ServerConfig:
    db_path: Path
    host: str
    port: int
    chat_model: str
    extract_model: str
    embed_model: str
    ollama_url: str
    default_user: str
    api_key: str
    static_dir: Path

    @classmethod
    def from_env(cls) -> ServerConfig:
        default_db = Path.home() / ".evermem" / "memory.db"
        db = os.environ.get("EVERMEM_DB", str(default_db))
        static = os.environ.get(
            "EVERMEM_STATIC_DIR",
            str(Path(__file__).resolve().parent / "static"),
        )
        return cls(
            db_path=Path(db),
            host=os.environ.get("EVERMEM_HOST", "0.0.0.0"),
            port=int(os.environ.get("EVERMEM_PORT", "8080")),
            chat_model=os.environ.get("EVERMEM_CHAT_MODEL", "qwen2.5:7b"),
            extract_model=os.environ.get("EVERMEM_EXTRACT_MODEL", ""),
            embed_model=os.environ.get("EVERMEM_EMBED_MODEL", ""),
            ollama_url=os.environ.get("EVERMEM_OLLAMA_URL", "http://localhost:11434"),
            default_user=os.environ.get("EVERMEM_USER", "default"),
            api_key=os.environ.get("EVERMEM_API_KEY", "").strip(),
            static_dir=Path(static),
        )
