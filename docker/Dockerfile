FROM node:20-alpine AS frontend

WORKDIR /app/web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN mkdir -p ../evermem/server/static
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY evermem ./evermem
COPY --from=frontend /app/evermem/server/static ./evermem/server/static

RUN pip install --no-cache-dir ".[server,pdf]"

ENV EVERMEM_DB=/data/memory.db
ENV EVERMEM_HOST=0.0.0.0
ENV EVERMEM_PORT=8080
ENV EVERMEM_OLLAMA_URL=http://ollama:11434
ENV EVERMEM_CHAT_MODEL=qwen2.5:7b
ENV EVERMEM_EMBED_MODEL=nomic-embed-text

EXPOSE 8080
VOLUME /data

CMD ["evermem-server"]
