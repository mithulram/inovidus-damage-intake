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
