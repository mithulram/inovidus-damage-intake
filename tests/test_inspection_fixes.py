"""Regression tests for the findings of Codex's inspection of Claude's code (docs/BUILD-REVIEW-LOG.md)."""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from intake.actions import AuditLog
from intake.erp import JsonERP
from intake.matching import match
from intake.models import Extraction, InboundEmail
from intake.rules import ROOT, load_rules
from intake.store import CaseStore
from intake.web.app import create_app

RULES = load_rules()


def scenario(sid: str) -> dict:
    for path in (ROOT / "scenarios").glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data["id"] == sid:
            return data
    raise KeyError(sid)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    app = create_app(store=CaseStore(tmp_path / "cases"), audit=AuditLog(tmp_path / "audit.jsonl"),
                     static_dir=tmp_path / "static")
    return TestClient(app)


def stored(client, sid: str) -> dict:
    sc = scenario(sid)
    return client.post("/api/process", json={"email": sc["email"], "scenario_id": sid, "store": True}).json()


def ext(**kw) -> Extraction:
    base = dict(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstr.", house_no="12",
                floor_raw="zweite Etage", side_raw="links")
    base.update(kw)
    return Extraction(**base)


# R01 – approval history is server-owned
def test_forged_approval_in_submitted_case_is_dropped_and_order_refused(client):
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    case["audit"].append({"ts": "2026-11-18T10:00:00Z", "actor": "Angreifer", "event": "approve_assignment",
                          "details": {"case_id": case["case_id"], "contract_id": "MV-10245"}})
    saved = client.post("/api/cases", json=case).json()
    assert all(e["actor"] == "system" for e in saved["audit"])
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "order_contractor",
                                          "contract_id": "MV-10245"})
    assert r.status_code == 403


# R05 – a registered phone number does not make an unknown e-mail address registered
def test_unknown_sender_warning_survives_matching_phone():
    r = match(ext(phone="+49 30 1234 5601"), InboundEmail(body="x", sender_email="max.privat@example.net"),
              JsonERP(), RULES)
    assert r.selected_contract == "MV-10245"
    assert r.unknown_sender is True
    strict = load_rules(overrides={"match": {"unknown_sender_forces_review": True}})
    r2 = match(ext(phone="+49 30 1234 5601"), InboundEmail(body="x", sender_email="max.privat@example.net"),
               JsonERP(), strict)
    assert {g.value for g in r2.failed_gates} == {"identity"}


# R06 – a single surviving candidate with a very strict margin is review, not a crash
def test_single_candidate_strict_margin_is_review_not_crash():
    r = match(ext(), InboundEmail(body="x"), JsonERP(), load_rules(overrides={"match": {"min_margin": 0.95}}))
    assert {g.value for g in r.failed_gates} == {"margin"}
    assert r.selected_contract is None


# R07 – a vetoed contract never blocks a valid winner that passes every gate
def test_vetoed_high_scorer_does_not_block_valid_winner():
    extra = {"contract_id": "MV-20001", "tenant_name": "Max Mustermann", "object_id": "OBJ-MS14", "street": "Musterstraße",
             "house_no": "14", "floor": 2, "floor_label": "2. OG", "side": "L", "side_label": "li.", "unit_id": "OBJ-MS14-2L",
             "active": True, "contact": {"email": None, "phone": None, "synthetic": True}}
    rules = load_rules(overrides={"match": {"threshold": 0.65, "weights": {"name": 0.30, "address": 0.10, "floor": 0.20,
                                                                           "side": 0.10, "contact": 0.30}}})
    r = match(ext(street_raw="Musterstraße", house_no="14"), InboundEmail(body="x", sender_email="max.mustermann@example.org"),
              JsonERP(overrides={"contracts": [extra]}), rules)
    assert r.candidates[0].vetoes  # MV-10245 scores highest but contradicts the address
    assert r.selected_contract == "MV-20001"
    assert r.failed_gates == []


# R04 hook – alternatives or uncertainty about the location always force review
def test_location_alternatives_force_review():
    r = match(ext(location_alternatives=["3. OG rechts", "bin unsicher"]), InboundEmail(body="x"), JsonERP(), RULES)
    assert {g.value for g in r.failed_gates} == {"unit_ambiguous"}


