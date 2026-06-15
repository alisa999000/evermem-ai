"""Document ingestion: PDF, DOCX, HTML, Markdown and plain text into memory.

Documents are split into paragraph-aligned blocks and stored as searchable
turns (role "document"). Recall then surfaces the exact passages that match
a query, the same way it surfaces past conversation turns.

Formats:
- .txt / .md / .markdown / .rst / .log / .csv  read as plain text (stdlib)
- .docx                                        zipfile + XML, no dependencies
- .html / .htm                                 stdlib HTMLParser, tags stripped
- .pdf                                         requires the optional pypdf extra:
                                               pip install "evermem-ai[pdf]"
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from .embeddings import split_chunks

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".log", ".csv"}
DEFAULT_BLOCK_CHARS = 1000


class IngestError(Exception):
    """Raised when a document cannot be read."""


@dataclass
class IngestReport:
    path: str
    session_id: str
    blocks: int
    characters: int
    claims_added: int = 0


# --------------------------------------------------------------- extractors


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


_DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _read_docx(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml_data = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise IngestError(f"Not a valid .docx file: {path}") from exc
    root = ElementTree.fromstring(xml_data)
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{_DOCX_NS}p"):
        runs = [node.text or "" for node in paragraph.iter(f"{_DOCX_NS}t")]
        text = "".join(runs).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


class _HTMLTextParser(HTMLParser):
    _SKIP = {"script", "style", "head", "noscript"}
    _BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def _read_html(path: Path) -> str:
    parser = _HTMLTextParser()
    parser.feed(_read_text(path))
    text = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _read_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise IngestError(
            "PDF support needs the optional pypdf package. "
            'Install it with: pip install "evermem-ai[pdf]"'
        ) from exc
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise IngestError(f"Cannot open PDF {path}: {exc}") from exc
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(page for page in pages if page)


def extract_text(path: str | Path) -> str:
    """Plain text of a document; raises IngestError for unsupported input."""
    file = Path(path)
    if not file.is_file():
        raise IngestError(f"File not found: {file}")
    suffix = file.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return _read_text(file)
    if suffix == ".docx":
        return _read_docx(file)
    if suffix in {".html", ".htm"}:
        return _read_html(file)
    if suffix == ".pdf":
        return _read_pdf(file)
    raise IngestError(
        f"Unsupported file type '{suffix}'. "
        f"Supported: {', '.join(sorted(TEXT_SUFFIXES))}, .docx, .html, .pdf"
    )


# ----------------------------------------------------------------- blocking


def split_blocks(text: str, *, max_chars: int = DEFAULT_BLOCK_CHARS) -> list[str]:
    """Split document text into paragraph-aligned blocks of up to max_chars.

    Paragraphs are kept together while they fit; an oversized paragraph is
    split on sentence boundaries via split_chunks.
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    blocks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        flat = " ".join(paragraph.split())
        if len(flat) > max_chars:
            if current:
                blocks.append(current)
                current = ""
            blocks.extend(split_chunks(flat, max_chars=max_chars))
            continue
        candidate = f"{current}\n{flat}" if current else flat
        if len(candidate) > max_chars and current:
            blocks.append(current)
            current = flat
        else:
            current = candidate
    if current:
        blocks.append(current)
    return blocks
