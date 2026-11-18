"""The HTTP boundary uses the same pipeline, persists only on request, never sends."""

from datetime import datetime, timedelta, timezone
import importlib

from fastapi.testclient import TestClient
import pytest
import yaml

from intake.actions import AuditLog
from intake.models import AuditEvent, CaseRecord
from intake.rules import DEFAULT_RULES_PATH, load_rules
from intake.scenarios import load_scenarios, run_scenario
from intake.steps import STEPS
from intake.store import CaseStore
from intake.web.app import create_app

SCENARIOS = load_scenarios()
EXCLUDED = {"audit", "processed_at", "received_at"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    app = create_app(store=CaseStore(tmp_path / "cases"), audit=AuditLog(tmp_path / "audit.jsonl"),
                     static_dir=tmp_path / "static")
    with TestClient(app) as client:
        yield client


def process(client, scenario=None, **kwargs):
    scenario = scenario or SCENARIOS[0]
    response = client.post("/api/process", json={"email": scenario.email.model_dump(mode="json"),
                                               "scenario_id": scenario.id, **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def inbox(client, scenario=None):
    case = process(client, scenario)
    response = client.post("/api/cases", json=case)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("provider", ["offline", "recorded"])
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.id)
def test_every_scenario_process_matches_chained_steps(client, scenario, provider):
    full = process(client, scenario, provider=provider)
    body = {"email": scenario.email.model_dump(mode="json"), "scenario_id": scenario.id, "provider": provider}
    for name in STEPS:
        response = client.post(f"/api/steps/{name}", json=body)
        assert response.status_code == 200, response.text
        body = {"case": response.json(), "scenario_id": scenario.id, "provider": provider}
    actual = CaseRecord.model_validate(full)
    chained = CaseRecord.model_validate(body["case"])
    assert actual.model_dump(exclude=EXCLUDED) == chained.model_dump(exclude=EXCLUDED)
    expected, checks = run_scenario(scenario, provider=provider)
    assert all(c.passed for c in checks)
    # Exercise the override behaviour independently of parity (both routes could omit it).
    for key in ["understanding", "match", "prior_cases", "urgency", "status", "reply_draft", "internal_task"]:
        assert getattr(actual, key) == getattr(expected, key)
    assert client.get("/api/cases").json() == []
    assert not client.app.state.store.path.exists()
    assert not client.app.state.audit.path.exists()


def test_health_rules_scenarios_and_same_origin(client):
    assert client.get("/api/health").json() == {
        "status": "ok", "provider_default": "offline", "rules_version": load_rules().version,
    }
    rules = client.get("/api/rules").json()
    assert rules["yaml"] == DEFAULT_RULES_PATH.read_text(encoding="utf-8")
    assert rules["parsed"] == yaml.safe_load(rules["yaml"])
    assert rules["version"] == load_rules().version
    scenarios = client.get("/api/scenarios").json()
    assert [s["id"] for s in scenarios] == [s.id for s in SCENARIOS]
    for actual, expected in zip(scenarios, SCENARIOS):
        assert actual == {"id": expected.id, "title": expected.title, "description": expected.description,
                          "email": expected.email.model_dump(mode="json"), "expected": expected.expected,
                          "rule_overrides": expected.rule_overrides or {},
                          "has_overrides": bool(expected.rule_overrides or expected.data_overrides)}
    assert "hint" in client.get("/").json()
    response = client.get("/api/health", headers={"Origin": "https://foreign.example"})
    assert "access-control-allow-origin" not in response.headers
    assert all("send" not in route.path for route in client.app.routes)


def test_case_round_trip_is_idempotent_and_reply_is_read_only(client):
    case = inbox(client)
    assert case["audit"][-1]["event"] == "in Prüfliste übernommen"
    assert client.get(f"/api/cases/{case['case_id']}").json() == case
    assert client.post("/api/cases", json=case).json() == case
    summary, = client.get("/api/cases").json()
    # FastAPI and Pydantic use equivalent ISO UTC spellings (+00:00 / Z).
    summary["received_at"] = datetime.fromisoformat(summary["received_at"])
    assert summary == {"case_id": case["case_id"], "received_at": datetime.fromisoformat(case["received_at"]),
                       "subject": case["input"]["subject"], "sender": case["input"]["sender_email"],
                       "status": case["status"],
                       "urgency": case["urgency"]["level"], "winner": case["match"]["winner"],
                       "selected_contract": case["match"]["selected_contract"],
                       "failed_gates": case["match"]["failed_gates"]}
    audit = client.get("/api/audit").json()
    assert len(audit) == 1 and audit[0] == case["audit"][-1]
    response = client.get(f"/api/cases/{case['case_id']}/reply?variant=ask_registered_email")
    assert response.status_code == 200
    assert response.json()["variant"] == "ask_registered_email"
    assert response.json()["auto_send"] is False
    assert client.get(f"/api/cases/{case['case_id']}").json() == case
    assert client.get("/api/audit").json() == audit


def test_process_store_true_enters_review_inbox_once(client):
    case = process(client, store=True)
    assert case["audit"][-1]["event"] == "in Prüfliste übernommen"
    assert client.get(f"/api/cases/{case['case_id']}").json() == case
    assert process(client, store=True) == case
    assert len(client.get("/api/audit").json()) == 1


def test_approval_rejects_missing_assignment_then_persists_valid_actions(client):
    case = inbox(client)
    request = {"case_id": case["case_id"], "actor": "Sachbearbeitung", "action": "order_contractor",
               "contract_id": "MV-10245"}
    denied = client.post("/api/approve", json=request)
    assert denied.status_code == 403 and "vorherige Zuordnungsfreigabe" in denied.json()["detail"]
    assert client.get(f"/api/cases/{case['case_id']}").json() == case
    assert len(client.get("/api/audit").json()) == 1
    for action in ["approve_assignment", "order_contractor", "approve_reply"]:
        response = client.post("/api/approve", json={**request, "action": action})
        assert response.status_code == 200, response.text
        assert response.json()["audit"][-1]["event"] == action
        assert response.json()["audit"][-1]["details"]["simulated"] is True
    saved = response.json()
    assert client.get(f"/api/cases/{case['case_id']}").json() == saved
    # Replayed n8n input must not erase later approvals.
    assert client.post("/api/cases", json=case).json() == saved
    assert saved["reply_draft"]["auto_send"] is False
    assert len(client.get("/api/audit").json()) == 4


def test_manual_assignment_requires_reason_and_staff_option_adapter(client):
    scenario = next(s for s in SCENARIOS if s.id == "S4b")
    case = inbox(client, scenario)
    request = {"case_id": case["case_id"], "actor": "Prüfer", "action": "approve_assignment", "contract_id": "MV-10245"}
    assert client.post("/api/approve", json=request).status_code == 403
    assert client.post("/api/approve", json={**request, "reason": "Telefonisch mit Mieter geklärt"}).status_code == 200
    assert client.post("/api/approve", json={**request, "contract_id": "UNKNOWN", "reason": "Geprüft"}).status_code == 403
    unknown = next(s for s in SCENARIOS if s.id == "S4c")
    case = inbox(client, unknown)
    response = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "Prüfer",
                                               "action": "choose_staff_option", "option": "ask_registered_email"})
    assert response.status_code == 200, response.text
    assert response.json()["audit"][-1]["details"]["staff_option"] == "ask_registered_email"


