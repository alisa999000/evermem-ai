# evermem Server

On-prem web chat + API over the evermem memory engine.

## Quick start (local)

```bash
pip install -e ".[server,pdf]"
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

export EVERMEM_DB=./server_memory.db
export EVERMEM_OLLAMA_URL=http://localhost:11434
evermem-server
```

Open http://127.0.0.1:8080

## Docker (server + Ollama)

```bash
cd docker
docker compose up --build
```

First run, pull models inside Ollama container:

```bash
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| EVERMEM_DB | ~/.evermem/memory.db | SQLite path |
| EVERMEM_PORT | 8080 | HTTP port |
| EVERMEM_CHAT_MODEL | qwen2.5:7b | Ollama model for answers |
| EVERMEM_EXTRACT_MODEL | (same as chat) | Extraction at ingest |
| EVERMEM_EMBED_MODEL | (empty) | Ollama embeddings; empty = built-in hash |
| EVERMEM_OLLAMA_URL | http://localhost:11434 | Ollama base URL |
| EVERMEM_API_KEY | (empty) | Optional Bearer / X-API-Key |

## API

- `GET /api/health`
- `GET /api/profile`
- `POST /api/remember` JSON `{text, session_id?, role?}`
- `POST /api/chat` JSON `{message, session_id?, use_llm?}`
- `POST /api/upload` multipart file + session_id
- `POST /api/feedback` JSON `{helpful, session_id?}`
