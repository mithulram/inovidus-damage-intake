"""Offline proofs of the exact Groq boundary, retries and recorded scenarios."""

import copy
import json

import httpx
import pytest

from intake.models import InboundEmail
from intake.providers import get_provider
from intake.providers.groq import INVALID, LIMIT, UNREACHABLE, GroqProvider
from intake.providers.llm_schema import SCHEMA, SYSTEM_PROMPT_PATH, build_user_message, parse_llm_content
from intake.providers.recorded import RecordedProvider
from intake.rules import ROOT, load_rules
from intake.scenarios import load_scenario, run_scenario

FIXTURES = sorted((ROOT / "examples/llm_recorded").glob("*.groq.json"))
SECRET = "private-test-key-never-expose"


@pytest.fixture
def original():
    return load_scenario(ROOT / "scenarios/S01_original.yaml").email


@pytest.fixture
def response():
    return json.loads((ROOT / "examples/llm_recorded/S01_original.groq.json").read_text())["response"]


def mock_provider(outcomes):
    calls = []

    def handler(request):
        calls.append(request)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        status, body = outcome
        return httpx.Response(status, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GroqProvider(SECRET, client=client), calls, client


def test_request_matches_recorded_contract_and_uses_response_model(original, response):
    response["model"] = "response-model"
    provider, calls, client = mock_provider([(200, response)])
    with client:
        result = provider.understand(original, load_rules())
        assert not client.is_closed  # injected clients remain owned by the caller
    assert result.provider == "groq" and result.model == "response-model"
    assert not result.fallback_used
    assert result.extraction.street_raw == "Musterstr."
    assert result.extraction.floor_raw == "zweite Etage"
    assert result.extraction.language == "de"
    request, = calls
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert request.extensions["timeout"] == dict.fromkeys(["connect", "read", "write", "pool"], 30.0)
    payload = json.loads(request.content)
    fixture = json.loads(FIXTURES[0].read_text())
    expected_request = copy.deepcopy(fixture["request"])
    expected_request["messages"][0]["content"] = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    assert payload == {**expected_request, "temperature": 0, "response_format": {
        "type": "json_schema", "json_schema": {"name": "understanding", "strict": True, "schema": SCHEMA},
    }}
    recorded_prompt = (ROOT / "examples/llm_recorded/system_prompt.txt").read_text(encoding="utf-8")
    added_instruction = ("- Nennt die E-Mail mehrere oder unsichere Ortsangaben, liste die weiteren/unsicheren "
                         "wörtlich in location_alternatives.\n")
    assert SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").replace(added_instruction, "") == recorded_prompt


@pytest.mark.parametrize("failure", ["invalid_json", "validation", "missing_field", "envelope", "raw_json", "400"])
@pytest.mark.parametrize("recover", [True, False])
def test_bad_output_retries_exactly_once(original, response, failure, recover):
    bad = copy.deepcopy(response)
    if failure == "invalid_json":
        bad["choices"][0]["message"]["content"] = SECRET + "{broken"
    elif failure in {"validation", "missing_field"}:
        content = json.loads(bad["choices"][0]["message"]["content"])
        if failure == "validation":
            content["extraction"]["language"] = SECRET
        else:
            del content["extraction"]["phone"]
        bad["choices"][0]["message"]["content"] = json.dumps(content)
    elif failure == "envelope":
        bad = {"choices": []}
    first = (400, {"error": SECRET}) if failure == "400" else (200, bad)
    if failure == "raw_json":
        # A JSON string is a valid HTTP body but not the expected response envelope.
        first = (200, SECRET + "{broken")
    provider, calls, client = mock_provider([first, (200, response) if recover else first])
    with client:
        result = provider.understand(original, load_rules())
    assert len(calls) == 2
    assert result.fallback_used is not recover
    assert result.provider == ("groq" if recover else "groq→offline")
    assert result.warnings == ([] if recover else [INVALID])
    assert SECRET not in result.model_dump_json()


@pytest.mark.parametrize("outcome,warning", [
    ((429, {"error": SECRET}), LIMIT),
    ((500, {"error": SECRET}), UNREACHABLE),
    ((401, {"error": SECRET}), UNREACHABLE),
    (httpx.ReadTimeout(SECRET), UNREACHABLE),
    (httpx.ConnectError(SECRET), UNREACHABLE),
])
def test_service_failures_fall_back_without_retry_or_secret(original, outcome, warning):
    provider, calls, client = mock_provider([outcome])
    with client:
        result = provider.understand(original, load_rules())
    assert len(calls) == 1
    assert result.provider == "groq→offline" and result.fallback_used
    assert result.warnings == [warning]
    assert SECRET not in result.model_dump_json()


def test_actual_non_json_http_response_retries(original, response):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="<html>invalid</html>") if len(calls) == 1 else httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = GroqProvider(SECRET, client=client).understand(original, load_rules())
    assert len(calls) == 2 and not result.fallback_used


