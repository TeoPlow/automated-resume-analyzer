import json

import pytest

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


class _FakeResponse:

    def __init__(self, response_text: str):
        self._response_text = response_text

    def raise_for_status(self):
        return None

    def json(self):
        return {"response": self._response_text}


class _FakeAsyncClient:

    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_call_llm_success_parses_markdown_json(monkeypatch):
    from profile.services import llm_parser as module

    payload = json.dumps(
        {
            "full_name": "Иван Иванов",
            "skills": ["Python"],
            "contacts": {"email": "ivan@example.com"},
        }
    )
    fake_client = _FakeAsyncClient([_FakeResponse(f"```json\n{payload}\n```")])
    monkeypatch.setattr(
        module.httpx, "AsyncClient", lambda *args, **kwargs: fake_client
    )

    parser = module.LlmParser("http://fake:11434", "test", max_retries=0)
    result = await parser._call_llm("text")

    assert result["full_name"] == "Иван Иванов"
    assert result["skills"] == ["Python"]


@pytest.mark.asyncio
async def test_call_llm_exhausts_retries(monkeypatch):
    from profile.services import llm_parser as module

    fake_client = _FakeAsyncClient(
        [
            _FakeResponse("not-json"),
            _FakeResponse("still-not-json"),
        ]
    )
    monkeypatch.setattr(
        module.httpx, "AsyncClient", lambda *args, **kwargs: fake_client
    )

    parser = module.LlmParser("http://fake:11434", "test", max_retries=1)
    result = await parser._call_llm("text")

    assert result == {}
