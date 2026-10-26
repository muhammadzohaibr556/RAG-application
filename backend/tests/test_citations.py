"""Citations must come from retrieved metadata even when a model produces invalid IDs."""

from unittest.mock import Mock

import pytest

from app.chat import ChatService
from app.citations import build_citations
from app.errors import ProviderError
from app.llm import ModelAnswer
from app.prompts import NOT_FOUND, build_prompt
from app.schemas import SearchHit


def hit():
    return SearchHit(
        chunk_id=42,
        document_id=1,
        filename="permit.pdf",
        page=4,
        text="Inspection occurs before occupancy.",
        score=0.91,
    )


def test_citation_metadata_and_deduplication():
    sources = build_citations([hit()], [42, 42])
    assert len(sources) == 1
    assert sources[0].filename == "permit.pdf" and sources[0].page == 4
    assert sources[0].excerpt == hit().text and sources[0].citation == 1
    with pytest.raises(ProviderError, match="unknown source"):
        build_citations([hit()], [999])


def test_chat_verified_labels_and_unsupported_answers():
    retrieval = Mock()
    retrieval.search.return_value = [hit()]
    model = Mock()
    model.answer.return_value = ModelAnswer(answer="Before occupancy.", source_ids=[42])
    chat = ChatService(retrieval, model)
    response = chat.query("When?", None, 5)
    assert response.answer == "Before occupancy. [1]"
    assert response.sources[0].chunk_id == 42
    model.answer.return_value = ModelAnswer(answer="Unsupported claim", source_ids=[])
    assert chat.query("When?", None, 5).answer == NOT_FOUND
    model.reset_mock()
    retrieval.search.return_value = []
    assert chat.query("When?", [], 5).sources == []
    model.answer.assert_not_called()


def test_prompt_contains_only_retrieved_text_and_ids():
    prompt = build_prompt("When?", [hit()])
    assert '"source_id": 42' in prompt and hit().text in prompt
    assert "permit.pdf" not in prompt
