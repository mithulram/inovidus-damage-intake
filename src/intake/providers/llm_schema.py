"""The live strict schema and the shared, validated LLM/email boundary."""

from __future__ import annotations

import json
import math
from typing import Any

from ..models import InboundEmail, Understanding
from ..rules import ROOT

SCHEMA = json.loads((ROOT / "examples/llm_recorded/schema.json").read_text(encoding="utf-8"))
SCHEMA["properties"]["extraction"]["properties"]["location_alternatives"] = {
    "type": "array", "items": {"type": "string"},
}
SCHEMA["properties"]["extraction"]["required"].append("location_alternatives")
SYSTEM_PROMPT_PATH = ROOT / "config/prompts/understanding_system.txt"


def build_user_message(email: InboundEmail) -> str:
    sender = email.sender_email or "(unbekannt)"
    if email.sender_display_name:
        sender = f"{email.sender_display_name} <{sender}>"
    return f"Betreff: {email.subject}\nAbsender: {sender}\n\n{email.body}"


def _validate(value: Any, schema: dict) -> None:
    """Validate the types/required fields/enums of this fixed schema, without coercion.

    The supplied schema uses only these JSON Schema keywords. Pydantic alone
    would fill missing nullable fields and coerce some invalid JSON types.
    """
    types = schema["type"]
    types = [types] if isinstance(types, str) else types
    valid = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
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
    elif isinstance(value, list):
        for item in value:
            _validate(item, schema["items"])


def parse_llm_content(content: str, provider: str, model: str | None) -> Understanding:
    payload = json.loads(content)
    # Recordings predate this field; retain strict validation of every other field.
    if isinstance(payload, dict) and isinstance(payload.get("extraction"), dict):
        payload["extraction"].setdefault("location_alternatives", [])
    _validate(payload, SCHEMA)
    classification = payload["classification"]
    classification["confidence"] = max(0.0, min(1.0, classification["confidence"]))
    return Understanding.model_validate({**payload, "provider": provider, "model": model})
