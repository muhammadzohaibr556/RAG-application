"""Token windows should overlap, terminate, and retain honest source coordinates."""

import pytest
import tiktoken

from app.chunking import chunk_units
from app.config import Settings
from app.extraction import TextUnit


def test_overlap_and_token_size():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = chunk_units([TextUnit(text, "line", 9)], size=30, overlap=8)
    encoding = tiktoken.get_encoding("cl100k_base")
    assert len(chunks) > 1
    assert all(chunk.token_count <= 30 for chunk in chunks)
    assert all(chunk.line_start == chunk.line_end == 9 for chunk in chunks)
    first = encoding.encode(chunks[0].text)
    second = encoding.encode(chunks[1].text)
    # Stripping can change the first token, but the interior overlapping tokens remain.
    assert first[-6:] == second[2:8]


def test_ranges_and_pdf_boundaries():
    chunks = chunk_units([TextUnit("alpha", "paragraph", 1), TextUnit("beta", "paragraph", 3)])
    assert chunks[0].paragraph_start == 1
    assert chunks[0].paragraph_end == 3
    pages = chunk_units([TextUnit("alpha", "page", 1), TextUnit("beta", "page", 2)])
    assert [chunk.page for chunk in pages] == [1, 2]


def test_unicode_is_not_corrupted():
    text = "سلام 🌍 café 日本語 " * 30
    chunks = chunk_units([TextUnit(text, "line", 1)], size=12, overlap=3)
    assert all("�" not in chunk.text for chunk in chunks)
    assert all(chunk.text in text for chunk in chunks)


def test_empty_and_invalid_windows():
    assert chunk_units([]) == []
    with pytest.raises(ValueError):
        chunk_units([], size=5, overlap=5)
    with pytest.raises(ValueError):
        Settings(chunk_size=10, chunk_overlap=10)
