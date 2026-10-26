"""Explicit API contracts make raw retrieval and generated answers easy to compare."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

PositiveId = Annotated[int, Field(gt=0)]


class DocumentView(BaseModel):
    """Expose completed ingestion metadata without returning every stored chunk."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    file_type: str
    size_bytes: int
    chunk_count: int
    created_at: datetime


class QueryOptions(BaseModel):
    """Scope retrieval: omitted/null document IDs mean all; an empty list means none."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    document_ids: list[PositiveId] | None = Field(default=None, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class SearchRequest(QueryOptions):
    """Accept a semantic search question without asking an LLM to generate anything."""

    query: str = Field(min_length=1, max_length=2000)


class ChatRequest(QueryOptions):
    """Accept one independent grounded question; conversation history is not sent to the model."""

    question: str = Field(min_length=1, max_length=2000)


class Location(BaseModel):
    """Store citation coordinates supplied by extraction, never invented by the language model."""

    filename: str
    page: int | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None


class SearchHit(Location):
    """A database passage joined to its FAISS cosine similarity and stable IDs."""

    chunk_id: int
    document_id: int
    text: str
    score: float


class SearchResponse(BaseModel):
    """Return inspectable retrieval results before any prompt or LLM step."""

    query: str
    results: list[SearchHit]


class Source(Location):
    """A numbered citation whose location and excerpt are copied from a retrieved database chunk."""

    citation: int
    chunk_id: int
    document_id: int
    excerpt: str
    score: float


class ChatResponse(BaseModel):
    """Return a grounded answer and application-generated, expandable sources."""

    answer: str
    sources: list[Source]
