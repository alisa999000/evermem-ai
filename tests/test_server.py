import json
import os

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from evermem.server.app import create_app  # noqa: E402
from evermem.server.config import ServerConfig  # noqa: E402
from evermem.server.service import pack_sources  # noqa: E402
from evermem.types import Claim, MemoryPack, ScoredClaim  # noqa: E402


@pytest.fixture
def client(tmp_path):
    cfg = ServerConfig(
        db_path=tmp_path / "test.db",
        host="127.0.0.1",
        port=8080,
        chat_model="",
        extract_model="",
        embed_model="",
        ollama_url="http://127.0.0.1:11434",
        default_user="test",
        api_key="",
        static_dir=__import__("pathlib").Path(__file__).resolve().parents[1]
        / "evermem"
        / "server"
        / "static",
    )
    app = create_app(cfg)
    with TestClient(app) as tc:
        yield tc


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_remember_and_profile(client):
    r = client.post("/api/remember", json={"text": "My name is Alex", "session_id": "s1"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s1"
    assert body["claims_added"] >= 1
    prof = client.get("/api/profile")
    assert prof.status_code == 200
    assert any("alex" in str(c["value"]).lower() for c in prof.json()["claims"])


def test_chat_recall_only(client):
    client.post("/api/remember", json={"text": "I live in Minsk", "session_id": "s2"})
    r = client.post(
        "/api/chat",
        json={"message": "where do I live?", "session_id": "s2", "use_llm": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert "[MEMORY]" in data["memory_prompt"]
    assert data["query_profile"] in {"general", "count", "temporal", "order", "recommend"}
    assert data["sources"]
    assert any("minsk" in s["snippet"].lower() for s in data["sources"])


def test_chat_stream_recall_only(client):
    client.post("/api/remember", json={"text": "I live in Minsk", "session_id": "s3"})
    r = client.post(
        "/api/chat/stream",
        json={"message": "where do I live?", "session_id": "s3", "use_llm": False},
    )
    assert r.status_code == 200
    events = []
    for line in r.text.split("\n"):
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload != "[DONE]":
                events.append(json.loads(payload))
    types = {e["type"] for e in events}
    assert "session" in types
    assert "meta" in types
    assert "token" in types
    assert "done" in types
    meta = next(e for e in events if e["type"] == "meta")
    assert meta["sources"]
    assert any("minsk" in s["snippet"].lower() for s in meta["sources"])


def test_pack_sources():
    pack = MemoryPack(
        query="test",
        claims=[
            ScoredClaim(
                claim=Claim(
                    id=1,
                    user_id="u",
                    subject="Alex",
                    predicate="location",
                    value="Minsk",
                    source_session="s1",
                ),
                score=0.9,
            )
        ],
    )
    sources = pack_sources(pack)
    assert len(sources) == 1
    assert sources[0]["type"] == "claim"
    assert sources[0]["snippet"] == "Minsk"


def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "evermem" in r.text.lower()


def test_api_key_required(tmp_path):
    cfg = ServerConfig(
        db_path=tmp_path / "auth.db",
        host="127.0.0.1",
        port=8080,
        chat_model="",
        extract_model="",
        embed_model="",
        ollama_url="http://127.0.0.1:11434",
        default_user="test",
        api_key="secret",
        static_dir=tmp_path,
    )
    app = create_app(cfg)
    with TestClient(app) as client:
        assert client.get("/api/profile").status_code == 401
        r = client.get("/api/profile", headers={"X-API-Key": "secret"})
        assert r.status_code == 200
