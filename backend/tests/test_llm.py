"""Verify the direct Responses API contract and safe handling of incomplete model output."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.errors import ProviderError
from app.llm import OpenAILanguageModel


@pytest.mark.parametrize(
    "status,output,success",
    [
        ("completed", '{"answer":"Yes","source_ids":[1]}', True),
        ("incomplete", '{"answer":"Yes","source_ids":[1]}', False),
        ("completed", "not JSON", False),
        ("completed", "", False),
    ],
)
def test_responses_contract(status, output, success):
    client = MagicMock()
    client.responses.create.return_value = SimpleNamespace(status=status, output_text=output)
    with patch("app.llm.OpenAI") as factory:
        factory.return_value.__enter__.return_value = client
        model = OpenAILanguageModel(Settings(openai_api_key="test"))
        if success:
            assert model.answer("context").source_ids == [1]
        else:
            with pytest.raises(ProviderError):
                model.answer("context")
    kwargs = client.responses.create.call_args.kwargs
    assert kwargs["store"] is False
    assert kwargs["text"]["format"]["strict"] is True
    assert "ONLY" in kwargs["instructions"]
