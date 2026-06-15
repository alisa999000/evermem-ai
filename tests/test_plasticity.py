from evermem.plasticity import PathPlasticity


def test_reward_raises_path_score():
    plasticity = PathPlasticity()
    nodes = ["s:user", "p:location", "v:minsk"]
    base = plasticity.path_score(nodes)
    for _ in range(5):
        plasticity.update_path(nodes, reward=0.9, confidence=0.9)
    assert plasticity.path_score(nodes) > base


def test_contradiction_lowers_path_score():
    plasticity = PathPlasticity()
    nodes = ["s:user", "p:location", "v:minsk"]
    for _ in range(5):
        plasticity.update_path(nodes, reward=0.9, confidence=0.9)
    high = plasticity.path_score(nodes)
    for _ in range(10):
        plasticity.update_path(nodes, reward=0.0, confidence=0.9, contradiction=1.0)
    assert plasticity.path_score(nodes) < high


def test_low_confidence_write_is_gated():
    plasticity = PathPlasticity()
    updated = plasticity.update_path(["a", "b"], reward=0.2, confidence=0.1)
    assert updated is False
    assert plasticity.edge_count() == 0


def test_export_load_roundtrip():
    plasticity = PathPlasticity()
    plasticity.update_path(["a", "b", "c"], reward=0.8, confidence=0.9)
    state = plasticity.export_state()

    restored = PathPlasticity()
    added = restored.load_state(state)
    assert added == 2
    assert abs(restored.path_score(["a", "b", "c"]) - plasticity.path_score(["a", "b", "c"])) < 1e-6
