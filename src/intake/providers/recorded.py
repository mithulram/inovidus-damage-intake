"""Replay genuine Groq responses by exact user-message text, never a live call."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import InboundEmail, Understanding
from ..rules import ROOT, Rules
from .llm_schema import build_user_message, parse_llm_content
from .offline import OfflineProvider


class RecordedProvider:
    name = "recorded(groq)"
    model = None

    def __init__(self, path: Path | str = ROOT / "examples/llm_recorded"):
        self._responses = {}
        for fixture in sorted(Path(path).glob("*.groq.json")):
            data = json.loads(fixture.read_text(encoding="utf-8"))
            self._responses[data["request"]["messages"][1]["content"]] = data["response"]

    def understand(self, email: InboundEmail, rules: Rules) -> Understanding:
        response = self._responses.get(build_user_message(email))
        if response is None:
            result = OfflineProvider().understand(email, rules)
            result.provider = "recorded(groq)→offline"
            result.fallback_used = True
            result.warnings.append("Keine Aufzeichnung für diese E-Mail – Regelmodus verwendet")
            return result
        return parse_llm_content(response["choices"][0]["message"]["content"], self.name, response["model"])