def test_bad_requests_have_explicit_errors_and_never_write(client, monkeypatch):
    for endpoint in ["/api/cases/MISSING", "/api/cases/MISSING/reply"]:
        assert client.get(endpoint).status_code == 404
    assert client.post("/api/approve", json={"case_id": "MISSING", "actor": "Prüfer", "action": "approve_reply"}).status_code == 404
    response = client.post("/api/steps/unknown", json={"email": {"body": "Hallo"}})
    assert response.status_code == 404
    assert all(name in response.json()["detail"] for name in STEPS)
    assert client.post("/api/steps/understand", json={}).status_code == 422
    assert client.post("/api/steps/match", json={"email": {"body": "Hallo"}}).status_code == 422
    incomplete = client.post("/api/steps/understand", json={"email": {"body": "Hallo"}}).json()
    assert client.post("/api/steps/task", json={"case": incomplete}).status_code == 422
    for extra in [{"provider": "unknown"}, {"scenario_id": "../unknown"}]:
        response = client.post("/api/process", json={"email": {"body": "Hallo"}, **extra})
        assert response.status_code == (404 if "scenario_id" in extra else 422)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    response = client.post("/api/process", json={"email": {"body": "Hallo"}, "provider": "groq"})
    assert response.status_code == 422 and "GROQ_API_KEY fehlt" in response.json()["detail"]
    assert not client.app.state.store.path.exists()


