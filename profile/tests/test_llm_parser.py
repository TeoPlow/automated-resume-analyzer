from profile.schemas.resume import ParsedContacts


class TestRegexExtraction:

    def test_extracts_email(self, llm_parser):
        text = "Контакты: john.doe@example.com, телефон ниже"

        contacts = llm_parser._extract_contacts_regex(text)

        assert contacts.email == "john.doe@example.com"

    def test_extracts_phone_plus7(self, llm_parser):
        text = "Телефон: +7 (999) 123-45-67"

        contacts = llm_parser._extract_contacts_regex(text)

        assert contacts.phone is not None
        assert "999" in contacts.phone

    def test_extracts_phone_8(self, llm_parser):
        text = "Тел: 8-916-555-44-33"

        contacts = llm_parser._extract_contacts_regex(text)

        assert contacts.phone is not None
        assert "916" in contacts.phone

    def test_extracts_telegram(self, llm_parser):
        text = "Telegram: @john_doe_dev"

        contacts = llm_parser._extract_contacts_regex(text)

        assert contacts.telegram == "@john_doe_dev"

    def test_extracts_linkedin(self, llm_parser):
        text = "Profile: linkedin.com/in/johndoe-123"

        contacts = llm_parser._extract_contacts_regex(text)

        assert contacts.linkedin == "https://linkedin.com/in/johndoe-123"

    def test_returns_none_when_no_contacts(self, llm_parser):
        text = "Просто текст без контактов."

        contacts = llm_parser._extract_contacts_regex(text)

        assert contacts.email is None
        assert contacts.phone is None
        assert contacts.telegram is None
        assert contacts.linkedin is None


class TestMergeResults:

    def test_regex_overrides_llm_contacts(self, llm_parser):
        regex_contacts = ParsedContacts(email="regex@test.com", phone="+79991234567")
        llm_result = {
            "full_name": "Иван Иванов",
            "contacts": {
                "email": "llm@test.com",
                "phone": "+70001112233",
            },
            "skills": ["Python"],
        }

        result = llm_parser._merge_results(regex_contacts, llm_result)

        assert result.contacts.email == "regex@test.com"
        assert result.contacts.phone == "+79991234567"
        assert result.full_name == "Иван Иванов"
        assert result.skills == ["Python"]

    def test_merge_with_empty_llm(self, llm_parser):
        regex_contacts = ParsedContacts(email="only@regex.com")

        result = llm_parser._merge_results(regex_contacts, {})

        assert result.contacts.email == "only@regex.com"
        assert result.skills == []