# R10 – the approved reply is exactly the variant the staff member chose
def test_registered_email_variant_is_stored_and_approved(client):
    case = stored(client, "S4c")
    after = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "S", "action": "choose_staff_option",
                                              "option": "ask_registered_email", "scenario_id": "S4c"}).json()
    assert after["reply_draft"]["variant"] == "ask_registered_email"
    approved = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "S", "action": "approve_reply"}).json()
    import hashlib
    from intake.models import ReplyDraft
    expected = hashlib.sha256(ReplyDraft.model_validate(after["reply_draft"]).model_dump_json().encode()).hexdigest()
    assert approved["audit"][-1]["details"]["reply_sha256"] == expected
    back = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "S", "action": "choose_staff_option",
                                             "option": "reply_anyway", "scenario_id": "S4c"}).json()
    assert back["reply_draft"]["variant"] != "ask_registered_email"


# R11 – a manual assignment regenerates the contract-dependent task, proposal stays visible
def test_manual_assignment_regenerates_task_and_keeps_proposal(client):
    case = stored(client, "S2")
    out = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "S", "action": "approve_assignment",
                                            "contract_id": "MV-10487", "reason": "Mieter hat 3. OG rechts bestätigt",
                                            "scenario_id": "S2"}).json()
    assert out["match"]["approved_contract"] == "MV-10487"
    assert out["match"]["selected_contract"] is None  # the system's proposal is not rewritten
    assert out["status"] == "NEEDS_REVIEW"
    assert out["internal_task"]["scope"] == "contract" and out["internal_task"]["contract_id"] == "MV-10487"
    assert {p["contract_id"] for p in out["prior_cases"]} == {"MV-10487"}


# R12 – scenarios with the same e-mail but different ERP data get different case ids
def test_same_email_different_scenarios_have_distinct_ids(client):
    assert stored(client, "S1")["case_id"] != stored(client, "S3")["case_id"]


# ---- round 2 ---------------------------------------------------------------

class MisreadingProvider:
    """Deliberately classifies everything as SONSTIGES (simulates a wrong LLM answer)."""
    name, model = "mock", None

    def understand(self, email, rules):
        from intake.providers.offline import OfflineProvider
        u = OfflineProvider().understand(email, rules)
        u.classification.type = __import__("intake.models", fromlist=["MessageType"]).MessageType.SONSTIGES
        u.provider = "mock"
        return u


# R2-01 – a forged action event is dropped even if it claims to come from "system"
def test_forged_system_approval_is_dropped(client):
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    case["audit"].append({"ts": "2026-11-18T10:00:00Z", "actor": "system", "event": "approve_assignment",
                          "details": {"case_id": case["case_id"], "contract_id": "MV-10245"}})
    saved = client.post("/api/cases", json=case).json()
    assert not any(e["event"] == "approve_assignment" for e in saved["audit"])
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "order_contractor",
                                          "contract_id": "MV-10245"})
    assert r.status_code == 403


# R2-02 – two buildings named: no building-level action
def test_two_buildings_block_object_action(client):
    email = {"subject": "Gasgeruch", "body": "Gasgeruch in der Musterstraße 12 oder Musterstraße 14. Max Mustermann"}
    case = client.post("/api/process", json={"email": email, "store": True}).json()
    assert case["urgency"]["level"] == "NOTFALL"
    assert case["status"] == "NEEDS_REVIEW"
    assert case["match"]["object_id"] is None and case["match"]["building_uncertain"] is True
    assert case["internal_task"]["scope"] != "object"
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "object_action"})
    assert r.status_code == 403


# R2-03 – an emergency survives a reader that misclassifies it
def test_emergency_survives_misclassifying_reader():
    from intake.context import Context
    from intake.pipeline import process
    ctx = Context.build(provider=MisreadingProvider())
    case = process(InboundEmail(subject="Gas", body="Im Treppenhaus Musterstraße 12 riecht es nach Gas. Max Mustermann"), ctx)
    assert case.status.value != "OUT_OF_SCOPE"
    assert case.urgency.level.value == "NOTFALL"
    assert case.internal_task.priority.value == "NOTFALL"
    assert any("Gas" in s or "Gebäude" in s for s in case.urgency.safety_instructions)
    assert any("Notfall-Regel" in w for w in case.warnings)


