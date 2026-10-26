"""Orchestrate upload → extract → normalize → chunk → embed → FAISS and PostgreSQL."""

import logging
from dataclasses import asdict

from fastapi import UploadFile
from sqlalchemy.orm import sessionmaker

from app.chunking import chunk_units
from app.config import Settings
from app.database import Chunk, Document
from app.embeddings import Embedder
from app.errors import DocumentNotFound, InvalidUpload, StorageError
from app.extraction import extract
from app.normalization import normalize
from app.uploads import read_upload
from app.vector_store import FaissStore

logger = logging.getLogger(__name__)


class IngestionService:
    """
    Coordinate explicit stages while keeping parsers, models, and storage independently
    testable.
    """

    def __init__(
        self, settings: Settings, sessions: sessionmaker, embedder: Embedder, store: FaissStore
    ):
        """Receive pipeline dependencies; no hidden global client or vector database is used."""
        self.settings, self.sessions = settings, sessions
        self.embedder, self.store = embedder, store

    def ingest(self, upload: UploadFile) -> Document:
        """
        Process one file synchronously; return a document only after its vectors and
        metadata persist.
        """
        filename, extension, content = read_upload(
            upload, self.settings.max_upload_mb * 1024 * 1024
        )
        units = normalize(extract(content, extension, self.settings.max_extracted_chars))
        drafts = chunk_units(units, self.settings.chunk_size, self.settings.chunk_overlap)
        if not drafts:
            raise InvalidUpload("No usable text remained after normalization.")
        vectors = self.embedder.embed([draft.text for draft in drafts])
        with self.store.lock, self.sessions() as session:
            document = Document(
                filename=filename,
                file_type=extension[1:],
                size_bytes=len(content),
                chunk_count=len(drafts),
                chunks=[Chunk(**asdict(draft)) for draft in drafts],
            )
            session.add(document)
            session.flush()  # PostgreSQL assigns the chunk IDs before FAISS uses them.
            self.store.add([chunk.id for chunk in document.chunks], vectors)
            session.commit()
            # A crash before commit leaves only orphan vectors; startup safely removes those.
        logger.info("Document processing completed: document_id=%d", document.id)
        return document

    def delete(self, document_id: int) -> None:
        """
        Commit metadata deletion first, then clean vectors; retrieval ignores orphan
        vector IDs.
        """
        with self.store.lock, self.sessions() as session:
            document = session.get(Document, document_id)
            if document is None:
                raise DocumentNotFound("This document no longer exists. Refresh the document list.")
            ids = [chunk.id for chunk in document.chunks]
            session.delete(document)
            session.commit()
            try:
                self.store.remove(ids)
            except StorageError:
                logger.exception(
                    "Document deleted; orphan FAISS vectors will be removed at startup"
                )
        logger.info("Document deleted: document_id=%d", document_id)
