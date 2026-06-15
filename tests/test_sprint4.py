"""Sprint 4: temporal events, assistant extraction, query router."""

import datetime as _dt

from evermem import EverMem
from evermem.events import extract_assistant_claims, extract_memory_events
from evermem.query_intent import looks_like_temporal_query, query_profile


def test_memory_events_indexed_on_observe():
    mem = EverMem()
    base = 1_700_000_000.0
    report = mem.observe(
        "I attended the Python webinar and finished The Nightingale",
        session_id="s1",
        happened_at=base,
    )
    assert report.events_added >= 1
    stats = mem.stats()
    assert stats["memory_events"] >= 1
    mem.close()


def test_assistant_recommendations_become_claims():
    mem = EverMem()
    mem.observe(
        "I'd recommend checking out DaVinci Resolve tutorials and the r/VideoEditing community.",
        session_id="s1",
        role="assistant",
    )
    preds = {c.predicate for c in mem.profile()}
    assert "recommendation" in preds
    mem.close()


def test_temporal_recall_injects_event_timeline_and_gaps():
    mem = EverMem()
    base = _dt.datetime(2023, 5, 1).timestamp()
    mem.observe("I attended Sunday mass at St. Mary's Church", session_id="s1", happened_at=base)
    mem.observe(
        "I went to the Ash Wednesday service at the cathedral",
        session_id="s2",
        happened_at=base + 30 * 86400,
    )
    ref = base + 40 * 86400
    pack = mem.recall(
        "How many days had passed between the Sunday mass at St. Mary's Church and the Ash Wednesday service?",
        session_id="q",
        reference_time=ref,
    )
    assert pack.query_profile == "temporal"
    assert pack.timeline_events
    assert pack.temporal_gaps
    assert any(gap.days == 30 for gap in pack.temporal_gaps)
    prompt = pack.as_prompt()
    assert "Pre-computed day gaps" in prompt
    assert "30 days" in prompt
    mem.close()


def test_structured_query_uses_wider_history_window():
    mem = EverMem()
    pack = mem.recall("How many projects have I led?", session_id="q", history_limit=6)
    assert pack.query_profile == "count"
    assert "Distinct items counted" in pack.as_prompt() or pack.entity_counts is not None
    mem.close()


def test_extract_assistant_claims_patterns():
    claims = extract_assistant_claims("You should try the Coursera photography course.")
    assert claims
    assert claims[0].kind == "preference"


def test_extract_memory_events_patterns():
    events = extract_memory_events("I finished reading The Hate U Give last week.")
    assert events
    assert any("finished" in event.label.lower() for event in events)


def test_query_profile_buckets():
    assert query_profile("How many days between X and Y?") == "temporal"
    assert looks_like_temporal_query("How long did it take me to find a house?")
