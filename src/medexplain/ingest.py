"""Turn an uploaded file into text.

Supported: plain text (.txt, .md, .text), PDF with a text layer (.pdf) and Word
(.docx). Anything else raises ``ValueError`` with a message the reader can act on.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import PurePath

SUPPORTED_EXTENSIONS = (".txt", ".text", ".md", ".pdf", ".docx")

# A PDF page with fewer extracted characters than this is treated as having no text
# layer (a scan or a photo). 20 is below the shortest real line of report text.
MIN_CHARS_PER_PAGE = 20


@dataclass(frozen=True)
class IngestedText:
    text: str
    source_name: str
    kind: str  # "text", "pdf", "docx"
    notes: tuple[str, ...] = ()  # things the reader should know, e.g. encoding used


def _decode_text(data: bytes, name: str) -> IngestedText:
    try:
        return IngestedText(data.decode("utf-8-sig"), name, "text")
    except UnicodeDecodeError:
        pass
    # Windows Notepad files are often cp1252. It decodes almost any byte string, so it
    # is used only after UTF-8 fails, and the reader is told.
    try:
        text = data.decode("cp1252")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"{name}: could not read the file as text (not UTF-8 or Windows-1252). Try saving it as UTF-8, or paste the text instead."
        ) from error
    return IngestedText(
        text,
        name,
        "text",
        (
            "The file was not UTF-8, so it was read as Windows-1252. If accented letters look wrong, paste the text instead.",
        ),
    )


def _read_pdf(data: bytes, name: str) -> IngestedText:
    try:
        from pypdf import PdfReader
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ValueError("Reading PDFs needs the 'pypdf' package. Install it, or paste the text instead.") from error
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise ValueError(
            f"{name}: the PDF is password-protected. Open it, save an unprotected copy, or paste the text."
        )
    pages = [page.extract_text() or "" for page in reader.pages]
    if not pages:
        raise ValueError(f"{name}: the PDF has no pages")
    empty = [number for number, page in enumerate(pages, start=1) if len(page.strip()) < MIN_CHARS_PER_PAGE]
    if len(empty) == len(pages):
        raise ValueError(
            f"{name}: no text could be read from this PDF. It is probably a scan or a photo. "
            "Copy the text from your patient portal and paste it instead."
        )
    notes = ()
    if empty:
        notes = (
            f"Pages {', '.join(map(str, empty))} had no readable text (they may be scanned images) and were skipped.",
        )
    return IngestedText("\n\n".join(page for page in pages if page.strip()), name, "pdf", notes)


def _read_docx(data: bytes, name: str) -> IngestedText:
    try:
        import docx
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ValueError(
            "Reading Word files needs the 'python-docx' package. Install it, or paste the text instead."
        ) from error
    document = docx.Document(io.BytesIO(data))
    lines = [paragraph.text for paragraph in document.paragraphs]
    # Lab results are often laid out in a table; keep each row on one line.
    for table in document.tables:
        for row in table.rows:
            lines.append("  ".join(cell.text.strip() for cell in row.cells))
    text = "\n".join(lines).strip()
    if not text:
        raise ValueError(f"{name}: the Word document has no text")
    return IngestedText(text, name, "docx")


def read_upload(name: str, data: bytes) -> IngestedText:
    """Read an uploaded file's bytes as text, choosing the reader by extension.

    >>> read_upload("note.txt", "Impression: normal".encode()).text
    'Impression: normal'
    """
    if not data:
        raise ValueError(f"{name}: the file is empty")
    extension = PurePath(name).suffix.lower()
    if extension in (".txt", ".text", ".md"):
        return _decode_text(data, name)
    if extension == ".pdf":
        return _read_pdf(data, name)
    if extension == ".docx":
        return _read_docx(data, name)
    if extension in (".png", ".jpg", ".jpeg", ".heic", ".gif", ".tif", ".tiff", ".bmp"):
        raise ValueError(
            f"{name}: photos and scans are not supported. Copy the text from your patient portal and paste it instead."
        )
    if extension == ".doc":
        raise ValueError(
            f"{name}: old-style .doc files are not supported. Save it as .docx or .pdf, or paste the text."
        )
    raise ValueError(
        f"{name}: unsupported file type {extension or '(none)'}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
    )
