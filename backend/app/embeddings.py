"""Embedding boundary: convert text into numeric meaning vectors without a RAG framework."""

import logging
from typing import Protocol

import numpy as np
from openai import OpenAI, OpenAIError

from app.config import Settings
from app.errors import ProviderError

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Small seam allowing retrieval tests to supply vectors without network calls."""

    def embed(self, texts: list[str]) -> np.ndarray:
        """Accept texts in order and return one float32 vector per text in that same order."""
        ...


class OpenAIEmbedder:
    """Use OpenAI embeddings for both ingestion and queries so their vectors are comparable."""

    def __init__(self, settings: Settings):
        """Retain model settings; missing credentials should not prevent browsing existing files."""
        self.settings = settings

    def embed(self, texts: list[str]) -> np.ndarray:
        """Batch text through OpenAI, restore input order, and return validated numeric vectors."""
        if not texts:
            return np.empty((0, self.settings.embedding_dimensions), dtype=np.float32)
        if not self.settings.openai_api_key:
            raise ProviderError("Set OPENAI_API_KEY in .env and restart the backend.")
        vectors = []
        try:
            with OpenAI(api_key=self.settings.openai_api_key, timeout=60, max_retries=1) as client:
                # At most 32 × ~8000 tokens stays below the API's per-request token budget.
                for offset in range(0, len(texts), 32):
                    batch = texts[offset : offset + 32]
                    response = client.embeddings.create(
                        model=self.settings.embedding_model,
                        dimensions=self.settings.embedding_dimensions,
                        input=batch,
                        encoding_format="float",
                    )
                    ordered = sorted(response.data, key=lambda item: item.index)
                    if [item.index for item in ordered] != list(range(len(batch))):
                        raise ProviderError(
                            "Embedding provider returned incomplete results. Retry the upload."
                        )
                    vectors.extend(item.embedding for item in ordered)
        except OpenAIError as exc:
            logger.warning("Embedding request failed: %s", type(exc).__name__)
            raise ProviderError(
                "OpenAI embeddings failed. Check your API key, quota, and model settings."
            ) from exc
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape != (len(texts), self.settings.embedding_dimensions):
            raise ProviderError("Embedding dimensions do not match EMBEDDING_DIMENSIONS.")
        if not np.isfinite(matrix).all() or (np.linalg.norm(matrix, axis=1) == 0).any():
            raise ProviderError("Embedding provider returned invalid vectors.")
        logger.info("%d embeddings generated", len(matrix))
        return matrix
