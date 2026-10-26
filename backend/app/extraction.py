"""Extract plain text plus original source positions before normalization or chunking."""

import logging
from dataclasses import dataclass
from io import BytesIO
from zipfile import BadZipFile, ZipFile

import pymupdf
from docx import Document as DocxDocument
from docx.text.paragraph import Paragraph

from app.errors import InvalidUpload, UploadTooLarge

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextUnit:
    """A page, paragraph, or line with its original one-based position for later citations."""

    text: str
    kind: str
    position: int


def extract_pdf(content: bytes, max_chars: int) -> list[TextUnit]:
    """Turn PDF bytes into numbered pages; reject encrypted or image-only input, without OCR."""
    logger.info("PDF extraction started")
    units: list[TextUnit] = []
    total = 0
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass:
                raise InvalidUpload("Password-protected PDFs are not supported.")
            for number, page in enumerate(document, 1):
                text = page.get_text("text", sort=True)
                total += len(text)
                check_text_budget(total, max_chars)
                units.append(TextUnit(text, "page", number))
    except (RuntimeError, ValueError) as exc:
        raise InvalidUpload("This PDF could not be read. Upload a valid text-based PDF.") from exc
    logger.info("%d pages extracted", len(units))
    return units


def extract_docx(content: bytes, max_chars: int) -> list[TextUnit]:
    """Read DOCX body paragraphs, including table cells, in XML order with stable numbering."""
    logger.info("DOCX extraction started")
    try:
        with ZipFile(BytesIO(content)) as archive:
            # DOCX is a ZIP archive. Bound expansion before python-docx opens the package.
            if sum(entry.file_size for entry in archive.infolist()) > max(
                8_000_000, max_chars * 20
            ):
                raise UploadTooLarge("DOCX expands beyond the extraction limit.")
            if "word/document.xml" not in archive.namelist():
                raise InvalidUpload("The uploaded archive is not a DOCX document.")
        document = DocxDocument(BytesIO(content))
        units: list[TextUnit] = []
        total = 0
        for number, element in enumerate(document.element.body.xpath(".//w:p"), 1):
            text = Paragraph(element, document).text
            total += len(text)
            check_text_budget(total, max_chars)
            units.append(TextUnit(text, "paragraph", number))
    except (BadZipFile, KeyError, ValueError, OSError) as exc:
        raise InvalidUpload("This DOCX could not be read. Upload a valid Word document.") from exc
    logger.info("%d paragraphs extracted", len(units))
    return units


def extract_txt(content: bytes, max_chars: int) -> list[TextUnit]:
    """Decode UTF-8 text into original line numbers, retaining blanks for citation accuracy."""
    logger.info("TXT extraction started")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InvalidUpload("TXT files must be saved with UTF-8 encoding.") from exc
    if "\x00" in text:
        raise InvalidUpload("This TXT contains binary data. Upload a UTF-8 text file.")
    check_text_budget(len(text), max_chars)
    units = [TextUnit(line, "line", number) for number, line in enumerate(text.splitlines(), 1)]
    logger.info("%d lines extracted", len(units))
    return units


def check_text_budget(characters: int, maximum: int) -> None:
    """Reject excessive extracted text before tokenization and embedding can consume resources."""
    if characters > maximum:
        raise UploadTooLarge("Extracted text exceeds MAX_EXTRACTED_CHARS. Split this document.")


def extract(content: bytes, extension: str, max_chars: int) -> list[TextUnit]:
    """Dispatch validated bytes to a format reader; return usable units or a friendly failure."""
    readers = {".pdf": extract_pdf, ".docx": extract_docx, ".txt": extract_txt}
    try:
        units = readers[extension](content, max_chars)
    except (InvalidUpload, UploadTooLarge):
        raise
    except Exception as exc:
        # Parsers expose many format-specific exceptions; keep them behind this boundary.
        logger.warning("Document parser failed: %s", type(exc).__name__)
        raise InvalidUpload("The file is damaged or is not the declared document format.") from exc
    if not any(unit.text.strip() for unit in units):
        raise InvalidUpload(
            "No readable text found. Scanned/image-only PDFs need OCR, which is not supported."
        )
    return units
