import json
from pathlib import Path

from evermem import EverMem
from evermem.counters import extract_countable_claims, summarize_entity_counts
from evermem.embeddings import normalize
from evermem.query_intent import (
    looks_like_count_query,
    looks_like_order_query,
    looks_like_recommend_query,
)
from bench.run_longmemeval import parse_date


def test_countable_claim_extraction():
    claims = extract_countable_claims(
        "I led the Alpha redesign project and I'm now leading the Beta migration project."
    )
    preds = {c.predicate for c in claims}
    assert "project_led" in preds
    assert len(claims) >= 2


def test_entity_count_summary_for_projects():
    mem = EverMem()
    mem.remember("user", "project_led", "alpha redesign")
    mem.remember("user", "project_led", "beta migration")
    summaries = summarize_entity_counts(mem.profile(), "How many projects have I led?")
    assert summaries
    assert summaries[0].count >= 2
    mem.close()


def test_recall_injects_entity_counts_for_multi_session():
    mem = EverMem()
    mem.observe("I led the Alpha project last month", session_id="s1")
    mem.observe("I'm leading the Beta project now", session_id="s2")
    pack = mem.recall("How many projects have I led?", session_id="q")
    assert pack.entity_counts
    assert any(item.count >= 2 for item in pack.entity_counts)
    assert "Distinct items counted" in pack.as_prompt()
    mem.close()


def test_recall_boosts_preferences_for_recommend_questions():
    mem = EverMem()
    mem.observe("I'm really into video editing and prefer DaVinci Resolve", session_id="s1")
    pack = mem.recall(
        "Can you recommend some resources where I can learn more about video editing?",
        session_id="q",
    )
    assert looks_like_recommend_query(pack.query)
    # preferences should appear in claims section
    text = pack.as_prompt().lower()
    assert "video" in text or "davinci" in text or "interest" in text
    mem.close()


def test_recall_adds_chronology_for_order_questions():
    mem = EverMem()
    base = 1_700_000_000.0
    mem.observe("I attended the Python webinar", session_id="s", happened_at=base)
    mem.observe("I attended the Time Management workshop", session_id="s", happened_at=base + 86400)
    pack = mem.recall(
        "Which event did I attend first, the workshop or the webinar?",
        session_id="q",
        reference_time=base + 200000,
    )
    assert looks_like_order_query(pack.query)
    assert pack.chronology
    assert pack.chronology[0].created_at <= pack.chronology[-1].created_at
    assert "Chronological order" in pack.as_prompt()
    mem.close()


def test_longmemeval_multi_session_sample_presence_improves():
    path = Path("bench/data/longmemeval_oracle.json")
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = [
        x
        for x in data
        if x.get("question_type") == "multi-session"
        and "how many projects" in x["question"].lower()
    ][:1]
    if not targets:
        return
    inst = targets[0]
    mem = EverMem()

    def ingest(instance):
        for idx, session in enumerate(instance.get("haystack_sessions", [])):
            sid = str(instance["haystack_session_ids"][idx])
            happened_at = parse_date(str(instance["haystack_dates"][idx]))
            for msg in session:
                text = str(msg.get("content", "")).strip()
                if text:
                    mem.observe(
                        text,
                        session_id=sid,
                        role=str(msg.get("role", "user")),
                        happened_at=happened_at,
                    )

    ingest(inst)
    q = inst["question"]
    ans = normalize(str(inst["answer"]))
    pack = mem.recall(
        q,
        session_id="bench",
        reference_time=parse_date(str(inst.get("question_date", ""))),
        history_limit=12,
        max_per_session=3,
    )
    assert pack.entity_counts or pack.aggregation
    mem.close()
