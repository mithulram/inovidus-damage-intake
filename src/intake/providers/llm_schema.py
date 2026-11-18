"""The recorded strict schema and the shared, validated LLM/email boundary."""

from __future__ import annotations

import json
import math
from typing import Any

from ..models import InboundEmail, Understanding
from ..rules import ROOT

SCHEMA = json.loads((ROOT / "examples/llm_recorded/schema.json").read_text(encoding="utf-8"))
SYSTEM_PROMPT_PATH = ROOT / "config/prompts/understanding_system.txt"


def build_user_message(email: InboundEmail) -> str:
    return f"Betreff: {email.subject}\nAbsender: {email.sender_email or '(unbekannt)'}\n\n{email.body}"


def _validate(value: Any, schema: dict) -> None:
    """Validate the types/required fields/enums of this fixed schema, without coercion.

    The supplied schema uses only these JSON Schema keywords. Pydantic alone
    would fill missing nullable fields and coerce some invalid JSON types.
    """
    types = schema["type"]
    types = [types] if isinstance(types, str) else types
    valid = {
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
        "number": type(value) in (int, float) and math.isfinite(value),
        "boolean": type(value) is bool,
        "null": value is None,
    }
    if not any(valid[t] for t in types):
        raise ValueError("KI-Ausgabe hat einen ungültigen Feldtyp")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError("KI-Ausgabe hat einen ungültigen Feldwert")
    if isinstance(value, dict):
        if set(schema["required"]) - value.keys() or value.keys() - schema["properties"].keys():
            raise ValueError("KI-Ausgabe hat fehlende oder zusätzliche Felder")
        for key, item in value.items():
            _validate(item, schema["properties"][key])


def parse_llm_content(content: str, provider: str, model: str | None) -> Understanding:
    payload = json.loads(content)
    _validate(payload, SCHEMA)
    classification = payload["classification"]
    classification["confidence"] = max(0.0, min(1.0, classification["confidence"]))
    return Understanding.model_validate({**payload, "provider": provider, "model": model})