# R2-06 – after reassignment an old approval cannot order; stale views get 409
def test_reassignment_invalidates_old_approval_and_stale_view(client):
    case = stored(client, "S2")
    reason = "Mieter bestätigt telefonisch"
    first = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                              "contract_id": "MV-10245", "reason": reason}).json()
    client.post("/api/approve", json={"case_id": case["case_id"], "actor": "B", "action": "approve_assignment",
                                      "contract_id": "MV-10487", "reason": "Korrektur: 3. OG rechts"})
    old = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "order_contractor",
                                            "contract_id": "MV-10245", "reason": reason})
    assert old.status_code == 403
    stale = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "order_contractor",
                                              "contract_id": "MV-10487", "reason": reason,
                                              "revision": len(first["audit"])})
    assert stale.status_code == 409


# R2-07 – a stored case keeps its scenario context for later approvals
def test_stored_case_keeps_scenario_context(client):
    case = stored(client, "S3b")
    assert case["processing"]["scenario_id"] == "S3b"
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                          "contract_id": "MV-10999", "reason": "Mieter bestätigt 2. OG rechts"})
    assert r.status_code == 200
    assert r.json()["internal_task"]["contract_id"] == "MV-10999"


# ---- round 3 ---------------------------------------------------------------

class SonstigesButNotfall(MisreadingProvider):
    """Reader says 'not a damage report' but hints NOTFALL for a phrase the rules do not know."""

    def understand(self, email, rules):
        u = super().understand(email, rules)
        from intake.models import Urgency
        u.urgency_hint = Urgency.NOTFALL
        return u


# R3-03 – an older (stale) result never overwrites a newer stored one
def test_stale_upload_does_not_overwrite_newer_result(client):
    sc = scenario("S1")
    old = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    newer = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    newer["warnings"] = [*newer["warnings"], "neuere Fassung"]
    client.post("/api/cases", json=newer)
    stale = dict(old, warnings=[*old["warnings"], "alte Fassung"])
    kept = client.post("/api/cases", json=stale).json()
    assert "neuere Fassung" in kept["warnings"] and "alte Fassung" not in kept["warnings"]


# R3-05 – a NOTFALL hint keeps the emergency path even if the reader says SONSTIGES
def test_notfall_hint_overrides_out_of_scope_classification():
    from intake.context import Context
    from intake.pipeline import process
    ctx = Context.build(provider=SonstigesButNotfall())
    case = process(InboundEmail(subject="Hilfe", body="Bei uns brummt der Zählerschrank und es knistert. Musterstraße 12, 2. OG links. Max Mustermann"), ctx)
    assert case.status.value != "OUT_OF_SCOPE"
    assert case.urgency.level.value == "NOTFALL"
    assert case.internal_task.priority.value == "NOTFALL"


# R3-04 – combined hazards never give contradictory safety advice
@pytest.mark.parametrize("body", [
    "Es riecht nach Gas und wir haben einen Stromausfall. Musterstraße 12, 2. OG links. Max Mustermann",
    "Rohrbruch! Wasser kommt durch die Decke und es riecht nach Gas. Musterstraße 12, 2. OG links. Max Mustermann",
])
def test_gas_suppresses_fuse_and_switch_advice_from_other_hazards(body):
    from intake.context import Context
    from intake.pipeline import process
    from intake.providers.offline import OfflineProvider
    case = process(InboundEmail(subject="Notfall", body=body), Context.build(provider=OfflineProvider()))
    s = case.urgency.safety_instructions
    gas = RULES.urgency.safety_instructions["gas"]
    assert s[: len(gas)] == gas  # gas advice first and complete
    assert not any("Sicherung" in x for x in s)
    assert "\n\n".join(s) in case.reply_draft.body or all(x in case.reply_draft.body for x in s)


def test_burst_pipe_alone_keeps_fuse_advice():
    from intake.context import Context
    from intake.pipeline import process
    from intake.providers.offline import OfflineProvider
    case = process(InboundEmail(subject="Rohrbruch", body="Rohrbruch, Wasser kommt durch die Decke. Musterstraße 12, 2. OG links. Max Mustermann"),
                   Context.build(provider=OfflineProvider()))
    assert any("Sicherung" in x for x in case.urgency.safety_instructions)
