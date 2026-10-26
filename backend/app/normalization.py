"""Normalize extracted text without discarding the original citation coordinates."""

import logging
import re
import unicodedata

from app.extraction import TextUnit


def normalize(units: list[TextUnit]) -> list[TextUnit]:
    """Clean Unicode and horizontal whitespace within each unit; retain page/line/paragraph IDs."""
    result = []
    for unit in units:
        text = unicodedata.normalize("NFC", unit.text).replace("\x00", "")
        text = re.sub(r"[^\S\n]+", " ", text).strip()
        if text:
            result.append(TextUnit(text, unit.kind, unit.position))
    logging.getLogger(__name__).info("Text normalized: %d nonempty units", len(result))
    return result
