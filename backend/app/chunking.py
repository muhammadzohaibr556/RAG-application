"""Split normalized source units into overlapping token windows with citation metadata."""

import logging
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

import tiktoken

from app.extraction import TextUnit


@dataclass(frozen=True)
class ChunkDraft:
    """A passage and its source range, ready for embedding and relational persistence."""

    text: str
    token_count: int
    page: int | None = None
    paragraph_start: int | None = None
    paragraph_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None


def chunk_group(units: list[TextUnit], size: int, overlap: int) -> list[ChunkDraft]:
    """
    Map token offsets to original text spans; output windows without splitting Unicode
    characters.
    """
    encoding = tiktoken.get_encoding("cl100k_base")
    starts, ends = [], []
    cursor = 0
    for unit in units:
        starts.append(cursor)
        ends.append(cursor + len(unit.text))
        cursor += len(unit.text) + 1
    text = "\n".join(unit.text for unit in units)
    tokens = encoding.encode(text, disallowed_special=())
    _, offsets = encoding.decode_with_offsets(tokens)
    offsets.append(len(text))
    chunks = []
    for start_token in range(0, len(tokens), size - overlap):
        end_token = min(start_token + size, len(tokens))
        start, end = offsets[start_token], offsets[end_token]
        passage = text[start:end].strip()
        if passage:
            first = units[min(bisect_right(ends, start), len(units) - 1)].position
            last = units[max(bisect_left(starts, end) - 1, 0)].position
            coordinates = (
                {"page": first}
                if units[0].kind == "page"
                else {f"{units[0].kind}_start": first, f"{units[0].kind}_end": last}
            )
            chunks.append(
                ChunkDraft(
                    text=passage,
                    token_count=len(encoding.encode(passage, disallowed_special=())),
                    **coordinates,
                )
            )
        if end_token == len(tokens):
            break
    return chunks


def chunk_units(units: list[TextUnit], size: int = 700, overlap: int = 120) -> list[ChunkDraft]:
    """Produce overlapping passages; keep PDFs within one page so page citations stay exact."""
    if size < 2 or not 0 <= overlap < size:
        raise ValueError("Chunk size must be at least 2 and overlap must be smaller than size.")
    if not units:
        return []
    groups = [[unit] for unit in units] if units[0].kind == "page" else [units]
    chunks = [chunk for group in groups for chunk in chunk_group(group, size, overlap)]
    logging.getLogger(__name__).info("%d chunks created", len(chunks))
    return chunks
