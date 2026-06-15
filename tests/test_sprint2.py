import time

from evermem import EverMem
from evermem.query_intent import count_topic_from_query, looks_like_count_query
from evermem.store import EPISODE_GAP_SECONDS


def test_count_query_detection():
    assert looks_like_count_query("How many times did I go to the gym?")
    assert looks_like_count_query("сколько раз я ходил в зал?")
    assert not looks_like_count_query("where do I live?")
    assert "зал" in count_topic_from_query("сколько раз я ходил в зал?")


def test_recall_auto_injects_aggregation():
    mem = EverMem()
    for i in range(4):
        mem.observe(f"сегодня ходил в зал, тренировка номер {i}", session_id=f"gym-{i}")
    pack = mem.recall("сколько раз я ходил в зал?", session_id="current")
    assert pack.aggregation is not None
    assert pack.aggregation.matching_turns >= 4
    prompt = pack.as_prompt()
    assert "mention counts" in prompt.lower() or "Distinct items counted" in prompt
    assert "4" in prompt or str(pack.aggregation.matching_turns) in prompt
    mem.close()


def test_episode_summarized_when_session_gap_closes_episode():
    mem = EverMem()
    base = time.time() - 10_000
    mem.observe("обсудили проект альфа", session_id="work", happened_at=base)
    mem.observe("решили перенести дедлайн", session_id="work", happened_at=base + 120)
    mem.observe("новая тема: отпуск", session_id="work", happened_at=base + EPISODE_GAP_SECONDS + 200)

    closed = mem.store.get_episode(1)
    assert closed is not None
    assert closed.summary.strip()
    assert "альфа" in closed.summary.lower() or "проект" in closed.summary.lower()
    mem.close()


def test_consolidate_fills_missing_summaries():
    mem = EverMem()
    # Insert episode without going through observe gap path
    now = time.time()
    eid = mem.store.touch_episode("manual", "default", "notes", now=now).episode_id
    mem.store.add_turn("manual", "default", "user", "первая мысль", now=now)
    mem.store.add_turn("manual", "default", "user", "вторая мысль", now=now + 1)
    mem.store._conn.execute(
        "UPDATE episodes SET turns=2, first_at=?, last_at=? WHERE id=?",
        (now, now + 1, eid),
    )
    mem.store._conn.commit()

    count = mem.consolidate(session_id="manual")
    assert count >= 1
    episode = mem.store.get_episode(eid)
    assert episode and episode.summary.strip()
    mem.close()


def test_langchain_adapter_roundtrip():
    pytest = __import__("pytest")
    langchain_core = pytest.importorskip("langchain_core")
    del langchain_core

    from evermem.integrations.langchain import EverMemChatHistory, EverMemRetriever

    mem = EverMem()
    history = EverMemChatHistory(mem, session_id="lc")
    history.add_user_message("I love hiking in the mountains")
    retriever = EverMemRetriever(mem, session_id="lc")
    prompt = retriever.invoke("what do I love?")
    assert "[MEMORY]" in prompt
    mem.close()
