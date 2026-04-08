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
