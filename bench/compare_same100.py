"""Compare v3 Qwen vs DeepSeek on the exact same 100 oracle questions."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def pct(rows: list[dict], key: str) -> float:
    vals = [float(r[key]) for r in rows if r.get(key) is not None]
    return 100.0 * sum(vals) / len(vals) if vals else 0.0


def main() -> None:
    v3 = json.loads(Path("bench/report_oracle_v3.json").read_text(encoding="utf-8"))
    ds = json.loads(Path("bench/report_oracle_deepseek_v4_100q.json").read_text(encoding="utf-8"))

    v3_map = {r["question_id"]: r for r in v3["results"]}
    ds_map = {r["question_id"]: r for r in ds["results"]}
    common_ids = [qid for qid in ds_map if qid in v3_map]

    v3_rows = [v3_map[qid] for qid in common_ids]
    ds_rows = [ds_map[qid] for qid in common_ids]
    v3_scored = [r for r in v3_rows if not r.get("abstention")]
    ds_scored = [r for r in ds_rows if not r.get("abstention")]

    print(f"matched questions: {len(common_ids)}")
    print(
        f"v3 Qwen on SAME 100q: QA {pct(v3_scored, 'qa_correct'):.1f}%  "
        f"presence {pct(v3_scored, 'answer_presence'):.1f}%  "
        f"evidence {pct(v3_scored, 'evidence_recall'):.1f}%"
    )
    print(
        f"ds DeepSeek SAME 100q: QA {pct(ds_scored, 'qa_correct'):.1f}%  "
        f"presence {pct(ds_scored, 'answer_presence'):.1f}%  "
        f"evidence {pct(ds_scored, 'evidence_recall'):.1f}%"
    )
    print()

    by_type: dict[str, list[str]] = defaultdict(list)
    for qid in common_ids:
        by_type[v3_map[qid]["question_type"]].append(qid)

    print("per type (same questions):")
    for t in sorted(by_type):
        ids = by_type[t]
        v3_t = [v3_map[i] for i in ids if not v3_map[i].get("abstention")]
        ds_t = [ds_map[i] for i in ids if not ds_map[i].get("abstention")]
        print(
            f"  {t:25s} n={len(v3_t):3d}  "
            f"v3 QA={pct(v3_t, 'qa_correct'):5.1f}%  ds QA={pct(ds_t, 'qa_correct'):5.1f}%  "
            f"v3 pres={pct(v3_t, 'answer_presence'):5.1f}%  ds pres={pct(ds_t, 'answer_presence'):5.1f}%"
        )

    pairs = [
        (v3_map[qid], ds_map[qid])
        for qid in common_ids
        if not v3_map[qid].get("abstention")
    ]
    both_ok = sum(1 for a, b in pairs if a.get("qa_correct") and b.get("qa_correct"))
    both_bad = sum(1 for a, b in pairs if not a.get("qa_correct") and not b.get("qa_correct"))
    v3_only = sum(1 for a, b in pairs if a.get("qa_correct") and not b.get("qa_correct"))
    ds_only = sum(1 for a, b in pairs if b.get("qa_correct") and not a.get("qa_correct"))
    print()
    print(f"head-to-head: both_ok={both_ok} both_bad={both_bad} v3_only={v3_only} ds_only={ds_only}")

    # Failure modes: ds wrong when presence was true
    ds_wrong_pres = [
        b for a, b in pairs if not b.get("qa_correct") and b.get("answer_presence")
    ]
    v3_wrong_pres = [
        a for a, b in pairs if not a.get("qa_correct") and a.get("answer_presence")
    ]
    print(
        f"wrong despite presence in pack: ds={len(ds_wrong_pres)}  v3={len(v3_wrong_pres)}"
    )

    print("\nv3 correct, ds wrong (sample):")
    shown = 0
    for a, b in pairs:
        if a.get("qa_correct") and not b.get("qa_correct"):
            if shown >= 5:
                break
            shown += 1
            print(f"  {b['question_id']} [{b['question_type']}] pres={b.get('answer_presence')}")
            print(f"    v3: {a.get('qa_answer', '')[:100]}")
            print(f"    ds: {b.get('qa_answer', '')[:100]}")

    print("\nds correct, v3 wrong (sample):")
    shown = 0
    for a, b in pairs:
        if b.get("qa_correct") and not a.get("qa_correct"):
            if shown >= 5:
                break
            shown += 1
            print(f"  {b['question_id']} [{b['question_type']}] pres={b.get('answer_presence')}")
            print(f"    v3: {a.get('qa_answer', '')[:100]}")
            print(f"    ds: {b.get('qa_answer', '')[:100]}")


if __name__ == "__main__":
    main()
