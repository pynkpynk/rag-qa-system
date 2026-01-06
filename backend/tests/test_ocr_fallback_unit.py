from __future__ import annotations

from app.services import indexing


class _FakeOCRBackend:
    def __init__(self, pages: list[tuple[int, str]]):
        self._pages = pages

    def extract(self, path: str, *, request_id: str | None = None):
        return self._pages


def test_normalize_table_like_text_converts_multi_space_rows():
    text = "H1  H2   H3\nalpha beta\na    b      c"
    normalized = indexing.normalize_table_like_text(text)
    lines = normalized.splitlines()
    assert lines[0] == "H1\tH2\tH3"
    assert lines[1] == "alpha beta"
    assert lines[2] == "a\tb\tc"


def test_extract_pdf_pages_with_ocr_fallback_uses_backend(monkeypatch, tmp_path):
    fake_pdf = tmp_path / "empty.pdf"
    fake_pdf.write_bytes(b"%PDF-1.4")

    def _fake_extract(path: str):
        return []

    monkeypatch.setattr(indexing, "_extract_pdf_pages_pypdf", _fake_extract)
    monkeypatch.setattr(
        indexing,
        "get_ocr_backend",
        lambda: _FakeOCRBackend([(1, "ocr text line")]),
    )

    result = indexing.extract_pdf_pages_with_ocr_fallback(
        str(fake_pdf), request_id="req", min_total_chars=5
    )

    assert result == [(1, "ocr text line")]
