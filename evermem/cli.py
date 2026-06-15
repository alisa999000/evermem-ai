"""evermem command line interface.

Examples:
    evermem remember "My name is Alex, I live in Minsk"
    evermem recall "where does the user live?"
    evermem import contract.pdf notes.md
    evermem profile
    evermem stats
    evermem mcp

The default database lives at ~/.evermem/memory.db (override with --db or
the EVERMEM_DB environment variable). Add --model to use a local Ollama
model for richer fact extraction.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .ingest import IngestError
from .memory import EverMem

DEFAULT_DB = os.environ.get("EVERMEM_DB", str(Path.home() / ".evermem" / "memory.db"))


def _build_memory(args: argparse.Namespace) -> EverMem:
    db_path = Path(args.db)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    llm = None
    if getattr(args, "model", ""):
        from .llm import OllamaLLM

        llm = OllamaLLM(args.model)
    embedder = None
    if getattr(args, "embed_model", ""):
        from .embed_backends import OllamaEmbedder

        embedder = OllamaEmbedder(args.embed_model)
    return EverMem(db_path, llm=llm, embedder=embedder, user_id=args.user)


def cmd_remember(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        report = mem.observe(args.text, session_id=args.session, role=args.role)
    finally:
        mem.close()
    print(
        f"stored turn {report.turn_id}: +{report.claims_added} new,"
        f" {report.claims_reinforced} reinforced, {report.claims_superseded} superseded"
    )
    return 0


def cmd_recall(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        pack = mem.recall(
            args.query,
            session_id=args.session,
            claims_limit=args.limit,
            history_limit=args.limit,
        )
        print(pack.as_prompt(budget_chars=args.budget or None))
    finally:
        mem.close()
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    status = 0
    try:
        for raw in args.paths:
            try:
                report = mem.observe_file(raw, extract_claims=bool(args.model))
            except IngestError as exc:
                print(f"SKIP {raw}: {exc}", file=sys.stderr)
                status = 1
                continue
            extra = f", {report.claims_added} claims" if report.claims_added else ""
            print(
                f"OK   {raw}: {report.blocks} blocks,"
                f" {report.characters} chars{extra} (session {report.session_id})"
            )
    finally:
        mem.close()
    return status


def cmd_profile(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        claims = mem.profile()
        conflicts = mem.conflicts()
    finally:
        mem.close()
    if not claims:
        print("(no facts stored yet)")
        return 0
    for claim in claims:
        print(
            f"{claim.subject} | {claim.predicate} = {claim.value}"
            f"  (trust {claim.trust:.2f}, seen x{claim.support}, source {claim.source})"
        )
    if conflicts:
        print("\nOpen contradictions:")
        for hint in conflicts:
            print(f"{hint.subject} | {hint.predicate}: " + " | ".join(hint.values))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        stats = mem.stats()
    finally:
        mem.close()
    width = max(len(key) for key in stats)
    for key, value in stats.items():
        print(f"{key:<{width}}  {value}")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        primer = mem.bootstrap()
        print(primer.as_prompt(budget_chars=args.budget or None))
    finally:
        mem.close()
    return 0


def cmd_forget(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        if args.claim_id:
            ok = mem.forget_claim(args.claim_id)
            print("forgot" if ok else "not found or already inactive")
            return 0 if ok else 1
        count = mem.forget(args.subject, args.predicate, value=args.value or None)
        print(f"invalidated {count} claim(s)")
    finally:
        mem.close()
    return 0


def cmd_correct(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        claim = mem.correct(args.subject, args.predicate, args.new_value, source_session=args.session)
        print(f"corrected id={claim.id}: {claim.subject} | {claim.predicate} = {claim.value}")
    finally:
        mem.close()
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        result = mem.aggregate(args.query)
        print(
            f"{result.matching_turns} turns in {result.matching_sessions} session(s)"
            + (f": {', '.join(result.session_ids[:8])}" if result.session_ids else "")
        )
    finally:
        mem.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from .export import write_export

    write_export(args.db, args.out, user_id=args.user if args.user != "default" else None)
    print(f"exported to {args.out}")
    return 0


def cmd_consolidate(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        sid = args.session or None
        count = mem.consolidate(session_id=sid)
        print(f"summarized {count} episode(s)")
    finally:
        mem.close()
    return 0


def cmd_purge(args: argparse.Namespace) -> int:
    mem = _build_memory(args)
    try:
        counts = mem.purge()
        print("purged:", counts)
    finally:
        mem.close()
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    os.environ["EVERMEM_DB"] = args.db
    if getattr(args, "model", ""):
        os.environ["EVERMEM_MODEL"] = args.model
    if getattr(args, "embed_model", ""):
        os.environ["EVERMEM_EMBED_MODEL"] = args.embed_model
    from .mcp_server import main as mcp_main

    mcp_main()
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", default=DEFAULT_DB, help=f"database path (default: {DEFAULT_DB})")
    parser.add_argument("--user", default="default", help="user id (default: default)")
    parser.add_argument("--model", default="", help="Ollama model for LLM fact extraction")
    parser.add_argument("--embed-model", default="", help="Ollama embedding model for recall quality")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evermem",
        description="Local-first memory for any LLM: one SQLite file, no cloud.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_remember = sub.add_parser("remember", help="store a message into memory")
    p_remember.add_argument("text")
    p_remember.add_argument("--session", default="cli")
    p_remember.add_argument("--role", default="user", choices=["user", "assistant"])
    _add_common(p_remember)
    p_remember.set_defaults(func=cmd_remember)

    p_recall = sub.add_parser("recall", help="retrieve a memory pack for a query")
    p_recall.add_argument("query")
    p_recall.add_argument("--session", default="cli")
    p_recall.add_argument("--limit", type=int, default=8)
    p_recall.add_argument("--budget", type=int, default=0, help="max characters in the pack")
    _add_common(p_recall)
    p_recall.set_defaults(func=cmd_recall)

    p_import = sub.add_parser("import", help="ingest documents (pdf, docx, html, md, txt)")
    p_import.add_argument("paths", nargs="+")
    _add_common(p_import)
    p_import.set_defaults(func=cmd_import)

    p_profile = sub.add_parser("profile", help="show everything known about the user")
    _add_common(p_profile)
    p_profile.set_defaults(func=cmd_profile)

    p_stats = sub.add_parser("stats", help="database counters")
    _add_common(p_stats)
    p_stats.set_defaults(func=cmd_stats)

    p_boot = sub.add_parser("bootstrap", help="session primer: facts, conflicts, stale warnings")
    p_boot.add_argument("--budget", type=int, default=4000)
    _add_common(p_boot)
    p_boot.set_defaults(func=cmd_bootstrap)

    p_forget = sub.add_parser("forget", help="invalidate a wrong fact")
    p_forget.add_argument("--claim-id", type=int, default=0)
    p_forget.add_argument("--subject", default="")
    p_forget.add_argument("--predicate", default="")
    p_forget.add_argument("--value", default="")
    _add_common(p_forget)
    p_forget.set_defaults(func=cmd_forget)

    p_correct = sub.add_parser("correct", help="supersede a fact with a corrected value")
    p_correct.add_argument("subject")
    p_correct.add_argument("predicate")
    p_correct.add_argument("new_value")
    p_correct.add_argument("--session", default="cli")
    _add_common(p_correct)
    p_correct.set_defaults(func=cmd_correct)

    p_agg = sub.add_parser("aggregate", help="count matching turns/sessions")
    p_agg.add_argument("query")
    _add_common(p_agg)
    p_agg.set_defaults(func=cmd_aggregate)

    p_export = sub.add_parser("export", help="backup memory to JSON")
    p_export.add_argument("out")
    _add_common(p_export)
    p_export.set_defaults(func=cmd_export)

    p_consolidate = sub.add_parser("consolidate", help="summarize episodes without summaries")
    p_consolidate.add_argument("--session", default="")
    _add_common(p_consolidate)
    p_consolidate.set_defaults(func=cmd_consolidate)

    p_purge = sub.add_parser("purge", help="erase all memory for --user (GDPR)")
    _add_common(p_purge)
    p_purge.set_defaults(func=cmd_purge)

    p_mcp = sub.add_parser("mcp", help="run the MCP server (for Cursor / Claude Desktop)")
    _add_common(p_mcp)
    p_mcp.set_defaults(func=cmd_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Legacy Windows consoles default to a non-UTF8 codepage; never crash on
    # Cyrillic or emoji output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
