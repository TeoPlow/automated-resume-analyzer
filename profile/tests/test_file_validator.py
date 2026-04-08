import pytest

from common.exceptions import AppError


class TestFileValidatorFormat:

    def test_valid_pdf_returns_extension(self, file_validator):
        content = b"%PDF-1.4 some pdf content"

        result = file_validator.validate("resume.pdf", content)

        assert result == "pdf"

    def test_valid_docx_returns_extension(self, file_validator):
        content = b"PK\x03\x04 some docx content"

        result = file_validator.validate("document.docx", content)

        assert result == "docx"

    def test_valid_txt_returns_extension(self, file_validator):
        content = b"Plain text resume content"

        result = file_validator.validate("resume.txt", content)

        assert result == "txt"

    def test_unsupported_extension_raises_400(self, file_validator):
        content = b"some content"

        with pytest.raises(AppError) as exc_info:
            file_validator.validate("image.png", content)

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_format"

    def test_no_extension_raises_400(self, file_validator):
        content = b"some content"

        with pytest.raises(AppError) as exc_info:
            file_validator.validate("resume", content)

        assert exc_info.value.status_code == 400

    def test_wrong_magic_bytes_raises_400(self, file_validator):
        content = b"NOT_A_PDF_FILE but pretending to be"

        with pytest.raises(AppError) as exc_info:
            file_validator.validate("resume.pdf", content)

        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_format"


class TestFileValidatorSize:

    def test_file_within_limit_passes(self, file_validator):
        content = b"%PDF" + b"x" * 1000

        result = file_validator.validate("small.pdf", content)

        assert result == "pdf"

    def test_file_exceeding_limit_raises_413(self, file_validator):
        content = b"%PDF" + b"x" * (11 * 1024 * 1024)

        with pytest.raises(AppError) as exc_info:
            file_validator.validate("huge.pdf", content)

        assert exc_info.value.status_code == 413
        assert exc_info.value.code == "file_too_large"
