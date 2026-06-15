"""Tests for auto-correction and quantity claim lifecycle."""

from evermem import EverMem
from evermem.corrections import (
    detect_correction,
    entities_overlap,
    prepare_observe_drafts,
)


def test_detect_correction_ru():
    hint = detect_correction("Я купил 9 мячей а не 10")
    assert hint.is_correction
    assert hint.new_quantity == 9
    assert hint.old_quantity == 10
    assert entities_overlap(hint.entity_tokens, {"мяч"})


def test_basketball_scenario_supersedes_ten(tmp_path):
    """Reproduce user report: 10 balls stored, correction to 9, recall only 9."""
    mem = EverMem(tmp_path / "balls.db")
    mem.observe(
        "Запомни что я люблю играть в морской бой. а 25 января 26 года я купил 10 баскетбольных мячей",
        session_id="s1",
    )
    mem.observe("Я купил 9 мячей а не 10", session_id="s2")

    bought = [c for c in mem.profile() if c.predicate == "has_bought"]
    values = [c.value for c in bought]
    assert not any("10" in v for v in values), values
    assert any("9" in v for v in values)

    pack = mem.recall("сколько баскетбольных мячей я купил", session_id="s3")
    pack_values = [item.claim.value for item in pack.claims if item.claim.predicate == "has_bought"]
    assert not any("10" in v for v in pack_values), pack_values
    mem.close()


def test_exclusive_quantity_supersedes_same_predicate():
    mem = EverMem()
    mem.remember("user", "has_bought", "10 basketballs", exclusive=False)
    mem.observe("I bought 9 basketballs", session_id="s")

    active = [c.value for c in mem.profile() if c.predicate == "has_bought"]
    assert "10 basketballs" not in active
    assert any("9" in v for v in active)
    mem.close()


def test_assistant_echo_not_stored_as_purchase():
    mem = EverMem()
    mem.observe("I bought 10 balls", session_id="s1")
    mem.observe("You bought 10 balls on January 25.", session_id="s1", role="assistant")

    bought = [c for c in mem.profile() if c.predicate == "has_bought"]
    assert len(bought) == 1
    assert "10" in bought[0].value
    mem.close()


def test_prepare_observe_drafts_correction_invalidation():
    from evermem.store import ClaimStore

    store = ClaimStore(":memory:")
    store.upsert_claim(
        "default",
        __import__("evermem.types", fromlist=["ClaimDraft"]).ClaimDraft(
            subject="user",
            predicate="has_bought",
            value="10 basketballs",
            exclusive=False,
        ),
    )
    drafts = prepare_observe_drafts(
        "9 balls not 10",
        "user",
        [],
        store=store,
        user_id="default",
    )
    assert drafts
    active = store.active_claims("default")
    assert not any("10" in c.value for c in active if c.predicate == "has_bought")
    store.close()
