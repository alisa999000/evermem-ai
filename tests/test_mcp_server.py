from evermem import EverMem
from evermem.mcp_server import McpServer


def make_server():
    return McpServer(memory=EverMem())


def test_initialize_and_tools_list():
    server = make_server()
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "evermem"

    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {tool["name"] for tool in tools["result"]["tools"]}
    assert "memory_initialize" in names
    assert "memory_recall" in names
    assert "memory_forget" in names
    assert "memory_feedback" in names
    assert "memory_aggregate" in names


def test_initialize_primer_and_recall_roundtrip():
    server = make_server()
    primer = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "memory_initialize", "arguments": {}},
        }
    )
    assert "[MEMORY_PRIMER]" in primer["result"]["content"][0]["text"]

    save = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "memory_remember",
                "arguments": {"text": "меня зовут Алекс, я живу в Минске", "session_id": "test"},
            },
        }
    )
    assert "remembered" in save["result"]["content"][0]["text"]

    recall = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "memory_recall",
                "arguments": {"query": "где живет пользователь?", "session_id": "other", "budget_chars": 2000},
            },
        }
    )
    text = recall["result"]["content"][0]["text"].lower()
    assert "минск" in text
    assert len(recall["result"]["content"][0]["text"]) <= 2000


def test_forget_correct_and_aggregate():
    server = make_server()
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "tools/call",
            "params": {
                "name": "memory_remember_fact",
                "arguments": {"subject": "user", "predicate": "city", "value": "минск"},
            },
        }
    )
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 21,
            "method": "tools/call",
            "params": {
                "name": "memory_correct",
                "arguments": {
                    "subject": "user",
                    "predicate": "city",
                    "new_value": "варшава",
                    "session_id": "fix",
                },
            },
        }
    )
    profile = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 22,
            "method": "tools/call",
            "params": {"name": "memory_profile", "arguments": {}},
        }
    )
    assert "варшава" in profile["result"]["content"][0]["text"]

    agg = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "tools/call",
            "params": {
                "name": "memory_remember",
                "arguments": {"text": "ходил в зал", "session_id": "a"},
            },
        }
    )
    assert "remembered" in agg["result"]["content"][0]["text"]
    count = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "tools/call",
            "params": {"name": "memory_aggregate", "arguments": {"query": "зал"}},
        }
    )
    assert "matching turn" in count["result"]["content"][0]["text"].lower()


def test_resources_list_and_read():
    server = make_server()
    resources = server.handle({"jsonrpc": "2.0", "id": 30, "method": "resources/list"})
    uris = {item["uri"] for item in resources["result"]["resources"]}
    assert "memory://profile" in uris

    read = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "resources/read",
            "params": {"uri": "memory://profile"},
        }
    )
    assert "contents" in read["result"]


def test_notifications_are_silent_and_unknown_method_errors():
    server = make_server()
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    error = server.handle({"jsonrpc": "2.0", "id": 5, "method": "no/such"})
    assert error["error"]["code"] == -32601


def test_unknown_tool_reports_tool_error():
    server = make_server()
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        }
    )
    assert response["result"]["isError"] is True