def test_from_env_missing_key_defaults_and_overrides(monkeypatch):
    for key in ["GROQ_API_KEY", "GROQ_MODEL", "GROQ_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY fehlt") as exc:
        GroqProvider.from_env()
    assert SECRET not in str(exc.value)
    monkeypatch.setenv("GROQ_API_KEY", SECRET)
    provider = GroqProvider.from_env()
    assert provider.model == "openai/gpt-oss-120b"
    assert SECRET not in repr(provider)
    monkeypatch.setenv("GROQ_MODEL", "custom-model")
    monkeypatch.setenv("GROQ_BASE_URL", "https://example.invalid/v1/")
    provider = GroqProvider.from_env()
    assert provider.model == "custom-model"
    assert provider._url == "https://example.invalid/v1/chat/completions"


@pytest.mark.parametrize("confidence,expected", [(-5, 0), (2, 1), (0.75, 0.75)])
def test_confidence_is_clamped(response, confidence, expected):
    content = json.loads(response["choices"][0]["message"]["content"])
    content["classification"]["confidence"] = confidence
    assert parse_llm_content(json.dumps(content), "test", "model").classification.confidence == expected


@pytest.mark.parametrize("field,value", [("confidence", "1"), ("confidence", True), ("confidence", float("nan")),
                                         ("confidence", float("inf")), ("reason", None)])
def test_parser_refuses_coercion_and_nonfinite_numbers(response, field, value):
    content = json.loads(response["choices"][0]["message"]["content"])
    content["classification"][field] = value
    with pytest.raises(ValueError):
        parse_llm_content(json.dumps(content), "test", "model")


@pytest.mark.parametrize("fixture_path", FIXTURES, ids=lambda p: p.stem)
def test_every_recorded_fixture_parses_and_satisfies_scenario(fixture_path):
    fixture = json.loads(fixture_path.read_text())
    response = fixture["response"]
    result = parse_llm_content(response["choices"][0]["message"]["content"], "recorded(groq)", response["model"])
    assert result.extraction.location_alternatives == []
    scenario = load_scenario(ROOT / "scenarios" / (fixture_path.name.removesuffix(".groq.json") + ".yaml"))
    assert build_user_message(scenario.email) == fixture["request"]["messages"][1]["content"]
    provider = get_provider("recorded")
    assert provider.understand(scenario.email, load_rules()) == result
    case, checks = run_scenario(scenario, provider=provider)
    assert all(c.passed for c in checks), [c.model_dump() for c in checks if not c.passed]
    assert case.processing.provider == "recorded(groq)"
    assert not case.processing.fallback_used
    if scenario.id == "S1":
        assert case.match.selected_contract == "MV-10245"


def test_live_schema_adds_required_location_array_to_recorded_schema():
    recorded_schema = json.loads((ROOT / "examples/llm_recorded/schema.json").read_text())
    live_extraction = SCHEMA["properties"]["extraction"]
    assert live_extraction["additionalProperties"] is False
    assert live_extraction["properties"]["location_alternatives"] == {"type": "array", "items": {"type": "string"}}
    assert "location_alternatives" in live_extraction["required"]
    previous_schema = copy.deepcopy(SCHEMA)
    del previous_schema["properties"]["extraction"]["properties"]["location_alternatives"]
    previous_schema["properties"]["extraction"]["required"].remove("location_alternatives")
    assert previous_schema == recorded_schema
    assert len(FIXTURES) == 5


@pytest.mark.parametrize("alternatives", [[], ["3. OG rechts", "bei der Etage unsicher"]])
def test_parser_accepts_live_location_alternatives(response, alternatives):
    content = json.loads(response["choices"][0]["message"]["content"])
    content["extraction"]["location_alternatives"] = alternatives
    result = parse_llm_content(json.dumps(content), "test", "model")
    assert result.extraction.location_alternatives == alternatives


@pytest.mark.parametrize("alternatives", [None, "3. OG rechts", {}, 1, True, [None], [1], [True], [[]], [{}]])
def test_parser_rejects_invalid_location_array_and_item_types(response, alternatives):
    content = json.loads(response["choices"][0]["message"]["content"])
    content["extraction"]["location_alternatives"] = alternatives
    with pytest.raises(ValueError):
        parse_llm_content(json.dumps(content), "test", "model")


def test_recorded_unknown_email_falls_back_and_matching_is_by_message_not_id(original):
    provider = RecordedProvider()
    changed_id = original.model_copy(update={"message_id": "different-id", "attachments": ["image.jpg"]})
    assert not provider.understand(changed_id, load_rules()).fallback_used
    unknown = original.model_copy(update={"body": original.body + " Neue Nachricht."})
    result = provider.understand(unknown, load_rules())
    assert result.fallback_used and result.provider == "recorded(groq)→offline"
    assert result.warnings == ["Keine Aufzeichnung für diese E-Mail – Regelmodus verwendet"]
    assert build_user_message(InboundEmail(body="Test")) == "Betreff: \nAbsender: (unbekannt)\n\nTest"
