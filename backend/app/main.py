"""Wire the explicit pipeline and translate internal failures at the API boundary."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
from app.chat import ChatService
from app.config import Settings
from app.database import Chunk, create_database
from app.embeddings import Embedder, OpenAIEmbedder
from app.errors import PipelineError
from app.ingestion import IngestionService
from app.llm import LanguageModel, OpenAILanguageModel
from app.middleware import UploadLimitMiddleware
from app.retrieval import RetrievalService
from app.vector_store import FaissStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


def create_app(
    settings: Settings | None = None,
    embedder: Embedder | None = None,
    model: LanguageModel | None = None,
) -> FastAPI:
    """Assemble production dependencies or test doubles without changing pipeline behavior."""
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Load DB/index, reconcile interrupted writes, and close resources on shutdown."""
        sessions = create_database(config.database_url)
        store = None
        try:
            store = FaissStore(
                config.faiss_directory, config.embedding_dimensions, config.embedding_model
            )
            with sessions() as session:
                store.reconcile(set(session.scalars(select(Chunk.id))))
            embeddings = embedder or OpenAIEmbedder(config)
            app.state.settings, app.state.sessions, app.state.store = config, sessions, store
            app.state.ingestion = IngestionService(config, sessions, embeddings, store)
            app.state.retrieval = RetrievalService(sessions, embeddings, store)
            app.state.chat = ChatService(app.state.retrieval, model or OpenAILanguageModel(config))
            yield
        finally:
            if store is not None:
                store.close()
            sessions.kw["bind"].dispose()

    app = FastAPI(title="RAG Learning Lab", version="1.0.0", lifespan=lifespan)
    app.add_middleware(UploadLimitMiddleware, max_bytes=config.max_upload_mb * 1024 * 1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )
    register_errors(app)
    app.include_router(router)
    return app


def register_errors(app: FastAPI) -> None:
    """Register safe errors without exposing document text, keys, or SQL parameters."""

    @app.exception_handler(PipelineError)
    async def pipeline_error(request: Request, exc: PipelineError) -> JSONResponse:
        """Expose a service's actionable public message without its internal cause."""
        return JSONResponse(
            status_code=exc.status_code, content={"error": {"code": exc.code, "message": str(exc)}}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Explain malformed request fields without reflecting uploaded contents."""
        fields = [".".join(map(str, error["loc"])) for error in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Check request fields: " + ", ".join(fields),
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        """Translate storage failures without exposing SQL parameters or document text."""
        logger.error("Database operation failed: %s", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "database_unavailable",
                    "message": "Database unavailable. Check PostgreSQL and retry.",
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Keep unexpected internals off the wire while logging the exception type."""
        logger.error("Unexpected pipeline failure: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Processing failed unexpectedly. Check backend logs and retry.",
                }
            },
        )


app = create_app()
