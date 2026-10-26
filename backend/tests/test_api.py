"""Exercise the entire HTTP pipeline with real extraction, SQL, and FAISS but fake model calls."""

import json
import os
from io import BytesIO
from uuid import uuid4

import numpy as np
import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import Settings
from app.errors import ProviderError
from app.llm import ModelAnswer
from app.main import create_app
from app.prompts import NOT_FOUND


class FakeEmbedder:
    """Deterministic fixture vectors; not a substitute for semantic embeddings in production."""

    def embed(self, texts):
        return np.array([[1, 0, 0] for _ in texts], dtype=np.float32)


class FakeModel:
    """Use the supplied context's actual ID so citation wiring is exercised end to end."""

    def answer(self, prompt):
        passage = json.loads(prompt)["passages"][0]
        return ModelAnswer(
            answer="Inspection is required before occupancy.", source_ids=[passage["source_id"]]
        )


@pytest.fixture
def settings(tmp_path):
    database_url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'metadata.db'}")
    engine = None
    schema = f"test_{uuid4().hex}"
    if database_url.startswith("postgresql"):
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        database_url = (
            make_url(database_url)
            .update_query_dict({"options": f"-csearch_path={schema}"})
            .render_as_string(hide_password=False)
        )
    yield Settings(
        database_url=database_url,
        faiss_directory=tmp_path / "faiss",
        embedding_dimensions=3,
        embedding_model="test-only",
        max_upload_mb=1,
        openai_api_key="",
    )
    if engine is not None:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


def upload(client, content=b"Permit terms\n\nInspection is required before occupancy."):
    return client.post(
        "/api/documents/upload", files={"file": ("permit.txt", content, "text/plain")}
    )


def test_full_pipeline_and_restart(settings):
    app = create_app(settings, FakeEmbedder(), FakeModel())
    with TestClient(app) as client:
        assert client.get("/health").json()["indexed_chunks"] == 0
        result = upload(client)
        assert result.status_code == 201, result.text
        document = result.json()
        assert document["chunk_count"] == 1
        search = client.post(
            "/api/search", json={"query": "When?", "document_ids": [document["id"]]}
        )
        hit = search.json()["results"][0]
        assert hit["line_start"] == 1 and hit["line_end"] == 3
        answer = client.post("/api/chat/query", json={"question": "When?"}).json()
        assert answer["answer"].endswith("[1]")
        assert answer["sources"][0]["chunk_id"] == hit["chunk_id"]
        assert len(client.get("/api/documents").json()) == 1
    with TestClient(create_app(settings, FakeEmbedder(), FakeModel())) as client:
        assert client.get("/health").json()["indexed_chunks"] == 1
        assert client.post("/api/search", json={"query": "When?"}).json()["results"]
        assert client.delete(f"/api/documents/{document['id']}").status_code == 204
        assert client.get("/api/documents").json() == []
        assert client.get("/health").json()["indexed_chunks"] == 0
        assert client.post("/api/chat/query", json={"question": "When?"}).json() == {
            "answer": NOT_FOUND,
            "sources": [],
        }
        assert client.delete(f"/api/documents/{document['id']}").status_code == 404


def test_bad_inputs_and_provider_failure(settings):
    with TestClient(create_app(settings, FakeEmbedder(), FakeModel())) as client:
        assert client.post("/api/search", json={"query": "   "}).status_code == 422
        assert client.post("/api/search", json={"query": "hi", "top_k": 0}).status_code == 422
        assert (
            client.post(
                "/api/chat/query", json={"question": "hi", "document_ids": [99]}
            ).status_code
            == 404
        )
        assert upload(client, b"a" * (1024 * 1024 + 1)).status_code == 413
        assert (
            client.post(
                "/api/documents/upload", files={"file": ("a.exe", b"abc", "text/plain")}
            ).status_code
            == 400
        )
        assert client.get("/api/documents").json() == []
    with TestClient(create_app(settings)) as client:
        failed = upload(client)
        assert failed.status_code == 503
        assert failed.json()["error"]["code"] == "provider_unavailable"
        assert client.get("/api/documents").json() == []
        assert client.get("/health").json()["indexed_chunks"] == 0


def test_search_never_calls_llm(settings):
    class FailingModel:
        def answer(self, prompt):
            raise ProviderError("LLM must not run")

    with TestClient(create_app(settings, FakeEmbedder(), FailingModel())) as client:
        assert upload(client).status_code == 201
        assert client.post("/api/search", json={"query": "inspection"}).status_code == 200
        assert client.post("/api/chat/query", json={"question": "inspection"}).status_code == 503


def test_chunked_upload_limit(settings):
    boundary = "test-boundary"

    def stream():
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode()
        for _ in range(20):
            yield b"x" * 65536
        yield f"\r\n--{boundary}--\r\n".encode()

    with TestClient(create_app(settings, FakeEmbedder(), FakeModel())) as client:
        result = client.post(
            "/api/documents/upload",
            content=stream(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        assert result.status_code == 413, result.text
        assert client.get("/api/documents").json() == []


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_binary_document_upload_and_citation(settings, extension):
    if extension == "pdf":
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((72, 72), "Inspection before occupancy.")
            content = pdf.tobytes()
        mime, coordinate = "application/pdf", "page"
    else:
        document = Document()
        document.add_paragraph("Inspection before occupancy.")
        stream = BytesIO()
        document.save(stream)
        content = stream.getvalue()
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        coordinate = "paragraph_start"
    with TestClient(create_app(settings, FakeEmbedder(), FakeModel())) as client:
        result = client.post(
            "/api/documents/upload", files={"file": (f"permit.{extension}", content, mime)}
        )
        assert result.status_code == 201, result.text
        answer = client.post("/api/chat/query", json={"question": "When?"}).json()
        assert answer["sources"][0][coordinate] == 1
        assert answer["sources"][0]["filename"] == f"permit.{extension}"


def test_failed_index_write_rolls_back_document(settings, monkeypatch):
    from app.errors import StorageError

    app = create_app(settings, FakeEmbedder(), FakeModel())
    with TestClient(app) as client:

        def fail(*args):
            raise StorageError("Disk full")

        monkeypatch.setattr(app.state.store, "add", fail)
        assert upload(client).status_code == 503
        assert client.get("/api/documents").json() == []
        assert client.get("/health").json()["indexed_chunks"] == 0
