"""evermem Server: FastAPI + web chat for on-prem deployments."""

from __future__ import annotations

import json
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ServerConfig
from .service import MemoryService

_app: FastAPI | None = None
_service: MemoryService | None = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str = ""
    use_llm: bool = True


class RememberRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    session_id: str = ""
    role: str = "user"


class FeedbackRequest(BaseModel):
    helpful: bool
    session_id: str = ""


def _session_id(raw: str) -> str:
    value = (raw or "").strip()
    return value or f"web-{uuid.uuid4().hex[:12]}"


def _auth(config: ServerConfig, authorization: str | None, x_api_key: str | None) -> None:
    if not config.api_key:
        return
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif x_api_key:
        token = x_api_key.strip()
    if token != config.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


def create_app(config: ServerConfig | None = None) -> FastAPI:
    global _app, _service
    cfg = config or ServerConfig.from_env()
    svc = MemoryService(cfg)
    _service = svc

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        svc.close()

    app = FastAPI(
        title="evermem Server",
        description="Local-first memory layer with web chat",
        version="0.4.1",
        lifespan=lifespan,
    )

    def get_cfg() -> ServerConfig:
        return cfg

    def get_svc() -> MemoryService:
        return svc

    def require_auth(
        authorization: Annotated[str | None, Header()] = None,
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> None:
        _auth(cfg, authorization, x_api_key)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "stats": svc.stats()}

    @app.get("/api/profile")
    def profile(_: None = Depends(require_auth), service: MemoryService = Depends(get_svc)) -> dict:
        return {"claims": service.profile()}

    @app.post("/api/remember")
    def remember(
        body: RememberRequest,
        _: None = Depends(require_auth),
        service: MemoryService = Depends(get_svc),
    ) -> dict:
        sid = _session_id(body.session_id)
        report = service.observe(body.text, session_id=sid, role=body.role)
        return {"session_id": sid, **report}

    @app.post("/api/chat")
    def chat(
        body: ChatRequest,
        _: None = Depends(require_auth),
        service: MemoryService = Depends(get_svc),
    ) -> dict:
        sid = _session_id(body.session_id)
        result = service.chat(body.message, session_id=sid, use_llm=body.use_llm)
        return {"session_id": sid, **result}

    @app.post("/api/chat/stream")
    def chat_stream(
        body: ChatRequest,
        _: None = Depends(require_auth),
        service: MemoryService = Depends(get_svc),
    ) -> StreamingResponse:
        sid = _session_id(body.session_id)

        def generate():
            try:
                yield f"data: {json.dumps({'type': 'session', 'session_id': sid})}\n\n"
                for event in service.chat_stream(
                    body.message,
                    session_id=sid,
                    use_llm=body.use_llm,
                ):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream; charset=utf-8",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/feedback")
    def feedback(
        body: FeedbackRequest,
        _: None = Depends(require_auth),
        service: MemoryService = Depends(get_svc),
    ) -> dict:
        sid = _session_id(body.session_id)
        count = service.feedback(body.helpful, session_id=sid)
        return {"session_id": sid, "claims_updated": count}

    @app.post("/api/upload")
    async def upload(
        _: None = Depends(require_auth),
        service: MemoryService = Depends(get_svc),
        session_id: str = "",
        file: UploadFile = File(...),
    ) -> dict:
        sid = _session_id(session_id)
        suffix = Path(file.filename or "upload.txt").suffix or ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            report = service.import_file(tmp_path, session_id=sid)
        finally:
            tmp_path.unlink(missing_ok=True)
        return {"session_id": sid, "filename": file.filename, **report}

    static_dir = cfg.static_dir
    index = static_dir / "index.html"
    if index.is_file():
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/")
        def index_page() -> FileResponse:
            return FileResponse(index)

        @app.get("/favicon.ico", include_in_schema=False)
        def favicon() -> FileResponse:
            ico = static_dir / "favicon.ico"
            if ico.is_file():
                return FileResponse(ico)
            return FileResponse(index, media_type="text/html")

    _app = app
    return app


def main() -> None:
    import uvicorn

    cfg = ServerConfig.from_env()
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()
