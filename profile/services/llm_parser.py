import json
import re

import httpx

from common.logger import setup_logger

from profile.schemas.resume import ParsedContacts, ParsedData

logger = setup_logger("profile.llm_parser")

_SYSTEM_PROMPT = (
    "You are a resume parser. Extract structured information from the "
    "resume text below. Return ONLY valid JSON, no extra text. "
    "If a field cannot be determined, use null."
)

_USER_PROMPT_TEMPLATE = """Parse this resume and extract the following fields:
- full_name (string)
- contacts: {{ email, phone, telegram, linkedin }} (strings or null)
- location (string or null)
- summary (string — brief professional summary, 1-2 sentences)
- skills (array of strings — ALL technical and soft skills mentioned)
- experience (array of objects, each with: company, position, start_date, end_date, description, technologies)
- education (array of objects: institution, degree, field, graduation_year)
- languages (array of objects: language, level)
- total_experience_years (number — total professional experience)
- desired_salary (number or null)
- desired_position (string or null)

Resume text:
---
{raw_text}
---"""


class LlmParser:
    """Гибридный парсер резюме: regex-предизвлечение + LLM."""

    def __init__(
        self,
        ollama_url: str,
        model: str,
        max_retries: int = 2,
    ) -> None:
        self._ollama_url = ollama_url.rstrip("/")
        self._model = model
        self._max_retries = max_retries

    async def parse(self, raw_text: str) -> ParsedData:
        """Распарсить текст резюме гибридным методом (regex + LLM)."""
        regex_contacts = self._extract_contacts_regex(raw_text)
        llm_result = await self._call_llm(raw_text)
        return self._merge_results(regex_contacts, llm_result)

    # --- Приватные методы ---

    def _extract_contacts_regex(self, text: str) -> ParsedContacts:
        """Извлечь контакты из текста с помощью регулярных выражений."""
        email = _find_first(r"[\w.-]+@[\w.-]+\.\w{2,}", text)
        phone = _find_first(
            r"(?:\+7|8)[\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}",
            text,
        )
        telegram = _find_first(r"@[A-Za-z_]\w{4,}", text)
        linkedin = _find_first(r"linkedin\.com/in/[\w-]+", text)
        if linkedin:
            linkedin = f"https://{linkedin}"
        return ParsedContacts(
            email=email, phone=phone, telegram=telegram, linkedin=linkedin
        )

    async def _call_llm(self, raw_text: str) -> dict:
        """Вызвать Ollama API для парсинга резюме с повторами."""
        prompt = _USER_PROMPT_TEMPLATE.format(raw_text=raw_text)
        for attempt in range(1, self._max_retries + 2):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    response = await client.post(
                        f"{self._ollama_url}/api/generate",
                        json={
                            "model": self._model,
                            "prompt": prompt,
                            "system": _SYSTEM_PROMPT,
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    body = response.json()
                    return _parse_json_response(body.get("response", ""))
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning(
                    "LLM: попытка %d/%d — ошибка парсинга: %s",
                    attempt,
                    self._max_retries + 1,
                    exc,
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "LLM: попытка %d/%d — HTTP ошибка: %s",
                    attempt,
                    self._max_retries + 1,
                    exc,
                )
        logger.error("LLM: все попытки исчерпаны")
        return {}

    def _merge_results(
        self, regex_contacts: ParsedContacts, llm_result: dict
    ) -> ParsedData:
        """Объединить результаты regex и LLM. Regex имеет приоритет."""
        llm_data = ParsedData.model_validate(llm_result) if llm_result else ParsedData()
        if regex_contacts.email:
            llm_data.contacts.email = regex_contacts.email
        if regex_contacts.phone:
            llm_data.contacts.phone = regex_contacts.phone
        if regex_contacts.telegram:
            llm_data.contacts.telegram = regex_contacts.telegram
        if regex_contacts.linkedin:
            llm_data.contacts.linkedin = regex_contacts.linkedin
        return llm_data


# --- Приватные функции ---


def _find_first(pattern: str, text: str) -> str | None:
    """Найти первое совпадение regex в тексте."""
    match = re.search(pattern, text)
    return match.group(0) if match else None


def _parse_json_response(text: str) -> dict:
    """Извлечь JSON из ответа LLM (может содержать markdown-обёртку)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return json.loads(text)