def test_store_orders_newest_first_updates_in_place_and_rejects_path_escape(tmp_path):
    store = CaseStore(tmp_path / "cases")
    case, _ = run_scenario(SCENARIOS[0], provider="offline")
    older = case.model_copy(update={"case_id": "OLD", "received_at": case.received_at - timedelta(days=1)})
    store.save(case)
    store.save(older)
    assert store.list() == [case, older]
    store.save(case)
    assert len(list(store.path.glob("*.json"))) == 2
    case.warnings.append("Geprüft")
    assert store.save(case) == store.get(case.case_id)
    assert store.list()[0].warnings == case.warnings
    assert store.get("MISSING") is None
    for case_id in ["../escape", "/tmp/escape", "", ".", "nested/file"]:
        with pytest.raises(ValueError, match="Ungültige Vorgangs-ID"):
            store.save(case.model_copy(update={"case_id": case_id}))
        with pytest.raises(ValueError):
            store.get(case_id)


def test_audit_endpoint_returns_last_200_events(client):
    assert client.get("/api/audit").json() == []
    for index in range(205):
        client.app.state.audit.append(AuditEvent(ts=datetime.now(timezone.utc), actor="test", event=str(index)))
    events = client.get("/api/audit").json()
    assert len(events) == 200
    assert events[0]["event"] == "5" and events[-1]["event"] == "204"


def test_static_is_mounted_only_when_present_and_run_binds_locally(tmp_path, monkeypatch):
    static = tmp_path / "static"
    absent = create_app(static_dir=static)
    assert not any(route.path == "/static" for route in absent.routes)
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Prüfliste</title>")
    (static / "app.js").write_text("console.log('ready')")
    with TestClient(create_app(static_dir=static)) as client:
        assert "<title>Prüfliste</title>" in client.get("/").text
        assert client.get("/static/app.js").status_code == 200
    module = importlib.import_module("intake.web.app")
    calls = []
    monkeypatch.setattr(module.uvicorn, "run", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.delenv("INTAKE_PORT", raising=False)
    module.run()
    monkeypatch.setenv("INTAKE_PORT", "8123")
    module.run()
    assert calls == [{"host": "127.0.0.1", "port": 8000}, {"host": "127.0.0.1", "port": 8123}]


def test_restoring_a_changed_result_refreshes_until_a_human_acted(client):
    """Live rule changes must reach the review inbox; human-touched cases are frozen."""
    case = inbox(client)
    changed = dict(case, warnings=[*case["warnings"], "Regel geändert"], processed_at="2099-01-01T00:00:00Z")
    refreshed = client.post("/api/cases", json=changed).json()
    assert refreshed["warnings"][-1] == "Regel geändert"
    assert refreshed["audit"][-1]["event"].startswith("neu verarbeitet")
    approved = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "Test",
                                                 "action": "approve_reply"}).json()
    frozen = client.post("/api/cases", json=dict(changed, warnings=["noch einmal geändert"])).json()
    assert frozen["warnings"] == approved["warnings"]
