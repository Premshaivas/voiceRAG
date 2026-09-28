from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.gzip import GZipMiddleware

from . import evaluation_model, multipart_model, session_model  # noqa: F401
from .answer_engine import GroundedAnswerEngine
from .config import Settings, settings
from .db import close_database, create_database, initialize_database
from .evaluation_routes import router as evaluation_router
from .admin_routes import router as admin_router
from .multipart_routes import router as multipart_router
from .rag_engine import RAGPipeline
from .rate_limit import RateLimiter
from .routes import router
from .s3_storage import ObjectStorage
from .session_routes import router as session_router
from .transcription import AssemblyAITranscriber
from .voice_agent import router as voice_agent_router
from .transcript_routes import router as transcript_router
from .workspace_routes import router as workspace_router
from .observability import Metrics, observe_request


def create_app(*, app_settings: Settings | None = None, pipeline: Any = None, transcriber: Any = None, answer_engine: Any = None, storage: Any = None, rate_limiter: Any = None) -> FastAPI:
    active_settings = app_settings or settings
    active_engine, session_factory = create_database(active_settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_settings.ensure_directories()
        await initialize_database(active_engine)
        if app.state.pipeline is None:
            app.state.pipeline = RAGPipeline(persist_directory=active_settings.chroma_dir)
        if app.state.transcriber is None:
            app.state.transcriber = AssemblyAITranscriber()
        if app.state.answer_engine is None:
            app.state.answer_engine = GroundedAnswerEngine(app.state.pipeline)
        if app.state.storage is None:
            app.state.storage = ObjectStorage(active_settings)
        yield
        await close_database(active_engine)

    app = FastAPI(title="VoiceRAG API", version="0.5.0", lifespan=lifespan)
    app.state.settings = active_settings
    app.state.session_factory = session_factory
    app.state.pipeline = pipeline
    app.state.transcriber = transcriber
    app.state.answer_engine = answer_engine
    app.state.storage = storage
    app.state.rate_limiter = rate_limiter or RateLimiter(active_settings.rate_limit_per_minute)
    app.state.metrics = Metrics()
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=active_settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @app.middleware("http")
    async def enforce_rate_limit(request: Request, call_next):
        if request.url.path == "/health" or request.app.state.rate_limiter.allow(request.client.host if request.client else "unknown"):
            return await call_next(request)
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded"})

    @app.middleware("http")
    async def request_observability(request: Request, call_next):
        return await observe_request(request, call_next, request.app.state.metrics)

    @app.get("/")
    async def root():
        return {"service": "VoiceRAG API", "status": "ok"}

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "voicerag"}

    @app.get("/health/ready")
    async def readiness(request: Request):
        required = ("pipeline", "transcriber", "answer_engine", "storage")
        missing = [name for name in required if getattr(request.app.state, name, None) is None]
        if missing:
            return JSONResponse(status_code=503, content={"status": "not_ready", "missing": missing})
        return {"status": "ready", "service": "voicerag", "vector_backend": request.app.state.settings.vector_backend}

    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request):
        return Response(content=request.app.state.metrics.prometheus(), media_type="text/plain; version=0.0.4")

    app.include_router(router)
    app.include_router(multipart_router)
    app.include_router(session_router)
    app.include_router(voice_agent_router)
    app.include_router(evaluation_router)
    app.include_router(transcript_router)
    app.include_router(admin_router)
    app.include_router(workspace_router)
    return app


app = create_app()
