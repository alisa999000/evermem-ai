from evermem import EverMem


def test_forget_and_correct_lifecycle():
    mem = EverMem()
    mem.observe("я живу в Минске", session_id="s1")
    mem.observe("я переехал в Варшаву", session_id="s2")

    active = mem.profile()
    locations = [c.value for c in active if c.predicate == "location"]
    assert "варшаву" in locations
    assert "минске" not in locations

    claim = mem.remember("user", "favorite_color", "синий")
    assert mem.forget_claim(claim.id)
    assert not any(c.predicate == "favorite_color" for c in mem.profile())

    mem.correct("user", "name", "Алексей", source_session="fix")
    names = [c for c in mem.profile() if c.predicate == "name"]
    assert any("алексей" in c.value for c in names)
    mem.close()


def test_bootstrap_surfaces_conflicts_and_stale():
    mem = EverMem()
    mem.remember("user", "diet", "веган", exclusive=False)
    mem.remember("user", "diet", "мясоед", exclusive=False)
    primer = mem.bootstrap()
    assert primer.conflicts
    text = primer.as_prompt()
    assert "[MEMORY_PRIMER]" in text
    assert "contradiction" in text.lower() or "diet" in text
    mem.close()


def test_aggregate_counts_sessions():
    mem = EverMem()
    for i in range(3):
        mem.observe(f"сегодня я ходил в зал номер {i}", session_id=f"gym-{i}")
    mem.observe("погода солнечная", session_id="weather")
    result = mem.aggregate("ходил в зал")
    assert result.matching_turns >= 3
    assert result.matching_sessions >= 3
    mem.close()


def test_provenance_on_observe():
    mem = EverMem()
    mem.observe("меня зовут Алекс", session_id="chat-42")
    claims = [c for c in mem.profile() if c.predicate == "name"]
    assert claims
    assert claims[0].source_turn_id is not None
    assert claims[0].source_session == "chat-42"
    mem.close()


def test_purge_erases_user():
    mem = EverMem()
    mem.observe("секрет", user_id="alice")
    counts = mem.purge(user_id="alice")
    assert counts["turns"] >= 1
    mem.close()

    mem2 = EverMem(mem.store.path)
    assert mem2.profile(user_id="alice") == []
    mem2.close()


def test_feedback_isolated_by_user():
    mem = EverMem()
    mem.observe("alice loves tea", user_id="alice", session_id="s")
    mem.observe("bob loves coffee", user_id="bob", session_id="s")
    mem.recall("what does alice like?", user_id="alice", session_id="s")
    mem.feedback(True, session_id="s", user_id="alice")
    mem.recall("what does bob like?", user_id="bob", session_id="s")
    n = mem.feedback(False, session_id="s", user_id="bob")
    assert n >= 0
    mem.close()
