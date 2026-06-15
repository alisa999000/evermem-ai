from evermem import EverMem


def test_observe_then_recall_across_sessions(tmp_path):
    db = tmp_path / "memory.db"

    mem = EverMem(db)
    mem.observe("Меня зовут Алекс, я живу в Минске", session_id="s1")
    mem.observe("я люблю чёрный кофе", session_id="s1")
    mem.close()

    # New process, new session; memory survives.
    mem2 = EverMem(db)
    pack = mem2.recall("как зовут пользователя и где он живет?", session_id="s2")
    text = pack.as_prompt().lower()
    assert "алекс" in text
    assert "минск" in text
    mem2.close()


def test_supersede_via_dialogue(tmp_path):
    mem = EverMem(tmp_path / "m.db")
    mem.observe("я живу в Минске")
    mem.observe("я переехал в Варшаву")

    pack = mem.recall("где живет пользователь?")
    values = [item.claim.value for item in pack.claims if item.claim.predicate == "location"]
    assert len(values) == 1
    assert values[0].startswith("варшав")

    history = mem.history("user", "location")
    assert [claim.value[:6] for claim in history] == ["минске"[:6], "варшав"]
    assert history[0].invalid_from is not None
    mem.close()


def test_conflict_surfaces_in_pack():
    mem = EverMem()
    mem.remember("user", "favorite_editor", "vim", exclusive=False)
    mem.remember("user", "favorite_editor", "emacs", exclusive=False)

    pack = mem.recall("favorite editor?")
    assert pack.conflicts
    conflict = pack.conflicts[0]
    assert set(conflict.values) == {"vim", "emacs"}
    assert "contradictions" in pack.as_prompt().lower()


def test_feedback_changes_trust_and_paths():
    mem = EverMem()
    claim = mem.remember("user", "likes", "coffee")
    before_trust = mem.store.get_claim(claim.id).trust
    before_path = mem.plasticity.path_score(["s:user", "p:likes", "v:coffee"])

    mem.recall("what does the user like?")
    touched = mem.feedback(True)
    assert touched >= 1
    assert mem.store.get_claim(claim.id).trust > before_trust
    assert mem.plasticity.path_score(["s:user", "p:likes", "v:coffee"]) > before_path


def test_recall_prefers_relevant_claim():
    mem = EverMem()
    mem.remember("user", "name", "алекс", exclusive=True)
    mem.remember("user", "has_pet", "кот барсик")
    mem.remember("эйнштейн", "нобелевская премия", "1921")

    pack = mem.recall("расскажи про нобелевскую премию эйнштейна")
    assert pack.claims
    assert pack.claims[0].claim.subject == "эйнштейн"


def test_history_surfaces_verbatim_turns_across_sessions():
    mem = EverMem()
    mem.observe("вчера мы обсуждали архитектуру декодера на GRU", session_id="old")
    mem.observe("сегодня хорошая погода", session_id="old")

    pack = mem.recall("что мы говорили про декодер?", session_id="new")
    assert pack.history
    assert "декодера" in pack.history[0].text
    assert "Relevant past messages" in pack.as_prompt()


def test_assistant_turns_searchable_and_extract_recommendations():
    mem = EverMem()
    mem.observe("I recommend the Honda Civic for your budget", session_id="s1", role="assistant")
    assert mem.stats()["claims_active"] >= 1

    pack = mem.recall("which car was recommended?", session_id="s2")
    prompt = pack.as_prompt().lower()
    assert "honda" in prompt or any("honda" in turn.text.lower() for turn in pack.history)


def test_history_diversity_caps_per_session():
    mem = EverMem()
    for i in range(6):
        mem.observe(f"в спортзале сегодня делал жим лежа подход {i}", session_id="gym-day-1")
    mem.observe("в спортзале делал приседания", session_id="gym-day-2")
    mem.observe("в спортзале делал становую тягу", session_id="gym-day-3")

    pack = mem.recall("что я делал в спортзале?", session_id="new", history_limit=6)
    sessions = [turn.session_id for turn in pack.history]
    assert sessions.count("gym-day-1") <= 2
    assert len(set(sessions)) >= 3


def test_timeline_renders_dates_and_offsets():
    import datetime

    mem = EverMem()
    day = datetime.datetime(2023, 5, 20).timestamp()
    question_day = datetime.datetime(2023, 5, 30).timestamp()
    mem.observe("я пробежал марафон в парке", session_id="s1", happened_at=day)

    pack = mem.recall("когда я бегал марафон?", session_id="s2", reference_time=question_day)
    prompt = pack.as_prompt()
    assert "2023-05-20" in prompt
    assert "10 days before the question" in prompt


def test_timeline_precomputes_day_gaps_between_events():
    import datetime

    mem = EverMem()
    first = datetime.datetime(2023, 1, 10).timestamp()
    second = datetime.datetime(2023, 1, 17).timestamp()
    question_day = datetime.datetime(2023, 2, 1).timestamp()
    mem.observe("я сходил на воркшоп по коммуникации", session_id="s1", happened_at=first)
    mem.observe("я сходил на командную встречу по проекту", session_id="s2", happened_at=second)

    pack = mem.recall("сколько дней между воркшопом и встречей?", session_id="s3", reference_time=question_day)
    prompt = pack.as_prompt()
    assert "2023-01-10 -> 2023-01-17 = 7 days" in prompt


def test_long_turn_found_by_inner_chunk():
    mem = EverMem()
    filler = "Сначала мы долго обсуждали погоду, планы на отпуск и сериалы. " * 8
    needle = "Кстати, мой рейс в Стамбул - номер TK284."
    mem.observe(filler + needle, session_id="s1", role="assistant")
    mem.observe("обычное сообщение про кофе", session_id="s1")

    pack = mem.recall("какой номер рейса в Стамбул?", session_id="s2")
    assert pack.history
    assert "TK284" in pack.history[0].text


def test_stats():
    mem = EverMem()
    mem.observe("меня зовут Анна")
    stats = mem.stats()
    assert stats["claims_active"] >= 1
    assert stats["turns"] == 1
    assert stats["episodes"] == 1
