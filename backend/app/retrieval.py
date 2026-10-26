"""Query embedding → semantic search → database lookup, without any language generation."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import joinedload, sessionmaker

from app.database import Chunk, Document
from app.embeddings import Embedder
from app.errors import DocumentNotFound
from app.schemas import SearchHit
from app.vector_store import FaissStore

logger = logging.getLogger(__name__)


def hit_from_chunk(chunk: Chunk, score: float) -> SearchHit:
    """
    Join a retrieved chunk and its score into a complete API result with original source
    locations.
    """
    return SearchHit(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        text=chunk.text,
        score=score,
        filename=chunk.document.filename,
        page=chunk.page,
        paragraph_start=chunk.paragraph_start,
        paragraph_end=chunk.paragraph_end,
        line_start=chunk.line_start,
        line_end=chunk.line_end,
    )


class RetrievalService:
    """Keep semantic retrieval independently observable and testable through /api/search."""

    def __init__(self, sessions: sessionmaker, embedder: Embedder, store: FaissStore):
        """Receive metadata access, query embeddings, and a shared persisted vector index."""
        self.sessions, self.embedder, self.store = sessions, embedder, store

    def search(self, query: str, document_ids: list[int] | None, top_k: int) -> list[SearchHit]:
        """
        Embed a question and retrieve the best passages strictly within the requested
        documents.
        """
        logger.info("Query received: characters=%d", len(query))
        if document_ids == []:
            return []
        with self.store.lock, self.sessions() as session:
            statement = select(Chunk.id)
            if document_ids is not None:
                requested = set(document_ids)
                found = set(session.scalars(select(Document.id).where(Document.id.in_(requested))))
                if requested != found:
                    raise DocumentNotFound(
                        "Some selected documents no longer exist. Refresh the list."
                    )
                statement = statement.where(Chunk.document_id.in_(requested))
            allowed = set(session.scalars(statement))
            if not allowed:
                return []
            vector = self.embedder.embed([query])
            logger.info("Query embedding created")
            matches = self.store.search(vector, top_k, allowed)
            chunks = session.scalars(
                select(Chunk)
                .options(joinedload(Chunk.document))
                .where(Chunk.id.in_([chunk_id for chunk_id, _ in matches]))
            )
            by_id = {chunk.id: chunk for chunk in chunks}
            hits = [hit_from_chunk(by_id[chunk_id], score) for chunk_id, score in matches]
        logger.info("%d chunks retrieved", len(hits))
        return hits
