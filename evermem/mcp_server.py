"""MCP server (stdio): plug eternal memory into Cursor, Claude Desktop, any MCP client.

Recommended agent flow:
1. memory_initialize   - session primer (facts, conflicts, stale warnings)
2. memory_recall       - before answering questions about the past
3. memory_remember     - after the user shares durable information
4. memory_feedback     - when recall was helpful or wrong
5. memory_forget       - when a stored fact is wrong or poisoned

Config example (Cursor mcp.json / Claude Desktop):

    {
      "mcpServers": {
        "evermem": {
          "command": "evermem",
          "args": ["mcp"],
          "env": {
            "EVERMEM_DB": "C:/Users/you/.evermem/memory.db",
            "EVERMEM_MODEL": "qwen2.5:7b",
            "EVERMEM_EMBED_MODEL": "nomic-embed-text"
          }
        }
      }
    }

Environment:
- EVERMEM_DB           - SQLite path (default ~/.evermem/memory.db)
- EVERMEM_MODEL        - Ollama model for rich extraction (optional)
- EVERMEM_EMBED_MODEL  - Ollama embedding model for better recall (optional)
- EVERMEM_SESSION      - default session_id when the client does not pass one
- EVERMEM_OLLAMA_URL   - Ollama base url (default http://127.0.0.1:11434)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import __version__
from .ingest import IngestError
from .llm import OllamaLLM
from .memory import EverMem

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "memory_initialize",
        "description": (
            "CALL FIRST at the start of every session. Returns a compressed primer: "
            "known facts, open contradictions and possibly stale items to verify. "
            "Prevents acting on outdated or conflicting memory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "default": "default"},
                "budget_chars": {"type": "integer", "default": 4000},
            },
        },
    },
    {
        "name": "memory_remember",
        "description": (
            "Save dialogue or a durable fact. Call when the user shares preferences, "
            "decisions, personal details or project context worth keeping."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The message or fact to remember."},
                "user_id": {"type": "string", "default": "default"},
                "session_id": {"type": "string", "description": "Conversation/workspace id."},
                "role": {
                    "type": "string",
                    "enum": ["user", "assistant"],
                    "default": "user",
                    "description": "user -> extract facts; assistant -> searchable verbatim only.",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "memory_remember_fact",
        "description": (
            "Write a structured fact directly (subject | predicate = value). "
            "Use to correct or pin a fact without free-text extraction."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "value": {"type": "string"},
                "exclusive": {"type": "boolean", "default": False},
                "user_id": {"type": "string", "default": "default"},
            },
            "required": ["subject", "predicate", "value"],
        },
    },
    {
        "name": "memory_recall",
        "description": (
            "Retrieve relevant memories for a query: facts, contradictions, "
            "past messages and document passages. Call before answering questions "
            "that may depend on prior conversations or uploaded files."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up."},
                "user_id": {"type": "string", "default": "default"},
                "session_id": {"type": "string", "description": "Current conversation id."},
                "budget_chars": {
                    "type": "integer",
                    "default": 4000,
                    "description": "Hard cap on returned text size.",
                },
                "claims_limit": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_aggregate",
        "description": (
            "Count how many past turns or sessions match a topic. "
            "Use for 'how many times did I...' style questions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "user_id": {"type": "string", "default": "default"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_profile",
        "description": "List all active facts about the user with trust and provenance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "default": "default"},
            },
        },
    },
    {
        "name": "memory_feedback",
        "description": (
            "After using memory_recall: reward (helpful=true) or punish (helpful=false) "
            "the facts that were retrieved. Memory learns which paths work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "helpful": {"type": "boolean"},
                "user_id": {"type": "string", "default": "default"},
                "session_id": {"type": "string"},
            },
            "required": ["helpful"],
        },
    },
    {
        "name": "memory_forget",
        "description": (
            "Invalidate a wrong or poisoned fact. By claim_id, or by subject+predicate "
            "(+optional value). History is kept but the fact stops appearing in recall."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "claim_id": {"type": "integer"},
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "value": {"type": "string"},
                "user_id": {"type": "string", "default": "default"},
            },
        },
    },
    {
        "name": "memory_correct",
        "description": (
            "Supersede the current value for subject|predicate with a corrected value. "
            "Preferred over forget+remember when the user fixes a fact."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "predicate": {"type": "string"},
                "new_value": {"type": "string"},
                "user_id": {"type": "string", "default": "default"},
                "session_id": {"type": "string"},
            },
            "required": ["subject", "predicate", "new_value"],
        },
    },
    {
        "name": "memory_consolidate",
        "description": (
            "Summarize closed episodes that lack a summary (sleep-time compute). "
            "Run after long sessions or before shutdown."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "default": "default"},
                "session_id": {"type": "string", "description": "Optional: limit to one session."},
            },
        },
    },
    {
        "name": "memory_import",
        "description": (
            "Ingest a local document (pdf, docx, html, md, txt) into searchable memory. "
            "Path must be absolute or relative to the current working directory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "user_id": {"type": "string", "default": "default"},
                "extract_claims": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        },
    },
]

RESOURCES = [
    {
        "uri": "memory://profile",
        "name": "Active memory profile",
        "description": "All active facts for the default user.",
        "mimeType": "text/plain",
    },
    {
        "uri": "memory://conflicts",
        "name": "Open memory conflicts",
        "description": "Contradictory facts that need user verification.",
        "mimeType": "text/plain",
    },
]


def _default_session() -> str:
    return os.environ.get("EVERMEM_SESSION", "default").strip() or "default"


def _build_memory() -> EverMem:
    db_path = os.environ.get("EVERMEM_DB", "")
    if not db_path:
        default_dir = Path.home() / ".evermem"
        default_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(default_dir / "memory.db")
    model = os.environ.get("EVERMEM_MODEL", "").strip()
    llm = None
    if model:
        llm = OllamaLLM(
            model,
            base_url=os.environ.get("EVERMEM_OLLAMA_URL", "http://127.0.0.1:11434"),
        )
    embedder = None
    embed_model = os.environ.get("EVERMEM_EMBED_MODEL", "").strip()
    if embed_model:
        from .embed_backends import OllamaEmbedder

        embedder = OllamaEmbedder(
            embed_model,
            base_url=os.environ.get("EVERMEM_OLLAMA_URL", "http://127.0.0.1:11434"),
        )
    return EverMem(db_path, llm=llm, embedder=embedder)


class McpServer:
    def __init__(self, memory: EverMem | None = None) -> None:
        self.memory = memory or _build_memory()

    def handle(self, request: dict) -> dict | None:
        method = str(request.get("method", ""))
        request_id = request.get("id")

        if method.startswith("notifications/"):
            return None
        if method == "initialize":
            return self._result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "evermem", "version": __version__},
                },
            )
        if method == "tools/list":
            return self._result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            params = request.get("params", {}) or {}
            name = str(params.get("name", ""))
            args = params.get("arguments", {}) or {}
            try:
                text = self._call_tool(name, args)
            except Exception as exc:
                return self._result(
                    request_id,
                    {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True},
                )
            return self._result(request_id, {"content": [{"type": "text", "text": text}]})
        if method == "resources/list":
            return self._result(request_id, {"resources": RESOURCES})
        if method == "resources/read":
            params = request.get("params", {}) or {}
            uri = str(params.get("uri", ""))
            try:
                text = self._read_resource(uri)
            except Exception as exc:
                return self._result(
                    request_id,
                    {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True},
                )
            return self._result(
                request_id,
                {"contents": [{"uri": uri, "mimeType": "text/plain", "text": text}]},
            )
        if method == "ping":
            return self._result(request_id, {})

        if request_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _read_resource(self, uri: str) -> str:
        if uri == "memory://profile":
            return self._format_profile("default")
        if uri == "memory://conflicts":
            conflicts = self.memory.conflicts()
            if not conflicts:
                return "no open conflicts"
            return "\n".join(
                f"- {hint.subject} | {hint.predicate}: " + " | ".join(hint.values)
                for hint in conflicts
            )
        raise ValueError(f"Unknown resource: {uri}")

    def _format_profile(self, user_id: str) -> str:
        claims = self.memory.profile(user_id=user_id)
        if not claims:
            return "memory is empty"
        lines = []
        for claim in claims:
            prov = f", session {claim.source_session}" if claim.source_session else ""
            lines.append(
                f"- id={claim.id} {claim.subject} | {claim.predicate} = {claim.value}"
                f" (trust {claim.trust:.2f}, seen x{claim.support}, source {claim.source}{prov})"
            )
        return "\n".join(lines)

    def _call_tool(self, name: str, args: dict) -> str:
        user_id = str(args.get("user_id", "default")) or "default"
        session_id = str(args.get("session_id", _default_session())) or _default_session()

        if name == "memory_initialize":
            primer = self.memory.bootstrap(user_id=user_id)
            budget = int(args.get("budget_chars", 4000) or 4000)
            return primer.as_prompt(budget_chars=budget)

        if name == "memory_remember":
            report = self.memory.observe(
                str(args.get("text", "")),
                session_id=session_id,
                user_id=user_id,
                role=str(args.get("role", "user")),
            )
            detail = (
                f"remembered turn {report.turn_id}: +{report.claims_added} new,"
                f" {report.claims_reinforced} reinforced,"
                f" {report.claims_superseded} superseded"
            )
            if report.claims_added == 0 and report.claims_reinforced == 0:
                detail += " (no structured facts extracted; text is still searchable)"
            return detail

        if name == "memory_remember_fact":
            claim = self.memory.remember(
                str(args["subject"]),
                str(args["predicate"]),
                str(args["value"]),
                exclusive=bool(args.get("exclusive", False)),
                user_id=user_id,
            )
            return f"stored fact id={claim.id}: {claim.subject} | {claim.predicate} = {claim.value}"

        if name == "memory_recall":
            pack = self.memory.recall(
                str(args.get("query", "")),
                session_id=session_id,
                user_id=user_id,
                claims_limit=int(args.get("claims_limit", 8) or 8),
            )
            budget = int(args.get("budget_chars", 4000) or 4000)
            return pack.as_prompt(budget_chars=budget)

        if name == "memory_aggregate":
            result = self.memory.aggregate(str(args.get("query", "")), user_id=user_id)
            sessions = ", ".join(result.session_ids[:10])
            suffix = f" Sessions: {sessions}" if sessions else ""
            return (
                f"query={result.query!r}: {result.matching_turns} matching turns"
                f" across {result.matching_sessions} session(s).{suffix}"
            )

        if name == "memory_profile":
            return self._format_profile(user_id)

        if name == "memory_feedback":
            count = self.memory.feedback(
                bool(args.get("helpful")),
                session_id=session_id,
                user_id=user_id,
            )
            return f"feedback applied to {count} claim(s)"

        if name == "memory_forget":
            if args.get("claim_id") is not None:
                ok = self.memory.forget_claim(int(args["claim_id"]))
                return "forgot claim" if ok else "claim not found or already inactive"
            subject = str(args.get("subject", "")).strip()
            predicate = str(args.get("predicate", "")).strip()
            if not subject or not predicate:
                raise ValueError("Provide claim_id or both subject and predicate.")
            value = str(args["value"]).strip() if args.get("value") else None
            count = self.memory.forget(subject, predicate, value=value, user_id=user_id)
            return f"invalidated {count} claim(s)"

        if name == "memory_correct":
            claim = self.memory.correct(
                str(args["subject"]),
                str(args["predicate"]),
                str(args["new_value"]),
                user_id=user_id,
                source_session=session_id,
            )
            return (
                f"corrected: {claim.subject} | {claim.predicate} = {claim.value}"
                f" (new id={claim.id})"
            )

        if name == "memory_consolidate":
            sid = str(args.get("session_id", "")).strip() or None
            count = self.memory.consolidate(user_id=user_id, session_id=sid)
            return f"summarized {count} episode(s)"

        if name == "memory_import":
            try:
                report = self.memory.observe_file(
                    str(args["path"]),
                    user_id=user_id,
                    extract_claims=bool(args.get("extract_claims", False)),
                )
            except IngestError as exc:
                raise ValueError(str(exc)) from exc
            return (
                f"imported {report.path}: {report.blocks} blocks,"
                f" {report.characters} chars, session {report.session_id}"
            )

        raise ValueError(f"Unknown tool: {name}")

    @staticmethod
    def _result(request_id, payload: dict) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def main() -> None:
    server = McpServer()
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    for raw_line in stdin:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = server.handle(request)
        if response is not None:
            stdout.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            stdout.flush()


if __name__ == "__main__":
    main()
