from profile.services.llm_parser import LlmParser


class TestRegexExtraction:

    def test_extracts_email(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        text = "Контакты: john.doe@example.com, телефон ниже"

        contacts = parser._extract_contacts_regex(text)

        assert contacts.email == "john.doe@example.com"

    def test_extracts_phone_plus7(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        text = "Телефон: +7 (999) 123-45-67"

        contacts = parser._extract_contacts_regex(text)

        assert contacts.phone is not None
        assert "999" in contacts.phone

    def test_extracts_phone_8(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        text = "Тел: 8-916-555-44-33"

        contacts = parser._extract_contacts_regex(text)

        assert contacts.phone is not None
        assert "916" in contacts.phone

    def test_extracts_telegram(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        text = "Telegram: @john_doe_dev"

        contacts = parser._extract_contacts_regex(text)

        assert contacts.telegram == "@john_doe_dev"

    def test_extracts_linkedin(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        text = "Profile: linkedin.com/in/johndoe-123"

        contacts = parser._extract_contacts_regex(text)

        assert contacts.linkedin == "https://linkedin.com/in/johndoe-123"

    def test_returns_none_when_no_contacts(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        text = "Просто текст без контактов."

        contacts = parser._extract_contacts_regex(text)

        assert contacts.email is None
        assert contacts.phone is None
        assert contacts.telegram is None
        assert contacts.linkedin is None


class TestMergeResults:

    def test_regex_overrides_llm_contacts(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        from profile.schemas.resume import ParsedContacts

        regex_contacts = ParsedContacts(
            email="regex@test.com", phone="+79991234567"
        )
        llm_result = {
            "full_name": "Иван Иванов",
            "contacts": {
                "email": "llm@test.com",
                "phone": "+70001112233",
            },
            "skills": ["Python"],
        }

        result = parser._merge_results(regex_contacts, llm_result)

        assert result.contacts.email == "regex@test.com"
        assert result.contacts.phone == "+79991234567"
        assert result.full_name == "Иван Иванов"
        assert result.skills == ["Python"]

    def test_merge_with_empty_llm(self):
        parser = LlmParser("http://fake:11434", "test", max_retries=0)
        from profile.schemas.resume import ParsedContacts

        regex_contacts = ParsedContacts(email="only@regex.com")

        result = parser._merge_results(regex_contacts, {})

        assert result.contacts.email == "only@regex.com"
        assert result.skills == []
