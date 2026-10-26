"""Thin HTTP adapters for ingestion, raw retrieval, and grounded answer services."""

from typing import Annotated

from fastapi import APIRouter, Path, Request, Response, UploadFile
from sqlalchemy import select, text

from app.database import Document
from app.schemas import ChatRequest, ChatResponse, DocumentView, SearchRequest, SearchResponse

router = APIRouter()


@router.get("/health")
def health(request: Request) -> dict[str, str | int]:
    """Check PostgreSQL and report the loaded FAISS size without calling OpenAI."""
    with request.app.state.sessions() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ok", "indexed_chunks": len(request.app.state.store.ids())}


@router.post("/api/documents/upload", response_model=DocumentView, status_code=201)
def upload_document(request: Request, file: UploadFile) -> DocumentView:
    """Return completed document metadata after the entire multipart ingestion pipeline."""
    return DocumentView.model_validate(request.app.state.ingestion.ingest(file))


@router.get("/api/documents", response_model=list[DocumentView])
def list_documents(request: Request) -> list[DocumentView]:
    """List successfully ingested documents for selection in the learning UI."""
    with request.app.state.sessions() as session:
        return [
            DocumentView.model_validate(document)
            for document in session.scalars(
                select(Document).order_by(Document.created_at.desc(), Document.id.desc())
            )
        ]


@router.delete("/api/documents/{document_id}", status_code=204)
def delete_document(request: Request, document_id: Annotated[int, Path(gt=0)]) -> Response:
    """Delete metadata and remove a document's vectors from subsequent retrieval."""
    request.app.state.ingestion.delete(document_id)
    return Response(status_code=204)


@router.post("/api/search", response_model=SearchResponse, response_model_exclude_none=True)
def search(request: Request, body: SearchRequest) -> SearchResponse:
    """Return semantic passages and cosine scores without generating an answer."""
    results = request.app.state.retrieval.search(
        body.query,
        body.document_ids,
        body.top_k or request.app.state.settings.retrieval_top_k,
    )
    return SearchResponse(query=body.query, results=results)


@router.post("/api/chat/query", response_model=ChatResponse, response_model_exclude_none=True)
def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """Run retrieval, prompt construction, generation, and trusted citation formatting."""
    return request.app.state.chat.query(
        body.question,
        body.document_ids,
        body.top_k or request.app.state.settings.retrieval_top_k,
    )
