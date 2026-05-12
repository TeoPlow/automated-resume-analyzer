import sys
from types import SimpleNamespace

import pytest


class TestTextExtractorTxt:

    def test_extract_utf8_text(self, text_extractor):
        content = "Привет, мир!".encode("utf-8")

        result = text_extractor.extract(content, "txt")

        assert "Привет, мир!" in result

    def test_extract_cp1251_text(self, text_extractor):
        content = "Резюме кандидата".encode("cp1251")

        result = text_extractor.extract(content, "txt")

        assert "Резюме кандидата" in result

    def test_extract_empty_txt(self, text_extractor):
        content = b""

        result = text_extractor.extract(content, "txt")

        assert result == ""


class _FakePdfPage:

    def get_text(self):
        return "PDF page text"


class _FakePdfDoc:

    def __enter__(self):
        return [_FakePdfPage(), _FakePdfPage()]

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeDocxDocument:

    def __init__(self, stream):
        self.paragraphs = [
            SimpleNamespace(text="First paragraph"),
            SimpleNamespace(text=""),
            SimpleNamespace(text="Second paragraph"),
        ]


def test_extract_pdf(monkeypatch, text_extractor):
    fake_fitz = SimpleNamespace(open=lambda *args, **kwargs: _FakePdfDoc())
    monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

    result = text_extractor.extract(b"%PDF-1.4", "pdf")

    assert result == "PDF page text\nPDF page text"


def test_extract_docx(monkeypatch, text_extractor):
    fake_docx = SimpleNamespace(Document=lambda stream: _FakeDocxDocument(stream))
    monkeypatch.setitem(sys.modules, "docx", fake_docx)

    result = text_extractor.extract(b"PK\x03\x04", "docx")

    assert result == "First paragraph\nSecond paragraph"


def test_unsupported_extension_raises(text_extractor):
    with pytest.raises(ValueError):
        text_extractor.extract(b"data", "png")
