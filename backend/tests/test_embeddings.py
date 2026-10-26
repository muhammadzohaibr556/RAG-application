"""Verify the embedding abstraction and SDK adapter without credentials or paid calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.config import Settings
from app.embeddings import OpenAIEmbedder
from app.errors import ProviderError


def test_missing_key_and_empty_input():
    embedder = OpenAIEmbedder(Settings(openai_api_key="", embedding_dimensions=2))
    assert embedder.embed([]).shape == (0, 2)
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        embedder.embed(["hello"])


def test_sdk_ordering():
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.0, 1.0]),
            SimpleNamespace(index=0, embedding=[1.0, 0.0]),
        ]
    )
    with patch("app.embeddings.OpenAI") as factory:
        factory.return_value.__enter__.return_value = client
        actual = OpenAIEmbedder(Settings(openai_api_key="test", embedding_dimensions=2)).embed(
            ["first", "second"]
        )
    np.testing.assert_array_equal(actual, [[1, 0], [0, 1]])
    assert actual.dtype == np.float32


def test_bad_dimensions_rejected():
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=0, embedding=[1.0]),
        ]
    )
    with patch("app.embeddings.OpenAI") as factory:
        factory.return_value.__enter__.return_value = client
        with pytest.raises(ProviderError, match="dimensions"):
            OpenAIEmbedder(Settings(openai_api_key="test", embedding_dimensions=2)).embed(["hi"])
