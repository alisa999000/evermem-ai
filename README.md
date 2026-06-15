# evermem

[![PyPI](https://img.shields.io/pypi/v/evermem-ai)](https://pypi.org/project/evermem-ai/)
[![Python](https://img.shields.io/pypi/pyversions/evermem-ai)](https://pypi.org/project/evermem-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![GitHub](https://img.shields.io/github/stars/alisa999000/evermem-ai?style=social)](https://github.com/alisa999000/evermem-ai)

**Local-first eternal memory for any LLM.** Conflict-aware facts, temporal validity windows, trust scoring, and retrieval that learns from feedback. Pure Python stdlib, zero dependencies in the core, SQLite under the hood, your data never leaves your machine.

**Install:** `pip install evermem-ai` | **Repo:** [github.com/alisa999000/evermem-ai](https://github.com/alisa999000/evermem-ai) | **PyPI:** [pypi.org/project/evermem-ai](https://pypi.org/project/evermem-ai/)

LLMs forget everything between sessions. Cloud memory services fix that by shipping your users' most personal data to someone else's API, and still get the hard parts wrong: they return facts that were contradicted weeks ago, add seconds of network latency to every turn, and break the moment you are offline. **evermem** runs entirely on your hardware and models memory as a *lifecycle*, not a pile of vectors:

- **Temporal validity** - "lived in Minsk" isn't deleted when the user moves to Warsaw; it's superseded with a validity window. Recall returns the current fact, history is never lost.
- **Conflict awareness** - contradictory facts are detected, surfaced to the LLM ("verify with the user"), and resolved by repetition and trust, not by last-write-wins.
- **Trust scoring** - every claim carries trust that grows with confirmation and decays with contradiction.
- **Retrieval plasticity** - recall paths that led to helpful answers are reinforced; noisy paths decay. Memory gets better the more you use it.
- **Four memory layers** - working (recent turns), episodic (conversation episodes), semantic (stabilized claims), conflict (open contradictions) - modeled on how biological memory actually works.

No API keys. No Docker. No graph database to operate. One SQLite file.

## Install

```bash
pip install evermem-ai            # core, zero dependencies
pip install "evermem-ai[pdf]"     # + PDF ingestion (pypdf)
```

The import name is `evermem`. Python 3.10+.

## Quickstart

```python
from evermem import EverMem

mem = EverMem("memory.db")  # rule-based extraction, no LLM needed

# Session 1
mem.observe("Меня зовут Алекс, я живу в Минске", session_id="s1")
mem.observe("I love black coffee", session_id="s1")

# Weeks later, a completely new session
pack = mem.recall("what do we know about the user?", session_id="s2")
print(pack.as_prompt())
# [MEMORY]
# Known facts (most relevant first):
# - user | name = алекс (trust 0.85, seen x1)
# - user | location = минске (trust 0.85, seen x1)
# - user | likes = black coffee (trust 0.75, seen x1)
# [/MEMORY]

mem.feedback(True, session_id="s2")  # reinforce what was useful
```

Inject `pack.as_prompt()` into any LLM's system prompt - OpenAI, Claude, or a 7B model running on your laptop. Use `pack.as_prompt(budget_chars=4000)` to hard-cap the pack size and keep prompts lean.

Working chat loops: [`examples/chat_ollama.py`](examples/chat_ollama.py) (fully offline) and [`examples/chat_openai.py`](examples/chat_openai.py) (any OpenAI-compatible endpoint).

## Documents: PDF, DOCX, HTML, Markdown

Feed files into the same memory; recall quotes the exact matching passages alongside conversation facts:

```python
mem.observe_file("contract.pdf")            # needs evermem-ai[pdf]
mem.observe_file("meeting_notes.md")        # txt/md/docx/html: zero dependencies

pack = mem.recall("what is the monthly rent?")
# history now contains the matching document blocks (role "document")
```

Documents are split into paragraph-aligned blocks, embedded chunk by chunk and searched exactly like past conversation turns. DOCX and HTML parsing is stdlib-only.

## Command line

Everything works from the terminal against the same database (`~/.evermem/memory.db` by default, override with `--db` or `EVERMEM_DB`):

```bash
evermem remember "we decided to ship v2 on March 3"
evermem import contract.pdf notes.md
evermem recall "when do we ship v2?"
evermem bootstrap        # session primer (call first in a new chat)
evermem profile          # everything known about the user, with trust and conflicts
evermem forget --subject user --predicate city   # invalidate a wrong fact
evermem correct user city "Warsaw"               # supersede with a correction
evermem aggregate "went to the gym"              # count matching sessions
evermem export backup.json                       # portable JSON backup
evermem stats            # database counters
evermem mcp              # run the MCP server
```

Add `--model qwen2.5:7b` to any command for LLM-powered fact extraction via Ollama, and `--embed-model nomic-embed-text` for better recall.

## evermem Server (on-prem product)

Web chat with streaming, memory sources, dark theme, PDF upload, and REST API for clients who will not integrate via Python (med centers, law firms, integrators).

```bash
pip install "evermem-ai[server,pdf]"
ollama pull qwen2.5:7b && ollama pull nomic-embed-text
evermem-server   # http://127.0.0.1:8080
```

API: `/api/chat`, `/api/chat/stream` (SSE), `/api/remember`, `/api/upload`, `/api/profile`, `/api/feedback`.

Docker (server + Ollama): see [server/README.md](server/README.md) and `docker/docker-compose.yml`.

### Rich extraction with a local LLM (Ollama)

```python
from evermem import EverMem, OllamaLLM

mem = EverMem("memory.db", llm=OllamaLLM("qwen2.5:7b"))
mem.observe("кстати, мы с женой завели кота, назвали Барсик")
# -> user | has_pet = кот барсик
```

If the LLM is down, extraction silently falls back to deterministic rules. The engine never breaks.

### Better recall with local embeddings (optional)

By default evermem uses built-in hash embeddings (zero downloads, runs anywhere). For noticeably better semantic recall, plug in any local embedding model via Ollama:

```python
from evermem import EverMem, OllamaEmbedder

mem = EverMem("memory.db", embedder=OllamaEmbedder("nomic-embed-text"))
```

Any callable `str -> list[float]` works - sentence-transformers, llama.cpp, your own model. The store handles arbitrary dimensions automatically.

### Plug into Cursor / Claude Desktop (MCP)

```json
{
  "mcpServers": {
    "evermem": {
      "command": "evermem",
      "args": ["mcp"],
      "env": { "EVERMEM_DB": "C:/Users/you/.evermem/memory.db" }
    }
  }
}
```

**Recommended agent flow** (matches what production memory MCPs like memory-mcp teach):

1. `memory_initialize` - session primer at the start of every chat
2. `memory_recall` - before answering questions about the past
3. `memory_remember` - after the user shares durable facts
4. `memory_feedback` - when recall was helpful or wrong
5. `memory_forget` / `memory_correct` - when a stored fact is poisoned or outdated

Also available: `memory_aggregate` (how many times...), `memory_import` (PDF/MD), `memory_remember_fact` (structured write), MCP resources `memory://profile` and `memory://conflicts`.

Set `EVERMEM_MODEL` and `EVERMEM_EMBED_MODEL` for local Ollama extraction and recall quality.

### LangChain / LlamaIndex

```bash
pip install "evermem-ai[langchain]"    # or [llamaindex]
```

```python
from evermem import EverMem
from evermem.integrations.langchain import EverMemChatHistory, EverMemRetriever

mem = EverMem("memory.db")
history = EverMemChatHistory(mem, session_id="app")
history.add_user_message("We ship v2 on March 3")
print(EverMemRetriever(mem, session_id="app").invoke("when do we ship?"))
```

## How it works

```
observe(text)
  └─ extractor (LLM or rules) -> claims (subject, predicate, value, exclusive)
       └─ ClaimStore (SQLite)
            ├─ same value        -> reinforce: support+1, trust ↑
            ├─ exclusive change  -> supersede: validity window closes, history kept
            └─ coexisting values -> open conflict, trust competition

recall(query)
  └─ score = 0.55·semantic + 0.15·recency + 0.20·trust + 0.10·learned_paths
       └─ MemoryPack: facts + contradictions + history timeline + episodes + recent turns

feedback(helpful)
  └─ plasticity: reward/decay retrieval paths; adjust claim trust
```

Embeddings are deterministic hash vectors (token stems + char trigrams) - robust to Russian/English morphology and typos, no model download required. The `embeddings` module is swappable for real embedding models.

## Why not just RAG?

RAG retrieves documents. Memory needs *lifecycle*: facts change, contradict each other, gain and lose credibility, and must be forgotten or superseded - not appended forever. A pure vector store will happily return "works at Acme" months after the user said they quit, because semantic similarity knows nothing about time. evermem models that lifecycle explicitly.

## Comparison

| | evermem | Mem0 | Zep / Graphiti | plain RAG |
|---|---|---|---|---|
| Runs fully offline | yes | no (LLM API for extraction) | no | depends |
| Setup | `pip install`, one file | SDK + LLM key | Docker + graph DB | DIY |
| Supersede / validity windows | yes | partial | yes (temporal graph) | no |
| Conflict surfacing to the LLM | yes | no | no | no |
| Learns from feedback | yes | no | no | no |
| Recall latency | ~0.1 s local | seconds (cloud) | seconds (cloud) | varies |
| Hardware floor | any CPU, even no ML model | cloud or GPU | server | GPU for embeddings |
| License | MIT | Apache 2.0 (cloud paid) | cloud / enterprise | - |

Honest scope: Mem0 and Zep are managed platforms with SDK ecosystems and dashboards; evermem is an engine you embed. If you want zero cloud, zero dependencies and memory lifecycle done right, that trade is the point.

## Performance

Latency on a plain CPU, zero-dependency mode (`python bench/latency.py`):

| store size | observe (p50) | recall (p50) | recall (p95) |
|---|---|---|---|
| 2,000 turns | 1.3 ms | 103 ms | 235 ms |
| 10,000 turns | 5.1 ms | 346 ms | 536 ms |

Writes never block on a network call. For comparison, independent 2026 reviews measure cloud memory services at roughly 4 s (Zep) and 7 s (Mem0) per recall round-trip.

## Benchmarks (LongMemEval)

Measured on [longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) with a **fully local stack**: `nomic-embed-text` embeddings + `qwen2.5:7b` reader/judge via Ollama. No cloud, no API keys.

| Metric | oracle (evidence only, n=500) | _s (~40 distractor sessions, n=100) |
|---|---|---|
| Evidence session recall | **99.8%** | **96.3%** |
| QA accuracy (local 7B reader) | **58.7%** | **51.1%** |
| Answer presence in pack | 44.7% | 51.1% |

Retrieval is essentially solved by the memory layer (96-100% evidence recall); the reader model sets the ceiling. Best types on the haystack: `knowledge-update` **85.7%** (temporal validity windows at work), `single-session-preference` 66.7%, `single-session-user` 61.5%.

For reference: Zep reports 63.8% on LongMemEval with a **GPT-4o reader** in the cloud. evermem reaches 51.1% with a 7B model that runs on a $300 GPU - a different point on the cost/privacy curve, fully offline. The pack hands the reader a dated timeline with pre-computed day gaps, which alone lifted temporal-reasoning QA from 4% to 40-52%.

Zero-dependency mode (hash embeddings, no Ollama at all) still achieves 71% evidence recall on the haystack - enough for edge devices where no embedding model fits.

```bash
python bench/run_longmemeval.py --data bench/data/longmemeval_s.json \
  --embed-model nomic-embed-text --qa-model qwen2.5:7b --every 5 --report bench/report_s_v3.json
python bench/analyze_errors.py --report bench/report_s_v3.json --data bench/data/longmemeval_s.json
```

Full runbook: [`bench/README.md`](bench/README.md).

## FAQ

**Does it need an internet connection or API key?** No. The core runs on the Python standard library alone. Ollama integration is optional and also local.

**Multiple users on one database?** Yes: every API call takes `user_id`, memories are strictly isolated per user.

**How do I delete a user's data (GDPR)?** Keep one database file per user and delete the file: erasure is then physical and provable, which is exactly what regulators want from on-device storage.

**What about non-English text?** The hash embedder handles Russian and English morphology out of the box; rule extraction covers both languages. Any other language works through an Ollama embedder and LLM extractor.

**Can I use my own vector model / store?** Embeddings are any `str -> list[float]` callable. The storage layer is a single SQLite file you can inspect with any SQLite client.

**Will it slow my agent down?** Recall is a local SQLite query plus vector scan: ~0.1 s at 2k turns on CPU, no network round-trip. `observe` is a few milliseconds and can run after the response is sent.

## Status & roadmap

- [x] Claim store with validity windows, conflicts, trust
- [x] Retrieval plasticity (learning from feedback)
- [x] LLM extraction (Ollama / OpenAI-compatible) with rule fallback
- [x] Pluggable embeddings (hash zero-dep default, Ollama backend, any callable)
- [x] Chunk-level turn search + dated timeline with pre-computed day gaps
- [x] Document ingestion: PDF, DOCX, HTML, Markdown, plain text
- [x] Memory lifecycle: forget, correct, purge (GDPR), provenance (source session/turn)
- [x] Session primer (`bootstrap` / `memory_initialize`) with stale-fact warnings
- [x] Multi-session aggregation (`aggregate` / `memory_aggregate`)
- [x] MCP: 10 tools + 2 resources, embed model, budget_chars, feedback loop
- [x] CLI: remember / recall / import / bootstrap / forget / correct / export / mcp
- [x] MCP server (memory for Cursor / Claude Desktop in one config line)
- [x] LongMemEval harness: retrieval metrics + QA stage (local reader + judge) + error analyzer
- [x] Multi-session: entity counters at ingest + distinct-item counts in recall
- [x] Temporal: chronological order block for which-first questions
- [x] Preferences: boosted in recall for recommend/suggest questions
- [x] Episode summarization (rule fallback; LLM when Ollama configured)
- [x] LangChain / LlamaIndex adapters (`pip install "evermem-ai[langchain]"`)
- [x] Sprint 4: memory events, assistant extract, query router (0.3.0)
- [x] **evermem Server**: FastAPI + web UI + upload + Docker (0.4.0)
- [ ] Control measurement: raw full history vs MemoryPack (context compression chart)
- [ ] Encrypted memory sync between devices (first paid feature; core stays MIT forever)

## Development

```bash
pip install -e ".[dev]"
pytest -q          # 80 tests, no network needed
python demo.py     # offline end-to-end scenario
```

MIT License.
