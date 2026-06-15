import zipfile
from pathlib import Path

import pytest

from evermem import EverMem
from evermem.ingest import IngestError, extract_text, split_blocks


def _make_docx(path: Path, paragraphs: list[str]) -> None:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    document = f'<?xml version="1.0"?><w:document {ns}><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def test_extract_text_plain_and_markdown(tmp_path):
    txt = tmp_path / "note.txt"
    txt.write_text("Договор номер 47. Сумма 5000 рублей.", encoding="utf-8")
    assert "5000" in extract_text(txt)

    md = tmp_path / "readme.md"
    md.write_text("# Title\n\nBody line.", encoding="utf-8")
    assert "Body line." in extract_text(md)


def test_extract_text_docx(tmp_path):
    docx = tmp_path / "contract.docx"
    _make_docx(docx, ["Пункт первый.", "Сумма по договору: 9000."])
    text = extract_text(docx)
    assert "Пункт первый." in text
    assert "9000" in text


def test_extract_text_html_strips_tags_and_scripts(tmp_path):
    html = tmp_path / "page.html"
    html.write_text(
        "<html><head><script>var x=1;</script></head>"
        "<body><h1>Заголовок</h1><p>Первый абзац.</p></body></html>",
        encoding="utf-8",
    )
    text = extract_text(html)
    assert "Заголовок" in text
    assert "Первый абзац." in text
    assert "var x" not in text


def test_extract_text_unsupported_and_missing(tmp_path):
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"MZ")
    with pytest.raises(IngestError):
        extract_text(exe)
    with pytest.raises(IngestError):
        extract_text(tmp_path / "nope.txt")


def test_pdf_without_pypdf_gives_actionable_error(tmp_path):
    try:
        import pypdf  # noqa: F401

        pytest.skip("pypdf installed; error path not reachable")
    except ImportError:
        pass
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(IngestError, match="evermem-ai\\[pdf\\]"):
        extract_text(pdf)


def test_split_blocks_keeps_paragraphs_and_respects_limit():
    text = "Первый абзац про погоду.\n\nВторой абзац про договор номер 47.\n\n" + ("Очень длинный абзац. " * 60)
    blocks = split_blocks(text, max_chars=200)
    assert all(len(block) <= 200 for block in blocks)
    assert any("договор номер 47" in block for block in blocks)


def test_observe_file_makes_document_searchable(tmp_path):
    doc = tmp_path / "contract.txt"
    doc.write_text(
        "Договор аренды офиса.\n\n"
        "Арендная плата составляет 2500 рублей в месяц.\n\n"
        "Срок действия договора: до конца 2027 года.",
        encoding="utf-8",
    )
    mem = EverMem()
    report = mem.observe_file(doc)
    assert report.blocks >= 1
    assert report.session_id == f"file:{doc.resolve()}"

    pack = mem.recall("какая арендная плата?", session_id="chat")
    assert pack.history
    assert any("2500" in turn.text for turn in pack.history)
    assert any(turn.role == "document" for turn in pack.history)
    mem.close()
