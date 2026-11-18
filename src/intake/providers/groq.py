"""Groq structured output, one validation retry, then a safe rule fallback."""

from __future__ import annotations

import os

import httpx

from ..models import InboundEmail, Understanding
from ..rules import Rules
from .llm_schema import SCHEMA, SYSTEM_PROMPT_PATH, build_user_message, parse_llm_content
from .offline import OfflineProvider

INVALID = "KI-Ausgabe ungültig – Regelmodus verwendet"
UNREACHABLE = "KI-Dienst nicht erreichbar – Regelmodus verwendet"
LIMIT = "KI-Limit erreicht (429) – Regelmodus verwendet"


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str = "openai/gpt-oss-120b",
                 base_url: str = "https://api.groq.com/openai/v1", client: httpx.Client | None = None):
        if not api_key.strip():
            raise ValueError("GROQ_API_KEY fehlt – bitte den API-Schlüssel setzen")
        self._api_key = api_key
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._client = client

    @classmethod
    def from_env(cls) -> "GroqProvider":
        return cls(api_key=os.getenv("GROQ_API_KEY", ""),
                   model=os.getenv("GROQ_MODEL") or "openai/gpt-oss-120b",
                   base_url=os.getenv("GROQ_BASE_URL") or "https://api.groq.com/openai/v1")

    def _fallback(self, email: InboundEmail, rules: Rules, warning: str) -> Understanding:
        result = OfflineProvider().understand(email, rules)
        result.provider = "groq→offline"
        result.fallback_used = True
        result.warnings.append(warning)
        return result

    def understand(self, email: InboundEmail, rules: Rules) -> Understanding:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")},
                {"role": "user", "content": build_user_message(email)},
            ],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "understanding", "strict": True, "schema": SCHEMA,
            }},
        }
        client = self._client if self._client is not None else httpx.Client()
        try:
            for attempt in range(2):
                try:
                    response = client.post(self._url, json=payload, timeout=30.0,
                                           headers={"Authorization": f"Bearer {self._api_key}"})
                except httpx.RequestError:
                    return self._fallback(email, rules, UNREACHABLE)
                if response.status_code == 429:
                    return self._fallback(email, rules, LIMIT)
                if response.status_code == 400:
                    if attempt == 0:
                        continue
                    return self._fallback(email, rules, INVALID)
                if not response.is_success:
                    return self._fallback(email, rules, UNREACHABLE)
                try:
                    data = response.json()
                    model = data["model"]
                    if not isinstance(model, str) or not model:
                        raise ValueError("Modell fehlt")
                    return parse_llm_content(data["choices"][0]["message"]["content"], self.name, model)
                except (ValueError, TypeError, KeyError, IndexError, OverflowError):
                    if attempt == 1:
                        return self._fallback(email, rules, INVALID)
        finally:
            if self._client is None:
                client.close()
