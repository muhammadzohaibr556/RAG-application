"""Persist exact cosine search in FAISS, using database chunk IDs as vector IDs."""

import fcntl
import json
import logging
import os
from pathlib import Path
from threading import RLock

import faiss
import numpy as np

from app.errors import StorageError

logger = logging.getLogger(__name__)


class FaissStore:
    """
    Own a single-process ID-mapped index; serialize mutations and atomically replace
    snapshots.
    """

    def __init__(self, directory: Path, dimensions: int, model: str):
        """Load a compatible index or create an empty one before the API accepts requests."""
        self.directory = directory
        self.dimensions = dimensions
        self.lock = RLock()
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "index.faiss"
        self._process_lock = (directory / "writer.lock").open("a")
        try:
            fcntl.flock(self._process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._load(model)
        except Exception as exc:
            self.close()
            if isinstance(exc, StorageError):
                raise
            raise StorageError(
                "Cannot open FAISS storage. Check permissions and run exactly one API worker."
            ) from exc

    def _load(self, model: str) -> None:
        """
        Check the persisted embedding fingerprint to prevent mixing incompatible vector
        spaces.
        """
        manifest = self.directory / "embedding.json"
        expected = {"model": model, "dimensions": self.dimensions}
        if self.path.exists() and not manifest.exists():
            raise StorageError(
                "FAISS embedding metadata is missing. Restore the matching index and metadata."
            )
        if manifest.exists() and json.loads(manifest.read_text()) != expected:
            raise StorageError(
                "Embedding settings changed. Restore the original settings "
                "or re-ingest into fresh storage."
            )
        self.index = (
            faiss.read_index(str(self.path))
            if self.path.exists()
            else faiss.IndexIDMap2(faiss.IndexFlatIP(self.dimensions))
        )
        if self.index.d != self.dimensions or not isinstance(self.index, faiss.IndexIDMap2):
            raise StorageError("FAISS index type or dimensions do not match this application.")
        if not manifest.exists():
            temporary = manifest.with_suffix(".tmp")
            temporary.write_text(json.dumps(expected))
            os.replace(temporary, manifest)
        logger.info("FAISS loaded: %d vectors", self.index.ntotal)

    def close(self) -> None:
        """Release the process lock during shutdown so a replacement API can open the index."""
        self._process_lock.close()

    def ids(self) -> set[int]:
        """Return the vector IDs for comparing FAISS with the relational chunk table."""
        with self.lock:
            return set(map(int, faiss.vector_to_array(self.index.id_map)))

    def _matrix(self, vectors: np.ndarray) -> np.ndarray:
        """Validate and L2-normalize a copy; inner products then equal cosine similarity."""
        matrix = np.array(vectors, dtype=np.float32, order="C", copy=True)
        if matrix.ndim != 2 or matrix.shape[1] != self.dimensions:
            raise StorageError("Vector dimensions do not match the FAISS index.")
        if not np.isfinite(matrix).all() or (np.linalg.norm(matrix, axis=1) == 0).any():
            raise StorageError("Cannot index an invalid or zero-length vector.")
        faiss.normalize_L2(matrix)
        return matrix

    def _persist(self, candidate: faiss.IndexIDMap2) -> None:
        """Write/fsync a new snapshot, then replace the old file before publishing it in memory."""
        temporary = self.path.with_suffix(".tmp")
        try:
            faiss.write_index(candidate, str(temporary))
            with temporary.open("rb") as file:
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        except Exception as exc:
            raise StorageError(
                "Could not save the FAISS index. Check disk space and permissions."
            ) from exc
        self.index = candidate

    def add(self, ids: list[int], vectors: np.ndarray) -> None:
        """Persist new vectors under chunk primary keys before committing their database rows."""
        with self.lock:
            matrix = self._matrix(vectors)
            if len(ids) != len(matrix) or len(set(ids)) != len(ids) or self.ids().intersection(ids):
                raise StorageError("FAISS requires one unique, unused chunk ID per vector.")
            candidate = faiss.clone_index(self.index)
            candidate.add_with_ids(matrix, np.asarray(ids, dtype=np.int64))
            self._persist(candidate)
            logger.info("%d vectors added to FAISS", len(ids))

    def remove(self, ids: list[int]) -> None:
        """
        Persist removal after relational deletion; stale vectors are never used without
        DB rows.
        """
        if not ids:
            return
        with self.lock:
            candidate = faiss.clone_index(self.index)
            candidate.remove_ids(np.asarray(ids, dtype=np.int64))
            self._persist(candidate)
            logger.info("%d vectors removed from FAISS", len(ids))

    def reconcile(self, database_ids: set[int]) -> None:
        """
        Remove crash-left orphan vectors, but refuse startup when database chunks lack
        vectors.
        """
        with self.lock:
            indexed = self.ids()
            if database_ids - indexed:
                raise StorageError(
                    "Database chunks are missing from FAISS. "
                    "Restore both volumes from the same backup or re-ingest."
                )
            self.remove(list(indexed - database_ids))

    def search(
        self, vector: np.ndarray, top_k: int, allowed_ids: set[int]
    ) -> list[tuple[int, float]]:
        """
        Return the best eligible IDs and cosine scores, including exact document-scope
        filtering.
        """
        with self.lock:
            if not allowed_ids or not self.index.ntotal:
                return []
            query = self._matrix(vector)
            if len(query) != 1:
                raise ValueError("Search expects exactly one query vector.")
            # shortcut: rank all vectors for correct filtered top-k; use FAISS selectors at scale.
            scores, ids = self.index.search(query, self.index.ntotal)
            results = [
                (int(chunk_id), float(score))
                for chunk_id, score in zip(ids[0], scores[0], strict=True)
                if int(chunk_id) in allowed_ids
            ][:top_k]
            logger.info("FAISS search performed: %d matches", len(results))
            return results
