from common.exceptions import AppError

# Magic bytes для определения реального типа файла
_SIGNATURES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF"],
    "docx": [b"PK\x03\x04"],
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "txt": [],
}


class FileValidator:
    """Валидатор загружаемых файлов резюме."""

    def __init__(
        self,
        max_size: int,
        allowed_extensions: list[str],
    ) -> None:
        self._max_size = max_size
        self._allowed_extensions = allowed_extensions

    def validate(self, filename: str, content: bytes) -> str:
        """Валидировать файл и вернуть расширение.

        Проверяет размер, расширение и magic bytes.
        """
        self._check_size(content)
        ext = self._extract_extension(filename)
        self._check_magic_bytes(content, ext)
        return ext

    # --- Приватные методы ---

    def _check_size(self, content: bytes) -> None:
        """Проверить, что размер файла не превышает лимит."""
        if len(content) > self._max_size:
            max_mb = self._max_size / (1024 * 1024)
            raise AppError(
                code="file_too_large",
                message=f"Размер файла превышает {max_mb:.0f} МБ",
                status_code=413,
            )

    def _extract_extension(self, filename: str) -> str:
        """Извлечь и проверить расширение файла."""
        if "." not in filename:
            raise AppError(
                code="invalid_format",
                message="Файл должен иметь расширение",
                status_code=400,
            )
        ext = filename.rsplit(".", maxsplit=1)[-1].lower()
        if ext not in self._allowed_extensions:
            allowed = ", ".join(self._allowed_extensions)
            raise AppError(
                code="invalid_format",
                message=f"Разрешённые форматы: {allowed}",
                status_code=400,
            )
        return ext

    def _check_magic_bytes(self, content: bytes, ext: str) -> None:
        """Проверить сигнатуру файла (magic bytes)."""
        signatures = _SIGNATURES.get(ext, [])
        if not signatures:
            return
        for sig in signatures:
            if content[: len(sig)] == sig:
                return
        raise AppError(
            code="invalid_format",
            message="Содержимое файла не соответствует расширению",
            status_code=400,
        )
