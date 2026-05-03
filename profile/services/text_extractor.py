from common.logger import setup_logger

logger = setup_logger("profile.text_extractor")


class TextExtractor:
    """Извлечение raw-текста из файлов различных форматов."""

    def extract(self, content: bytes, extension: str) -> str:
        """Извлечь текст из файла по его расширению."""
        extractors = {
            "pdf": self._extract_pdf,
            "docx": self._extract_docx,
            "doc": self._extract_docx,
            "txt": self._extract_txt,
        }
        extractor = extractors.get(extension)
        if not extractor:
            raise ValueError(f"Неподдерживаемый формат: {extension}")
        text = extractor(content)
        logger.info("Извлечено %d символов из .%s файла", len(text), extension)
        return text

    # --- Приватные методы ---

    def _extract_pdf(self, content: bytes) -> str:
        """Извлечь текст из PDF через PyMuPDF."""
        import fitz

        pages: list[str] = []
        with fitz.open(stream=content, filetype="pdf") as doc:
            for page in doc:
                pages.append(str(page.get_text()))
        return "\n".join(pages)

    def _extract_docx(self, content: bytes) -> str:
        """Извлечь текст из DOCX/DOC через python-docx."""
        import io

        from docx import Document

        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)

    def _extract_txt(self, content: bytes) -> str:
        """Извлечь текст из TXT с автоопределением кодировки."""
        for encoding in ("utf-8", "cp1251", "latin-1"):
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, ValueError):
                continue
        return content.decode("utf-8", errors="replace")
