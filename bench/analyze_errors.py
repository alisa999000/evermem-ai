"""Error analysis for LongMemEval QA reports.

Classifies every failed question into:
- judge_suspect: gold answer is actually inside the model answer (judge was unfair),
- reader_dontknow: answer was retrieved into the pack, reader still said "I don't know",
- reader_wrong: answer was in the pack, reader answered something else,
- retrieval_miss: answer never made it into the pack.

Usage:
    python bench/analyze_errors.py --report bench/report_s_v2.json --data bench/data/longmemeval_s.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evermem.embeddings import normalize, tokens  # noqa: E402


def content_overlap(gold: str, model: str) -> float:
    g = {t for t in tokens(gold) if len(t) > 1}
    if not g:
        return 0.0
    m = set(tokens(model))
    return len(g & m) / len(g)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--examples", type=int, default=3)
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    dataset = json.loads(Path(args.data).read_text(encoding="utf-8"))
    gold_by_id = {
        str(item["question_id"]): (str(item["question"]), str(item["answer"]))
        for item in dataset
    }

    rows = [r for r in report["results"] if not r.get("abstention") and r.get("qa_correct") is not None]
    failed = [r for r in rows if not r["qa_correct"]]

    categories: dict[str, list[dict]] = defaultdict(list)
    for row in failed:
        question, gold = gold_by_id.get(str(row["question_id"]), ("", ""))
        model_answer = str(row.get("qa_answer") or "")
        norm_model = normalize(model_answer)
        norm_gold = normalize(gold)

        if norm_gold and (norm_gold in norm_model or content_overlap(gold, model_answer) >= 0.8):
            cat = "judge_suspect"
        elif "don't know" in norm_model or "do not know" in norm_model:
            cat = "reader_dontknow" if row["answer_presence"] else "retrieval_miss"
        elif row["answer_presence"]:
            cat = "reader_wrong"
        else:
            cat = "retrieval_miss"
        row["_question"] = question
        row["_gold"] = gold
        categories[cat].append(row)

    total = len(rows)
    correct = sum(1 for r in rows if r["qa_correct"])
    print(f"scored: {total}, judged correct: {correct} ({100*correct/total:.1f}%), failed: {len(failed)}")
    print()
    print("Failure breakdown:")
    for cat, items in sorted(categories.items(), key=lambda kv: -len(kv[1])):
        types = Counter(r["question_type"] for r in items)
        top_types = ", ".join(f"{t}:{n}" for t, n in types.most_common(3))
        print(f"  {cat:16s} {len(items):4d}  ({top_types})")

    suspect = len(categories.get("judge_suspect", []))
    if suspect:
        adjusted = 100 * (correct + suspect) / total
        print(f"\nIf judge_suspect counted correct: {adjusted:.1f}% (vs {100*correct/total:.1f}%)")

    for cat in ("judge_suspect", "reader_dontknow", "reader_wrong", "retrieval_miss"):
        items = categories.get(cat, [])
        if not items:
            continue
        print(f"\n--- examples: {cat} ---")
        for row in items[: args.examples]:
            print(f"  [{row['question_type']}] {row['_question'][:110]}")
            print(f"    gold : {row['_gold'][:110]}")
            print(f"    model: {str(row.get('qa_answer'))[:110]}")


if __name__ == "__main__":
    main()
