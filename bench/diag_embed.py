import json
import time
import urllib.request


def post(url: str, payload: dict):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read())
    return (time.perf_counter() - t0) * 1000, data


def show(label: str, ms: float, d: dict, n: int = 1):
    total = d.get("total_duration", 0) / 1e6
    load = d.get("load_duration", 0) / 1e6
    print(f"{label}: http={ms:.0f}ms server={total:.0f}ms load={load:.0f}ms per_item={ms / n:.0f}ms")


ms, d = post("http://localhost:11434/api/embed", {"model": "nomic-embed-text", "input": "warm"})
show("warmup", ms, d)

for text in ["short one", "a much longer sentence about cars, coffee and the weather in the city today"]:
    ms, d = post("http://localhost:11434/api/embed", {"model": "nomic-embed-text", "input": text})
    show(f"single ({len(text)} chars)", ms, d)

batch = ["batch sentence number " + str(i) for i in range(32)]
ms, d = post("http://localhost:11434/api/embed", {"model": "nomic-embed-text", "input": batch})
show("batch x32", ms, d, n=32)
