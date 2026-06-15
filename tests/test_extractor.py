from evermem.extractor import LLMExtractor, RuleExtractor


def test_rule_extractor_russian_name_and_location():
    extractor = RuleExtractor()
    result = extractor.extract("Привет! Меня зовут Алекс, я живу в Минске")
    by_predicate = {claim.predicate: claim for claim in result.claims}
    assert by_predicate["name"].value.lower().startswith("алекс")
    assert by_predicate["name"].exclusive
    assert "минск" in by_predicate["location"].value.lower()


def test_rule_extractor_english_preference():
    extractor = RuleExtractor()
    result = extractor.extract("I love black coffee")
    assert result.claims
    claim = result.claims[0]
    assert claim.predicate == "likes"
    assert not claim.exclusive
    assert "coffee" in claim.value.lower()


def test_rule_extractor_possessive_dash():
    extractor = RuleExtractor()
    result = extractor.extract("мой любимый язык - питон")
    assert result.claims
    claim = result.claims[0]
    assert claim.subject == "user"
    assert "питон" in claim.value.lower()
    assert claim.exclusive


def test_rule_extractor_skips_questions():
    extractor = RuleExtractor()
    result = extractor.extract("Как меня зовут?")
    predicates = {claim.predicate for claim in result.claims}
    assert "name" not in predicates or not result.claims


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, system: str, user: str) -> str:
        return self.response


def test_llm_extractor_parses_strict_json():
    llm = _FakeLLM(
        '{"claims": [{"subject": "user", "predicate": "job", "value": "backend developer",'
        ' "kind": "fact", "exclusive": true}], "topic": "work"}'
    )
    extractor = LLMExtractor(llm)
    result = extractor.extract("я работаю бэкенд-разработчиком")
    assert len(result.claims) == 1
    assert result.claims[0].predicate == "job"
    assert result.claims[0].exclusive
    assert result.topic == "work"


def test_split_chunks_sentence_aligned():
    from evermem.embeddings import split_chunks

    short = split_chunks("Одно короткое сообщение.")
    assert short == ["Одно короткое сообщение."]

    long_text = "Первое предложение о погоде. " * 5 + "Номер рейса TK284. " + "Еще немного слов о сериалах. " * 5
    chunks = split_chunks(long_text, max_chars=120)
    assert len(chunks) >= 3
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert any("TK284" in chunk for chunk in chunks)


def test_llm_extractor_falls_back_on_garbage():
    llm = _FakeLLM("sorry, I cannot do that")
    extractor = LLMExtractor(llm)
    result = extractor.extract("меня зовут Анна")
    assert any(claim.predicate == "name" for claim in result.claims)
