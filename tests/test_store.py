from evermem.store import ClaimStore
from evermem.types import ClaimDraft


def draft(subject="user", predicate="location", value="minsk", exclusive=True, **kw):
    return ClaimDraft(subject=subject, predicate=predicate, value=value, exclusive=exclusive, **kw)


def test_repeat_claim_reinforces_support_and_trust():
    store = ClaimStore()
    first, outcome1 = store.upsert_claim("u1", draft())
    second, outcome2 = store.upsert_claim("u1", draft())
    assert outcome1 == "added"
    assert outcome2 == "reinforced"
    assert second.id == first.id
    assert second.support == 2
    assert second.trust > first.trust


def test_exclusive_claim_supersedes_with_validity_window():
    store = ClaimStore()
    old, _ = store.upsert_claim("u1", draft(value="minsk"), now=1000.0)
    new, outcome = store.upsert_claim("u1", draft(value="warsaw"), now=2000.0)
    assert outcome == "superseded"

    active = store.active_claims("u1", subject="user", predicate="location")
    assert [claim.value for claim in active] == ["warsaw"]

    history = store.claim_history("u1", "user", "location")
    assert len(history) == 2
    assert history[0].value == "minsk"
    assert history[0].invalid_from == 2000.0
    assert history[0].superseded_by == new.id
    assert history[1].value == "warsaw"
    assert history[1].active


def test_non_exclusive_values_coexist_and_form_conflict():
    store = ClaimStore()
    store.upsert_claim("u1", draft(predicate="likes", value="python", exclusive=False))
    store.upsert_claim("u1", draft(predicate="likes", value="rust", exclusive=False))

    active = store.active_claims("u1", predicate="likes")
    assert len(active) == 2

    conflicts = store.conflicts("u1")
    assert len(conflicts) == 1
    assert conflicts[0].predicate == "likes"
    assert set(conflicts[0].values) == {"python", "rust"}


def test_users_are_isolated():
    store = ClaimStore()
    store.upsert_claim("alice", draft(value="minsk"))
    store.upsert_claim("bob", draft(value="grodno"))
    assert [c.value for c in store.active_claims("alice")] == ["minsk"]
    assert [c.value for c in store.active_claims("bob")] == ["grodno"]


def test_search_finds_relevant_claim_despite_morphology():
    store = ClaimStore()
    store.upsert_claim("u1", draft(subject="эйнштейн", predicate="нобелевская премия", value="1921", exclusive=False))
    store.upsert_claim("u1", draft(subject="user", predicate="likes", value="кофе", exclusive=False))

    results = store.search_claims("u1", "когда эйнштейну дали нобелевскую премию?")
    assert results[0][0].subject == "эйнштейн"
    assert results[0][1] > results[1][1]


def test_custom_embed_fn_any_dimension():
    def tiny_embed(text: str) -> list[float]:
        # 4-dim toy embedding: deterministic, distinguishes "cat" from "dog".
        base = [0.1, 0.2, 0.3, 0.4]
        if "cat" in text:
            base = [1.0, 0.0, 0.0, 0.0]
        if "dog" in text:
            base = [0.0, 1.0, 0.0, 0.0]
        return base

    store = ClaimStore(embed_fn=tiny_embed)
    store.upsert_claim("u1", draft(predicate="has_pet", value="cat", exclusive=False))
    store.upsert_claim("u1", draft(predicate="has_car", value="dog sled", exclusive=False))

    results = store.search_claims("u1", "cat")
    assert results[0][0].value == "cat"
    assert results[0][1] > results[1][1]


def test_persistence_roundtrip(tmp_path):
    db = tmp_path / "memory.db"
    store = ClaimStore(db)
    store.upsert_claim("u1", draft())
    store.save_meta("plasticity", [{"src": "a", "dst": "b", "weight": 1.0, "hits": 3}])
    store.close()

    reopened = ClaimStore(db)
    assert [c.value for c in reopened.active_claims("u1")] == ["minsk"]
    meta = reopened.load_meta("plasticity")
    assert meta == [{"src": "a", "dst": "b", "weight": 1.0, "hits": 3}]
