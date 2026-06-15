"""LongMemEval retrieval benchmark for evermem.

Dataset: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
(500 questions; each = a chat history + a question about it).

For every question we:
1. ingest the whole chat history through `EverMem.observe()` (fresh memory per question),
2. call `recall(question)` and get a MemoryPack,
3. score the pack WITHOUT any LLM:
   - answer_presence: the gold answer string occurs in the pack (strict),
   - token_recall: fraction of gold-answer content tokens present in the pack (soft),
   - evidence_recall: fraction of evidence sessions that made it into the
     pack's retrieved history (meaningful for _s/_m variants with distractor
     sessions; on the oracle variant every session is evidence).

Abstention questions (`*_abs`) are excluded from presence metrics and counted
separately; the correct behavior there is to find nothing.

Usage:
    python bench/run_longmemeval.py --data bench/data/longmemeval_oracle.json --limit 50
    python bench/run_longmemeval.py --data bench/data/longmemeval_oracle.json --report bench/report.json
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

_bench_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_bench_dir.parent))
sys.path.insert(0, str(_bench_dir))

from evermem import EverMem, OllamaEmbedder  # noqa: E402
from evermem.llm import OllamaLLM  # noqa: E402
from evermem.embeddings import normalize, split_chunks, token_key, tokens  # noqa: E402
from evermem.llm import LLMUnavailable  # noqa: E402

from llm_backends import build_qa_llm, describe_backend  # noqa: E402

QA_SYSTEM = (
    "You are a helpful assistant with memory of past conversations with the user. "
    "Use ONLY the information in the [MEMORY] block. "
    "Think briefly in 1-3 short steps (counting, comparing dates if needed), "
    "then give the final line in the format 'Answer: <short answer>'. "
    "Timeline entries already include dates, day offsets and pre-computed day gaps "
    "between events - use those numbers directly instead of computing dates yourself. "
    "Distinct item counts and chronological order sections are also pre-computed - "
    "trust those numbers for how-many and which-first questions. "
    "Only if the memory has no relevant information at all, finish with 'Answer: I don't know'."
)

JUDGE_SYSTEM = (
    "You are grading answers about a user's conversation history. "
    "Reply with exactly one word: CORRECT or WRONG. "
    "The model answer is CORRECT if it contains or implies the gold answer's key "
    "information, even with extra detail, different wording or formatting. "
    "Mark WRONG only if the key information is missing or contradicts the gold answer."
)

STOP_TOKENS = {
    "the", "a", "an", "of", "to", "in", "on", "at", "and", "or", "is", "was",
    "were", "are", "for", "with", "his", "her", "their", "its", "it", "they",
    "he", "she", "user", "users",
}


def content_tokens(text: str) -> set[str]:
    return {
        token_key(tok)
        for tok in tokens(text)
        if len(tok) > 1 and tok not in STOP_TOKENS
    }


def parse_date(raw: str) -> float | None:
    """Parse LongMemEval dates like '2023/05/20 (Sat) 02:21' to epoch seconds."""
    match = re.search(r"(\d{4})/(\d{2})/(\d{2})(?:.*?(\d{2}):(\d{2}))?", str(raw))
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    hour = int(match.group(4) or 0)
    minute = int(match.group(5) or 0)
    try:
        return datetime.datetime(year, month, day, hour, minute).timestamp()
    except ValueError:
        return None


def run_qa(qa_llm, judge_llm, *, pack, question: str, question_date: str, answer: str, is_abstention: bool) -> dict:
    out: dict = {"qa_answer": None, "qa_substring": None, "qa_correct": None}
    try:
        prompt = (
            f"{pack.as_prompt()}\n\nToday is {question_date}.\n"
            f"Question: {question}"
        )
        raw_answer = qa_llm.complete(QA_SYSTEM, prompt).strip()
    except LLMUnavailable:
        return out
    # Take the text after the last 'Answer:' marker (reasoning comes before it).
    marker = raw_answer.rfind("Answer:")
    model_answer = raw_answer[marker + len("Answer:"):].strip() if marker >= 0 else raw_answer
    out["qa_answer"] = model_answer[:300]

    model_norm = normalize(model_answer)
    if is_abstention:
        out["qa_correct"] = "don't know" in model_norm or "do not know" in model_norm
        out["qa_substring"] = out["qa_correct"]
        return out

    out["qa_substring"] = bool(normalize(answer)) and normalize(answer) in model_norm
    if out["qa_substring"]:
        # Gold answer is contained verbatim; skip the judge.
        # (error analysis showed the judge wrongly fails ~5-7% of these).
        out["qa_correct"] = True
        return out
    if judge_llm is not None:
        try:
            verdict = judge_llm.complete(
                JUDGE_SYSTEM,
                f"Question: {question}\nGold answer: {answer}\nModel answer: {model_answer}\nVerdict:",
            )
            out["qa_correct"] = verdict.strip().lower().startswith("correct")
        except LLMUnavailable:
            out["qa_correct"] = None
    return out


def evaluate_instance(
    instance: dict,
    *,
    claims_limit: int,
    history_limit: int,
    max_per_session: int = 3,
    embedder=None,
    qa_llm=None,
    judge_llm=None,
    extract_llm=None,
) -> dict:
    question_id = str(instance.get("question_id", ""))
    question = str(instance.get("question", ""))
    answer = str(instance.get("answer", ""))
    question_type = str(instance.get("question_type", "unknown"))
    is_abstention = question_id.endswith("_abs")

    sessions = instance.get("haystack_sessions", []) or []
    session_ids = instance.get("haystack_session_ids", []) or []
    session_dates = instance.get("haystack_dates", []) or []
    evidence_ids = set(instance.get("answer_session_ids", []) or [])

    mem = EverMem(embedder=embedder, llm=extract_llm) if extract_llm else EverMem(embedder=embedder)
    ingest_start = time.perf_counter()
    prepared: list[tuple[str, str, str, float | None]] = []
    for idx, session in enumerate(sessions):
        sid = str(session_ids[idx]) if idx < len(session_ids) else f"session-{idx}"
        date = str(session_dates[idx]) if idx < len(session_dates) else ""
        happened_at = parse_date(date)
        for message in session:
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            prepared.append((sid, str(message.get("role", "user")), content, happened_at))
    if embedder is not None and hasattr(embedder, "prewarm"):
        to_warm: list[str] = [question]
        for _, _, text, _ in prepared:
            to_warm.extend(split_chunks(text))
        embedder.prewarm(to_warm)
    for sid, role, text, happened_at in prepared:
        mem.observe(text, session_id=sid, role=role, happened_at=happened_at)
    ingest_seconds = time.perf_counter() - ingest_start

    reference_time = parse_date(str(instance.get("question_date", "")))
    recall_start = time.perf_counter()
    pack = mem.recall(
        question,
        session_id="__bench_question__",
        claims_limit=claims_limit,
        history_limit=history_limit,
        max_per_session=max_per_session,
        reference_time=reference_time,
    )
    recall_seconds = time.perf_counter() - recall_start

    pack_text = normalize(pack.searchable_text())
    answer_norm = normalize(answer)
    presence = bool(answer_norm) and answer_norm in pack_text

    answer_tokens = content_tokens(answer)
    pack_tokens = content_tokens(pack_text)
    token_recall = (
        len(answer_tokens & pack_tokens) / len(answer_tokens) if answer_tokens else 0.0
    )

    retrieved_sessions = {turn.session_id for turn in pack.history}
    evidence_recall = (
        len(retrieved_sessions & evidence_ids) / len(evidence_ids) if evidence_ids else None
    )

    row = {
        "question_id": question_id,
        "question_type": question_type,
        "abstention": is_abstention,
        "answer_presence": presence,
        "token_recall": round(token_recall, 4),
        "evidence_recall": None if evidence_recall is None else round(evidence_recall, 4),
        "sessions": len(sessions),
        "ingest_seconds": round(ingest_seconds, 3),
        "recall_seconds": round(recall_seconds, 3),
    }
    if qa_llm is not None:
        row.update(
            run_qa(
                qa_llm,
                judge_llm,
                pack=pack,
                question=question,
                question_date=str(instance.get("question_date", "")),
                answer=answer,
                is_abstention=is_abstention,
            )
        )
    mem.close()
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LongMemEval retrieval benchmark on evermem.")
    parser.add_argument("--data", required=True, help="Path to longmemeval_*.json")
    parser.add_argument("--limit", type=int, default=0, help="Evaluate only first N questions (0 = all).")
    parser.add_argument("--claims-limit", type=int, default=8)
    parser.add_argument("--history-limit", type=int, default=12)
    parser.add_argument("--max-per-session", type=int, default=3)
    parser.add_argument("--report", default="", help="Write a JSON report to this path.")
    parser.add_argument(
        "--embed-model",
        default="",
        help="Ollama embedding model (e.g. nomic-embed-text). Empty = hash embeddings.",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get("EVERMEM_OLLAMA_URL", "http://localhost:11434"),
        help="Ollama base URL for embeddings (default localhost).",
    )
    parser.add_argument(
        "--qa-backend",
        default="ollama",
        choices=["ollama", "deepseek", "openai"],
        help="QA/judge provider: ollama (local), deepseek (API), openai (API).",
    )
    parser.add_argument(
        "--qa-model",
        default="",
        help="Model name. Ollama: qwen2.5:7b. DeepSeek: deepseek-chat. OpenAI: gpt-4o.",
    )
    parser.add_argument(
        "--judge-model",
        default="",
        help="Judge model (default: same as --qa-model).",
    )
    parser.add_argument(
        "--judge-backend",
        default="",
        help="Judge provider (default: same as --qa-backend).",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API key for deepseek/openai backends (or use DEEPSEEK_API_KEY / OPENAI_API_KEY).",
    )
    parser.add_argument(
        "--api-base-url",
        default="",
        help="Override API base URL (DeepSeek default https://api.deepseek.com/v1).",
    )
    parser.add_argument(
        "--extract-llm",
        default="",
        help="Ollama model for claim extraction at ingest (e.g. qwen2.5:7b). Empty = rules only.",
    )
    parser.add_argument("--every", type=int, default=1, help="Evaluate every Nth question (sampling).")
    args = parser.parse_args()

    data = json.loads(Path(args.data).read_text(encoding="utf-8"))
    if args.every > 1:
        data = data[:: args.every]
    if args.limit > 0:
        data = data[: args.limit]

    embedder = (
        OllamaEmbedder(args.embed_model, base_url=args.ollama_url)
        if args.embed_model
        else None
    )

    qa_llm = None
    judge_llm = None
    run_qa_stage = bool(args.qa_model) or args.qa_backend in {"deepseek", "openai"}
    if run_qa_stage:
        qa_llm = build_qa_llm(
            backend=args.qa_backend,
            model=args.qa_model,
            base_url=args.api_base_url,
            api_key=args.api_key,
            timeout=300.0,
        )
        judge_backend = args.judge_backend or args.qa_backend
        judge_model = args.judge_model or args.qa_model
        judge_llm = build_qa_llm(
            backend=judge_backend,
            model=judge_model,
            base_url=args.api_base_url,
            api_key=args.api_key,
            timeout=300.0,
        )

    extract_llm = None
    if args.extract_llm.strip():
        extract_llm = OllamaLLM(args.extract_llm.strip(), base_url=args.ollama_url)

    qa_label = "off"
    if qa_llm is not None:
        qa_label = describe_backend(args.qa_backend, args.qa_model)
        if args.judge_model and args.judge_model != args.qa_model:
            qa_label += f" judge={describe_backend(args.judge_backend or args.qa_backend, args.judge_model)}"
    print(
        f"embeddings: {args.embed_model or 'hash (zero-dep)'};"
        f" extract: {args.extract_llm or 'rules'};"
        f" qa: {qa_label}; questions: {len(data)}"
    )

    results: list[dict] = []
    errors = 0
    started = time.perf_counter()
    for index, instance in enumerate(data):
        try:
            results.append(
                evaluate_instance(
                    instance,
                    claims_limit=args.claims_limit,
                    history_limit=args.history_limit,
                    max_per_session=args.max_per_session,
                    embedder=embedder,
                    qa_llm=qa_llm,
                    judge_llm=judge_llm,
                    extract_llm=extract_llm,
                )
            )
        except Exception as exc:  # one bad instance must not kill a multi-hour run
            errors += 1
            print(f"  [{index + 1}] ERROR {instance.get('question_id', '?')}: {exc}", flush=True)
        finally:
            # Texts never repeat across questions; a growing cache only eats RAM.
            if embedder is not None and hasattr(embedder, "clear_cache"):
                embedder.clear_cache()
        if (index + 1) % 25 == 0 or index + 1 == len(data):
            elapsed = time.perf_counter() - started
            print(f"  [{index + 1}/{len(data)}] elapsed {elapsed:.0f}s", flush=True)
    if errors:
        print(f"  errors: {errors} instances skipped", flush=True)

    scored = [row for row in results if not row["abstention"]]
    abstained = [row for row in results if row["abstention"]]

    def pct(rows: list[dict], key: str) -> float:
        vals = [float(row[key]) for row in rows if row[key] is not None]
        return 100.0 * sum(vals) / len(vals) if vals else 0.0

    print()
    print("=== evermem x LongMemEval (retrieval, no LLM) ===")
    print(f"questions scored: {len(scored)}  (abstention excluded: {len(abstained)})")
    print(f"answer presence : {pct(scored, 'answer_presence'):.1f}%")
    print(f"token recall    : {pct(scored, 'token_recall'):.1f}%")
    evidence_rows = [row for row in scored if row["evidence_recall"] is not None]
    if evidence_rows:
        print(f"evidence recall : {pct(evidence_rows, 'evidence_recall'):.1f}%")

    qa_rows = [row for row in scored if row.get("qa_correct") is not None]
    if qa_rows:
        print(f"QA accuracy     : {pct(qa_rows, 'qa_correct'):.1f}%  (LLM reader + judge, n={len(qa_rows)})")
        print(f"QA substring    : {pct(qa_rows, 'qa_substring'):.1f}%")
        abs_rows = [row for row in abstained if row.get("qa_correct") is not None]
        if abs_rows:
            print(f"abstention acc  : {pct(abs_rows, 'qa_correct'):.1f}%  (n={len(abs_rows)})")
    print()

    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in scored:
        by_type[row["question_type"]].append(row)
    has_qa = any(row.get("qa_correct") is not None for row in scored)
    header = f"{'question type':32s} {'n':>4s} {'presence':>9s} {'tok.rec':>8s}"
    if has_qa:
        header += f" {'QA acc':>7s}"
    print(header)
    for question_type in sorted(by_type):
        rows = by_type[question_type]
        line = (
            f"{question_type:32s} {len(rows):4d}"
            f" {pct(rows, 'answer_presence'):8.1f}%"
            f" {pct(rows, 'token_recall'):7.1f}%"
        )
        if has_qa:
            qa_typed = [row for row in rows if row.get("qa_correct") is not None]
            line += f" {pct(qa_typed, 'qa_correct'):6.1f}%"
        print(line)

    total_ingest = sum(row["ingest_seconds"] for row in results)
    total_recall = sum(row["recall_seconds"] for row in results)
    print(f"\ningest {total_ingest:.0f}s total, recall {total_recall:.2f}s total")

    if args.report:
        qa_scored = [row for row in scored if row.get("qa_correct") is not None]
        payload = {
            "dataset": str(args.data),
            "embed_model": args.embed_model or "hash",
            "extract_model": args.extract_llm or "rules",
            "qa_backend": args.qa_backend if qa_llm else None,
            "qa_model": args.qa_model or None,
            "qa_label": qa_label if qa_llm else None,
            "questions": len(results),
            "answer_presence_pct": round(pct(scored, "answer_presence"), 2),
            "token_recall_pct": round(pct(scored, "token_recall"), 2),
            "qa_accuracy_pct": round(pct(qa_scored, "qa_correct"), 2) if qa_scored else None,
            "per_type": {
                qt: {
                    "n": len(rows),
                    "answer_presence_pct": round(pct(rows, "answer_presence"), 2),
                    "token_recall_pct": round(pct(rows, "token_recall"), 2),
                }
                for qt, rows in sorted(by_type.items())
            },
            "results": results,
        }
        Path(args.report).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"report written to {args.report}")


if __name__ == "__main__":
    main()
