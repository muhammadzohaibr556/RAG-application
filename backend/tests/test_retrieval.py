"""Test real relational joins and FAISS filtering with a deterministic query embedding."""

import numpy as np
import pytest

from app.database import Chunk, Document, create_database
from app.errors import DocumentNotFound
from app.retrieval import RetrievalService
from app.vector_store import FaissStore


class QueryEmbedder:
    """Test double returning a known direction, so expected nearest neighbors are unambiguous."""

    def embed(self, texts):
        return np.array([[1, 0]] * len(texts), dtype=np.float32)


def test_document_filter_applied_before_top_k(tmp_path):
    sessions = create_database(f"sqlite:///{tmp_path / 'test.db'}")
    store = FaissStore(tmp_path / "index", 2, "test")
    with sessions() as session:
        docs = [
            Document(
                filename=f"{i}.txt",
                file_type="txt",
                size_bytes=10,
                chunks=[Chunk(text=f"passage {i}", token_count=3, line_start=2, line_end=4)],
            )
            for i in range(2)
        ]
        session.add_all(docs)
        session.commit()
        ids = [doc.chunks[0].id for doc in docs]
        selected = docs[1].id
    store.add(ids, np.array([[1, 0], [0, 1]]))
    service = RetrievalService(sessions, QueryEmbedder(), store)
    hits = service.search("inspection", [selected], 1)
    assert len(hits) == 1 and hits[0].chunk_id == ids[1]
    assert hits[0].line_start == 2 and hits[0].filename == "1.txt"
    assert service.search("inspection", [], 5) == []
    assert service.search("inspection", None, 1)[0].chunk_id == ids[0]
    with pytest.raises(DocumentNotFound):
        service.search("inspection", [999], 5)
    store.close()
    sessions.kw["bind"].dispose()
