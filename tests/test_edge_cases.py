"""Regression tests for edge cases found while testing (see deliverables/07_Tests_und_Sicherheit.md)."""

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


def reseal(client, case: dict) -> dict:
    """Simulate a different result that this server legitimately produced (sealed with its own key)."""
    from intake.models import CaseRecord
    return client.app.state.sealer.seal(CaseRecord.model_validate(case)).model_dump(mode="json")


def stored(client, sid: str) -> dict:
    sc = scenario(sid)
    return client.post("/api/process", json={"email": sc["email"], "scenario_id": sid, "store": True}).json()


def ext(**kw) -> Extraction:
    base = dict(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstr.", house_no="12",
                floor_raw="zweite Etage", side_raw="links")
    base.update(kw)
    return Extraction(**base)


# approval history is server-owned
def test_forged_approval_in_submitted_case_is_dropped_and_order_refused(client):
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    case["audit"].append({"ts": "2026-11-18T10:00:00Z", "actor": "Angreifer", "event": "approve_assignment",
                          "details": {"case_id": case["case_id"], "contract_id": "MV-10245"}})
    saved = client.post("/api/cases", json=reseal(client, case)).json()
    assert all(e["actor"] == "system" for e in saved["audit"])
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "order_contractor",
                                          "contract_id": "MV-10245"})
    assert r.status_code == 403


# a registered phone number does not make an unknown e-mail address registered
def test_unknown_sender_warning_survives_matching_phone():
    r = match(ext(phone="+49 30 1234 5601"), InboundEmail(body="x", sender_email="max.privat@example.net"),
              JsonERP(), RULES)
    assert r.selected_contract == "MV-10245"
    assert r.unknown_sender is True
    strict = load_rules(overrides={"match": {"unknown_sender_forces_review": True}})
    r2 = match(ext(phone="+49 30 1234 5601"), InboundEmail(body="x", sender_email="max.privat@example.net"),
               JsonERP(), strict)
    assert {g.value for g in r2.failed_gates} == {"identity"}


# a single surviving candidate with a very strict margin is review, not a crash
def test_single_candidate_strict_margin_is_review_not_crash():
    r = match(ext(), InboundEmail(body="x"), JsonERP(), load_rules(overrides={"match": {"min_margin": 0.95}}))
    assert {g.value for g in r.failed_gates} == {"margin"}
    assert r.selected_contract is None


# a vetoed contract never blocks a valid winner that passes every gate
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


# alternatives or uncertainty about the location always force review
def test_location_alternatives_force_review():
    r = match(ext(location_alternatives=["3. OG rechts", "bin unsicher"]), InboundEmail(body="x"), JsonERP(), RULES)
    assert {g.value for g in r.failed_gates} == {"unit_ambiguous"}


# the approved reply is exactly the variant the staff member chose
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


# a manual assignment regenerates the contract-dependent task, proposal stays visible
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


# scenarios with the same e-mail but different ERP data get different case ids
def test_same_email_different_scenarios_have_distinct_ids(client):
    assert stored(client, "S1")["case_id"] != stored(client, "S3")["case_id"]


# ---- edge cases, part 2 --------------------------------------------------

class MisreadingProvider:
    """Deliberately classifies everything as SONSTIGES (simulates a wrong LLM answer)."""
    name, model = "mock", None

    def understand(self, email, rules):
        from intake.providers.offline import OfflineProvider
        u = OfflineProvider().understand(email, rules)
        u.classification.type = __import__("intake.models", fromlist=["MessageType"]).MessageType.SONSTIGES
        u.provider = "mock"
        return u


# a forged action event is dropped even if it claims to come from "system"
def test_forged_system_approval_is_dropped(client):
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    case["audit"].append({"ts": "2026-11-18T10:00:00Z", "actor": "system", "event": "approve_assignment",
                          "details": {"case_id": case["case_id"], "contract_id": "MV-10245"}})
    saved = client.post("/api/cases", json=reseal(client, case)).json()
    assert not any(e["event"] == "approve_assignment" for e in saved["audit"])
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "order_contractor",
                                          "contract_id": "MV-10245"})
    assert r.status_code == 403


# two buildings named: no building-level action
def test_two_buildings_block_object_action(client):
    email = {"subject": "Gasgeruch", "body": "Gasgeruch in der Musterstraße 12 oder Musterstraße 14. Max Mustermann"}
    case = client.post("/api/process", json={"email": email, "store": True}).json()
    assert case["urgency"]["level"] == "NOTFALL"
    assert case["status"] == "NEEDS_REVIEW"
    assert case["match"]["object_id"] is None and case["match"]["building_uncertain"] is True
    assert case["internal_task"]["scope"] != "object"
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "object_action"})
    assert r.status_code == 403


# an emergency survives a reader that misclassifies it
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


# after reassignment an old approval cannot order; stale views get 409
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


# a stored case keeps its scenario context for later approvals
def test_stored_case_keeps_scenario_context(client):
    case = stored(client, "S3b")
    assert case["processing"]["scenario_id"] == "S3b"
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                          "contract_id": "MV-10999", "reason": "Mieter bestätigt 2. OG rechts"})
    assert r.status_code == 200
    assert r.json()["internal_task"]["contract_id"] == "MV-10999"


# ---- edge cases, part 3 --------------------------------------------------

class SonstigesButNotfall(MisreadingProvider):
    """Reader says 'not a damage report' but hints NOTFALL for a phrase the rules do not know."""

    def understand(self, email, rules):
        u = super().understand(email, rules)
        from intake.models import Urgency
        u.urgency_hint = Urgency.NOTFALL
        return u


# an older (stale) result never overwrites a newer stored one
def test_stale_upload_does_not_overwrite_newer_result(client):
    sc = scenario("S1")
    old = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    newer = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    newer["warnings"] = [*newer["warnings"], "neuere Fassung"]
    client.post("/api/cases", json=reseal(client, newer))
    stale = dict(old, warnings=[*old["warnings"], "alte Fassung"])
    kept = client.post("/api/cases", json=reseal(client, stale)).json()
    assert "neuere Fassung" in kept["warnings"] and "alte Fassung" not in kept["warnings"]


# a NOTFALL hint keeps the emergency path even if the reader says SONSTIGES
def test_notfall_hint_overrides_out_of_scope_classification():
    from intake.context import Context
    from intake.pipeline import process
    ctx = Context.build(provider=SonstigesButNotfall())
    case = process(InboundEmail(subject="Hilfe", body="Bei uns brummt der Zählerschrank und es knistert. Musterstraße 12, 2. OG links. Max Mustermann"), ctx)
    assert case.status.value != "OUT_OF_SCOPE"
    assert case.urgency.level.value == "NOTFALL"
    assert case.internal_task.priority.value == "NOTFALL"


# combined hazards never give contradictory safety advice
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


# ---- edge cases, part 4 --------------------------------------------------

# every way of saying "the building is uncertain" blocks building actions
@pytest.mark.parametrize("alternative", ["Bei der Anschrift bin ich unsicher", "not sure about the house number",
                                         "Hausnummer weiß ich nicht genau", "unsure which building"])
def test_building_uncertainty_words(alternative):
    r = match(ext(location_alternatives=[alternative]), InboundEmail(body="x"), JsonERP(), RULES)
    assert r.building_uncertain is True and r.object_id is None


def test_anschrift_uncertainty_end_to_end(client):
    email = {"subject": "Gasgeruch", "body": "Gasgeruch. Musterstr. 12, 2. OG links; Bei der Anschrift bin ich unsicher. Viele Grüße, Max Mustermann"}
    case = client.post("/api/process", json={"email": email, "store": True}).json()
    assert case["match"]["object_id"] is None
    assert case["internal_task"]["scope"] != "object"
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "object_action"})
    assert r.status_code == 403


# ---- edge cases, part 5 --------------------------------------------------

class GasReader(MisreadingProvider):
    """Reader recognises gas (category + NOTFALL) in a phrasing the keyword rules may not know."""

    def understand(self, email, rules):
        from intake.models import MessageType, Urgency
        u = super().understand(email, rules)
        u.classification.type, u.classification.category = MessageType.SCHADENMELDUNG, "Gasgeruch"
        u.urgency_hint = Urgency.NOTFALL
        return u


# gas recognised by the reader activates gas advice and suppresses fuse advice
def test_reader_recognised_gas_drives_safety_advice():
    from intake.context import Context
    from intake.pipeline import process
    case = process(InboundEmail(subject="Rohrbruch", body="Rohrbruch, Wasser kommt durch die Decke. Es müffelt komisch nach Leitung. Musterstraße 12, 2. OG links. Max Mustermann"),
                   Context.build(provider=GasReader()))
    s = case.urgency.safety_instructions
    assert s[0] == RULES.urgency.safety_instructions["gas"][0]
    assert not any("Sicherung" in x for x in s)


# a run that started earlier never overwrites a newer stored result, however late it finishes
def test_late_finishing_old_run_does_not_overwrite(client):
    sc = scenario("S1")
    old = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    new = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    new["warnings"] = [*new["warnings"], "neu"]
    client.post("/api/cases", json=reseal(client, new))
    old["processed_at"] = "2099-01-01T00:00:00Z"  # finished last
    old["warnings"] = [*old["warnings"], "alt"]
    kept = client.post("/api/cases", json=reseal(client, old)).json()
    assert "neu" in kept["warnings"] and "alt" not in kept["warnings"]


# approving after the rules changed is refused (re-process first)
def test_approval_refused_when_rules_changed(client):
    case = stored(client, "S1")
    from intake.web import app as app_module
    stored_case = client.get(f"/api/cases/{case['case_id']}").json()
    stored_case["processing"]["rules_version"] = "sha256:veraltet"
    store = client.app.state.store
    from intake.models import CaseRecord
    store.save(CaseRecord.model_validate(stored_case))
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                          "contract_id": "MV-10245"})
    assert r.status_code == 409 and "Regeln" in r.json()["detail"]


def test_compact_street_and_number_counts_as_building_uncertainty():
    r = match(ext(location_alternatives=["Vielleicht Musterstraße12"]), InboundEmail(body="x"), JsonERP(), RULES)
    assert r.building_uncertain is True and r.object_id is None


# ---- edge cases, part 6 --------------------------------------------------

# doubt without a floor/side reference is treated as doubt about the building (fail-safe)
def test_unspecific_doubt_blocks_building_action(client):
    email = {"subject": "Gasgeruch", "body": "Gasgeruch. Musterstr. 12; ich bin unsicher. Viele Grüße, Max Mustermann"}
    case = client.post("/api/process", json={"email": email, "store": True}).json()
    assert case["match"]["object_id"] is None and case["internal_task"]["scope"] != "object"
    assert client.post("/api/approve", json={"case_id": case["case_id"], "actor": "X", "action": "object_action"}).status_code == 403


def test_floor_only_doubt_keeps_building():
    r = match(ext(location_alternatives=["3. OG rechts"]), InboundEmail(body="x"), JsonERP(), RULES)
    assert r.building_uncertain is False and r.object_id == "OBJ-MS12"


# after a human action and a rule change, re-processing supersedes the proposal and voids old approvals
def test_reprocess_after_rule_change_supersedes_and_voids_approvals(client, monkeypatch):
    import intake.web.app as app_module
    from intake.rules import load_rules as real_load
    case = stored(client, "S1")
    client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                      "contract_id": "MV-10245"})
    changed = lambda overrides=None, path=None: real_load(path, {**(overrides or {}), "match": {"threshold": 0.95}})
    monkeypatch.setattr("intake.context.load_rules", changed)
    blocked = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "order_contractor",
                                                "contract_id": "MV-10245"})
    assert blocked.status_code == 409
    sc = scenario("S1")
    new = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1", "store": True}).json()
    assert new["status"] == "NEEDS_REVIEW"  # 0.90 < 0.95
    assert new["audit"][-1]["event"].startswith("neu verarbeitet (Regeln geändert)")
    assert any(e["event"] == "approve_assignment" for e in new["audit"])  # history kept
    stale = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "order_contractor",
                                              "contract_id": "MV-10245", "reason": "alt"})
    assert stale.status_code == 403  # the old approval no longer counts


# the generation watermark advances even when the result is unchanged
def test_watermark_blocks_older_run_after_identical_newer_run(client):
    sc = scenario("S1")
    first = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1", "store": True}).json()
    slow_old = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1", "provider": "recorded"}).json()
    client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1", "store": True})  # newest, identical
    slow_old["warnings"] = [*slow_old["warnings"], "langsam"]
    kept = client.post("/api/cases", json=reseal(client, slow_old)).json()
    assert "langsam" not in kept["warnings"] and kept["processing"]["provider"] == first["processing"]["provider"]


# staff options follow the human-approved contract
def test_staff_options_follow_manual_assignment(client):
    case = stored(client, "S4b")
    out = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                            "contract_id": "MV-10112", "reason": "Erika ist Mieterin im EG"}).json()
    call = next((o for o in out["staff_options"] if o["code"] == "call_tenant"), None)
    assert call is None or (call["available"] is False and not call.get("detail"))


# contact state is consistent after reassignment, in both directions
def test_contact_state_consistent_after_reassignment(client):
    sc = scenario("S2")
    email = {**sc["email"], "sender_email": "max.mustermann@example.org"}
    case = client.post("/api/process", json={"email": email, "scenario_id": "S2", "store": True}).json()
    assert case["match"]["unknown_sender"] is False
    out = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                            "contract_id": "MV-10112", "reason": "Test: Erika"}).json()
    assert out["match"]["unknown_sender"] is True
    assert "Nicht von der registrierten E-Mail-Adresse" in out["warnings"]
    opt = next(o for o in out["staff_options"] if o["available"])
    ok = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "choose_staff_option",
                                           "option": opt["code"]})
    assert ok.status_code == 200
    back = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                             "contract_id": "MV-10245", "reason": "doch Max"}).json()
    assert back["match"]["unknown_sender"] is False and back["staff_options"] == []
    assert "Nicht von der registrierten E-Mail-Adresse" not in back["warnings"]


@pytest.mark.parametrize("body,street", [
    ("Hilfe Musterstraße 12 2. OG li. Max Mustermann", "Musterstraße"),
    ("Adresse: Musterstraße 12, 2. OG links. Max Mustermann", "Musterstraße"),
    ("Alte Musterstraße 12, 2. OG links. Max Mustermann", "Alte Musterstraße"),
])
def test_street_prefix_stoplist(body, street):
    from intake.providers.offline import OfflineProvider
    assert OfflineProvider().understand(InboundEmail(subject="x", body=body), RULES).extraction.street_raw == street


# ---- edge cases, part 7 --------------------------------------------------

# an incomplete address earns no points (street without number cannot reach the threshold)
@pytest.mark.parametrize("street,house", [("Musterstraße", None), (None, "12")])
def test_incomplete_address_scores_zero(street, house):
    r = match(ext(street_raw=street, house_no=house), InboundEmail(body="x", sender_email="max.mustermann@example.org"),
              JsonERP(), RULES)
    win = next(c for c in r.candidates if c.contract_id == "MV-10245")
    assert next(s for s in win.signals if s.name == "address").points == 0
    assert r.selected_contract is None and "threshold" in {g.value for g in r.failed_gates}


# ---- edge cases, part 8 --------------------------------------------------

# after a supersede, the new proposal is not "human-touched" by the old approvals
def test_superseded_history_does_not_freeze_new_proposal(client, monkeypatch):
    from intake.rules import load_rules as real_load
    case = stored(client, "S1")
    client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                      "contract_id": "MV-10245"})
    monkeypatch.setattr("intake.context.load_rules",
                        lambda overrides=None, path=None: real_load(path, {**(overrides or {}), "match": {"threshold": 0.95}}))
    sc = scenario("S1")
    client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1", "store": True})  # supersedes
    other_reader = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1", "store": True,
                                                     "provider": "recorded"}).json()
    assert other_reader["processing"]["provider"] == "recorded(groq)"  # newer result accepted, not frozen


# ---- edge cases, part 9 --------------------------------------------------

def _save(client, case: dict) -> None:
    from intake.models import CaseRecord
    client.app.state.store.save(CaseRecord.model_validate(case))


# the ERP data the reviewer saw is pinned; a change blocks approval and voids old approvals
def test_case_records_erp_version(client):
    case = stored(client, "S1")
    assert case["processing"]["erp_version"] == JsonERP().version
    assert JsonERP(overrides={"contracts": [{"contract_id": "MV-10245", "active": False}]}).version != JsonERP().version


def test_approval_refused_when_erp_data_changed(client):
    case = stored(client, "S1")
    old = client.get(f"/api/cases/{case['case_id']}").json()
    old["processing"]["erp_version"] = "sha256:veraltet"
    _save(client, old)
    r = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                          "contract_id": "MV-10245"})
    assert r.status_code == 409 and "ERP-Daten" in r.json()["detail"]


def test_erp_change_supersedes_frozen_proposal_and_voids_approvals(client):
    case = stored(client, "S1")
    client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                      "contract_id": "MV-10245"})
    old = client.get(f"/api/cases/{case['case_id']}").json()
    old["processing"]["erp_version"] = "sha256:alt"  # approved on older ERP data
    _save(client, old)
    sc = scenario("S1")
    new = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1", "store": True}).json()
    assert new["audit"][-1]["event"].startswith("neu verarbeitet (ERP-Daten geändert)")
    assert new["processing"]["erp_version"] == JsonERP().version
    stale = client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "order_contractor",
                                              "contract_id": "MV-10245", "reason": "alt"})
    assert stale.status_code == 403  # the approval given on the old data no longer counts


# a single field holding alternatives is ambiguous for every provider (not only the rules reader)
@pytest.mark.parametrize("field,value", [("floor_raw", "2. bzw. 3. OG"), ("floor_raw", "2./3. Etage"),
                                         ("side_raw", "links bzw. rechts"), ("side_raw", "links oder rechts")])
def test_compound_unit_value_forces_review(field, value):
    r = match(ext(**{field: value}), InboundEmail(body="x", sender_email="max.mustermann@example.org"), JsonERP(), RULES)
    assert r.selected_contract is None and "unit_ambiguous" in {g.value for g in r.failed_gates}
    assert r.building_uncertain is False and r.object_id == "OBJ-MS12"


@pytest.mark.parametrize("field,value", [("house_no", "12-14"), ("house_no", "12 oder 14"),
                                         ("street_raw", "Musterstr. bzw. Hauptstr.")])
def test_compound_address_value_makes_building_uncertain(field, value):
    r = match(ext(**{field: value}), InboundEmail(body="x", sender_email="max.mustermann@example.org"), JsonERP(), RULES)
    assert r.selected_contract is None and r.building_uncertain is True and r.object_id is None


def test_compound_floor_is_unclear_not_last_number():
    from intake.normalize import normalize_floor
    assert normalize_floor("2. bzw. 3. OG", RULES.normalize)[:2] == (None, "unclear")
    assert normalize_floor("zweite Etage", RULES.normalize)[:2] == (2, "ok")


# every step of a chain runs on the rules and ERP data the case started with
def test_step_rejects_case_from_other_rules_version(client):
    sc = scenario("S1")
    case = client.post("/api/steps/understand", json={"email": sc["email"], "scenario_id": "S1"}).json()
    case["processing"]["rules_version"] = "sha256:anders"
    r = client.post("/api/steps/match", json={"case": reseal(client, case), "scenario_id": "S1"})
    assert r.status_code == 409 and "Regeln" in r.json()["detail"]
    case["processing"]["rules_version"] = RULES.version
    case["processing"]["erp_version"] = "sha256:anders"
    r = client.post("/api/steps/match", json={"case": reseal(client, case), "scenario_id": "S1"})
    assert r.status_code == 409 and "ERP-Daten" in r.json()["detail"]


def test_store_rejects_proposal_built_on_old_basis(client):
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    case["processing"]["erp_version"] = "sha256:alt"
    assert client.post("/api/cases", json=reseal(client, case)).status_code == 409


# ---- edge cases, part 10 --------------------------------------------------

# a floor range or list written in words never collapses to one floor
@pytest.mark.parametrize("floor", ["zweite bis dritte Etage", "EG, 2. OG", "zwischen 2. und 3. OG", "erste, zweite Etage",
                                   "2nd to 3rd floor", "Erdgeschoss oder erste Etage"])
def test_floor_range_in_words_forces_review(floor):
    from intake.normalize import normalize_floor
    assert normalize_floor(floor, RULES.normalize)[:2] == (None, "unclear")
    r = match(ext(floor_raw=floor, side_raw="rechts"), InboundEmail(body="x", sender_email="max.mustermann@example.org"),
              JsonERP(), RULES)
    assert r.selected_contract is None and "unit_ambiguous" in {g.value for g in r.failed_gates}


@pytest.mark.parametrize("floor,expected", [("zweite Etage", 2), ("2. OG", 2), ("im zweiten Stock", 2), ("EG", 0),
                                            ("Erdgeschoss", 0), ("3. Obergeschoss", 3)])
def test_single_floor_still_definite(floor, expected):
    from intake.normalize import normalize_floor
    assert normalize_floor(floor, RULES.normalize)[:2] == (expected, "ok")


# ---- edge cases, part 11 --------------------------------------------------

def _process(client, body: str, subject: str = "Schaden") -> dict:
    return client.post("/api/process", json={"email": {"subject": subject, "body": body,
                                                       "sender_email": "max.mustermann@example.org"}}).json()


# the rules reader keeps every floor of a range or list
@pytest.mark.parametrize("floor", ["Zwischen 2. und 3. OG rechts", "erste, zweite Etage links", "2. und 3. Etage links"])
def test_offline_reader_keeps_floor_lists(client, floor):
    case = _process(client, f"Wasser läuft aus der Spüle. Musterstraße 12. {floor}. Viele Grüße, Max Mustermann")
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None
    assert "unit_ambiguous" in case["match"]["failed_gates"]


def test_house_number_before_floor_is_not_a_floor_list(client):
    case = _process(client, "Wasser läuft aus der Spüle. Musterstraße 12, zweite Etage links. Viele Grüße, Max Mustermann")
    assert case["status"] == "READY_FOR_APPROVAL" and case["match"]["selected_contract"] == "MV-10245"


# a record without its rules/ERP basis is never trusted
@pytest.mark.parametrize("field", ["rules_version", "erp_version"])
@pytest.mark.parametrize("value", [None, ""])
def test_unversioned_records_are_refused(client, field, value):
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    case["processing"][field] = value
    assert client.post("/api/cases", json=reseal(client, case)).status_code == 409
    assert client.post("/api/steps/match", json={"case": reseal(client, case), "scenario_id": "S1"}).status_code == 409
    stored_case = stored(client, "S1")
    stored_case = client.get(f"/api/cases/{stored_case['case_id']}").json()
    stored_case["processing"][field] = value
    _save(client, stored_case)
    r = client.post("/api/approve", json={"case_id": stored_case["case_id"], "actor": "A",
                                          "action": "approve_assignment", "contract_id": "MV-10245"})
    assert r.status_code == 409 and "neu verarbeiten" in r.json()["detail"]


# "läuft aus" without water context is not damage
def test_contract_ending_question_is_not_water_damage(client):
    case = _process(client, "Mein Mietvertrag läuft aus. Wie erhalte ich meine Kaution? Musterstr. 12, 2. OG links. "
                            "Viele Grüße, Max Mustermann", subject="Frage zum Vertrag")
    assert case["status"] == "OUT_OF_SCOPE"
    assert case["understanding"]["classification"]["type"] == "ANFRAGE_MIETE"
    assert case["urgency"]["level"] == "NORMAL"


def test_real_leak_with_laeuft_aus_still_urgent(client):
    case = _process(client, "Seit heute läuft aus dem Siphon unter der Spüle ständig Wasser. Musterstraße 12, zweite Etage "
                            "links. Viele Grüße, Max Mustermann")
    assert case["understanding"]["classification"]["type"] == "SCHADENMELDUNG" and case["urgency"]["level"] == "DRINGEND"


# ---- edge cases, part 12 --------------------------------------------------

# a proposal is trusted only as this server produced it (status, match, building cannot be edited)
def test_edited_proposal_is_refused(client):
    sc = scenario("S2")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S2"}).json()
    case["status"] = "READY_FOR_APPROVAL"
    case["match"]["selected_contract"] = "MV-10487"
    r = client.post("/api/cases", json=case)
    assert r.status_code == 409 and "nicht unverändert" in r.json()["detail"]
    assert client.post("/api/steps/task", json={"case": case, "scenario_id": "S2"}).status_code == 409


def test_edited_building_is_refused(client):
    email = {"subject": "Gasgeruch", "body": "Gasgeruch. Musterstr. 12; ich bin unsicher. Viele Grüße, Max Mustermann"}
    case = client.post("/api/process", json={"email": email}).json()
    case["match"]["object_id"], case["match"]["building_uncertain"] = "OBJ-MS12", False
    assert client.post("/api/cases", json=case).status_code == 409


def test_unsealed_and_untouched_cases(client):
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()
    assert case["processing"]["signature"].startswith("hmac-sha256:")
    assert client.post("/api/cases", json=dict(case, processing={**case["processing"], "signature": None})).status_code == 409
    assert client.post("/api/cases", json=case).status_code == 200  # an unchanged server result is accepted
    chain = client.post("/api/steps/understand", json={"email": sc["email"], "scenario_id": "S1"}).json()
    assert client.post("/api/steps/match", json={"case": chain, "scenario_id": "S1"}).status_code == 200


# a negated floor/side/address is doubt, never a definite value
@pytest.mark.parametrize("field,value", [("side_raw", "nicht links"), ("floor_raw", "nicht im 2. OG"),
                                         ("side_raw", "not left")])
def test_negated_raw_value_forces_review(field, value):
    r = match(ext(**{field: value}), InboundEmail(body="x", sender_email="max.mustermann@example.org"), JsonERP(), RULES)
    assert r.selected_contract is None and "unit_ambiguous" in {g.value for g in r.failed_gates}


@pytest.mark.parametrize("text", ["Musterstr. 12, 2. OG, aber nicht links.", "Musterstraße 12, nicht im 2. OG, links.",
                                  "Musterstraße 12, zweite Etage, also nicht rechts."])
def test_negated_place_in_email_forces_review(client, text):
    case = _process(client, f"Wasser läuft aus der Spüle. {text} Viele Grüße, Max Mustermann")
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None


def test_plain_location_without_negation_still_matches(client):
    case = _process(client, "Wasser läuft aus der Spüle. Musterstraße 12, zweite Etage links. Ich weiß nicht, seit wann. "
                            "Viele Grüße, Max Mustermann")
    assert case["status"] == "READY_FOR_APPROVAL" and case["match"]["selected_contract"] == "MV-10245"


def test_sealed_case_survives_a_javascript_round_trip(client):
    """n8n and the browser parse JSON as JavaScript numbers: every integer must stay exact (< 2**53)."""
    sc = scenario("S1")
    case = client.post("/api/process", json={"email": sc["email"], "scenario_id": "S1"}).json()

    def ints(x):
        if isinstance(x, bool):
            return []
        if isinstance(x, int):
            return [x]
        if isinstance(x, dict):
            return [i for v in x.values() for i in ints(v)]
        if isinstance(x, list):
            return [i for v in x for i in ints(v)]
        return []
    assert all(abs(i) < 2**53 for i in ints(case))


# ---- edge cases, part 13 --------------------------------------------------

# negation anywhere earlier in the clause ("nicht mehr im 2. OG") is doubt
@pytest.mark.parametrize("text", ["Musterstraße 12. Wir wohnen nicht mehr im 2. OG links.",
                                  "Musterstraße 12. Früher im 2. OG links, jetzt woanders."])
def test_negated_clause_forces_review(client, text):
    case = _process(client, f"Wasser läuft aus der Spüle. {text} Viele Grüße, Max Mustermann")
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None


def test_negation_in_other_clause_does_not_block(client):
    case = _process(client, "Die Spüle ist nicht dicht, Wasser läuft aus der Spüle. Musterstraße 12, zweite Etage links. "
                            "Viele Grüße, Max Mustermann")
    assert case["status"] == "READY_FOR_APPROVAL" and case["match"]["selected_contract"] == "MV-10245"


# a street-name preposition is kept or makes the address doubtful, never silently dropped
@pytest.mark.parametrize("text", ["Adresse: Am Beispielweg 7, 1. OG links.", "Wir wohnen am Beispielweg 7, 1. OG links."])
def test_street_prefix_is_not_dropped(client, text):
    case = client.post("/api/process", json={"email": {"subject": "Schaden", "body": f"Wasser läuft aus der Spüle. {text} "
                                             "Viele Grüße, Maximilian Muster"}}).json()
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None


def test_capitalised_street_prefix_mid_sentence_is_part_of_name():
    from intake.providers.offline import OfflineProvider
    e = OfflineProvider().understand(InboundEmail(subject="x", body="Wasser läuft aus der Spüle in Am Beispielweg 7, "
                                                  "1. OG links. Viele Grüße, Maximilian Muster"), RULES).extraction
    assert e.street_raw == "Am Beispielweg"


# the e-mail header name counts as the writer for every provider
def test_header_name_of_other_person_forces_identity_review(client):
    body = {"subject": "Schaden", "sender_display_name": "Erika Muster", "sender_email": "erika.muster@example.net",
            "body": "Wasser läuft aus der Spüle. Wohnung von Max Mustermann, Musterstraße 12, 2. OG links."}
    case = client.post("/api/process", json={"email": body}).json()
    assert case["status"] == "NEEDS_REVIEW" and "identity" in case["match"]["failed_gates"]


def test_header_name_reaches_the_llm_message():
    from intake.providers.llm_schema import build_user_message
    msg = build_user_message(InboundEmail(body="x", sender_email="e@example.net", sender_display_name="Erika Muster"))
    assert "Erika Muster <e@example.net>" in msg


# ---- edge cases, part 14 --------------------------------------------------

# negation after the place, in the same clause
@pytest.mark.parametrize("text", ["In der Musterstraße 12, 2. OG links wohnen wir nicht mehr.",
                                  "Musterstraße 12, zweite Etage links ist nicht unsere Wohnung."])
def test_negation_after_place_forces_review(client, text):
    case = _process(client, f"Wasser läuft aus der Spüle. {text} Viele Grüße, Max Mustermann")
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None


def test_negation_in_following_clause_does_not_block(client):
    case = _process(client, "Musterstraße 12, zweite Etage links, und das Wasser läuft aus der Spüle und hört nicht auf. "
                            "Viele Grüße, Max Mustermann")
    assert case["status"] == "READY_FOR_APPROVAL" and case["match"]["selected_contract"] == "MV-10245"


# only completely processed records enter the inbox or allow actions; steps run once, in order
def test_partial_emergency_cannot_enter_inbox_or_be_acted_on(client):
    sc = scenario("S5b")
    case = client.post("/api/steps/understand", json={"email": sc["email"], "scenario_id": "S5b"}).json()
    case = client.post("/api/steps/match", json={"case": case, "scenario_id": "S5b"}).json()
    r = client.post("/api/cases", json=case)
    assert r.status_code == 422 and "nicht fertig" in r.json()["detail"]
    from intake.models import CaseRecord
    partial = CaseRecord.model_validate(case)
    with pytest.raises(PermissionError):
        from intake.actions import Approval, execute
        execute(partial, Approval(case_id=partial.case_id, actor="A", action="object_action"),
                client.app.state.audit)


def test_steps_cannot_be_rerun_out_of_order(client):
    sc = scenario("S1")
    body = {"email": sc["email"], "scenario_id": "S1"}
    case = client.post("/api/steps/understand", json=body).json()
    assert client.post("/api/steps/urgency", json={"case": case, "scenario_id": "S1"}).status_code == 422
    for name in ("match", "prior_cases", "urgency", "draft", "task"):
        case = client.post(f"/api/steps/{name}", json={"case": case, "scenario_id": "S1"}).json()
    assert client.post("/api/steps/match", json={"case": case, "scenario_id": "S1"}).status_code == 422
    assert client.post("/api/cases", json=case).status_code == 200


# ---- edge cases, part 15 --------------------------------------------------

@pytest.mark.parametrize("text", ["Musterstraße 12, 2. OG links (oder doch 3.?).", "Musterstraße 12, 2. OG links (glaube ich)."])
def test_hedging_bracket_after_place_forces_review(client, text):
    case = _process(client, f"Wasser läuft aus der Spüle. {text} Viele Grüße, Max Mustermann")
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None


@pytest.mark.parametrize("text", ["Ich wohne Musterstraße 12, 2. OG links, schreibe aber für meine Mutter. Viele Grüße, Max Mustermann",
                                  "Musterstraße 12, 2. OG links. Viele Grüße, Max Mustermann i. A. Hausverwaltung Schmidt"])
def test_writing_for_someone_else_is_not_the_tenant(client, text):
    case = _process(client, f"Wasser läuft aus der Spüle. {text}")
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None


def test_plain_bracket_after_place_still_matches(client):
    case = _process(client, "Wasser läuft aus der Spüle. Musterstraße 12, 2. OG links (Küche). Viele Grüße, Max Mustermann")
    assert case["status"] == "READY_FOR_APPROVAL" and case["match"]["selected_contract"] == "MV-10245"


# ---- edge cases, part 16 --------------------------------------------------

# a wrapped line inside a sentence does not hide a negation
@pytest.mark.parametrize("text", ["Musterstraße 12, 2. OG links wohnen wir\nnicht mehr.",
                                  "Musterstraße 12, wir wohnen nicht\nmehr im 2. OG links."])
def test_line_wrap_does_not_hide_negation(client, text):
    case = _process(client, f"Wasser läuft aus der Spüle. {text} Viele Grüße, Max Mustermann")
    assert case["status"] == "NEEDS_REVIEW" and case["match"]["selected_contract"] is None


def test_blank_line_still_separates_negation(client):
    case = _process(client, "Musterstraße 12, zweite Etage links\n\nNicht dringend, aber Wasser läuft aus der Spüle. "
                            "Viele Grüße, Max Mustermann")
    assert case["status"] == "READY_FOR_APPROVAL" and case["match"]["selected_contract"] == "MV-10245"


# writing for someone else is an identity question, whatever the threshold
@pytest.mark.parametrize("phrase", ["Ich schreibe für meinen Partner.", "Ich schreibe für meine Mutter.",
                                    "Ich schreibe für meine Mitbewohnerin."])
def test_writing_for_someone_else_forces_identity_review(client, phrase):
    case = _process(client, f"Wasser läuft aus der Spüle. {phrase} Musterstraße 12, 2. OG links. Viele Grüße, Max Mustermann")
    assert case["status"] == "NEEDS_REVIEW" and "identity" in case["match"]["failed_gates"]


def test_proxy_review_holds_with_lowered_threshold():
    rules = load_rules(None, {"match": {"threshold": 0.65}})
    r = match(ext(tenant_name=None, on_behalf_of="für meine Mutter"),
              InboundEmail(body="x", sender_email="max.mustermann@example.org"), JsonERP(), rules)
    assert r.selected_contract is None and "identity" in {g.value for g in r.failed_gates}


# ---- edge cases, part 17 --------------------------------------------------

# same message id with different content never returns the old (approved) decision
def test_same_message_id_different_content_is_conflict(client):
    first = {"subject": "Schaden", "message_id": "<abc@example.org>", "sender_email": "max.mustermann@example.org",
             "body": "Wasser läuft aus der Spüle. Musterstraße 12, 2. OG links. Viele Grüße, Max Mustermann"}
    case = client.post("/api/process", json={"email": first, "store": True}).json()
    client.post("/api/approve", json={"case_id": case["case_id"], "actor": "A", "action": "approve_assignment",
                                      "contract_id": "MV-10245"})
    changed = dict(first, body="Gasgeruch! Musterstraße 12, 3. OG rechts. Viele Grüße, Max Mustermann")
    r = client.post("/api/process", json={"email": changed, "store": True})
    assert r.status_code == 409 and "anderer Inhalt" in r.json()["detail"]
    same = client.post("/api/process", json={"email": first, "store": True})
    assert same.status_code == 200  # an identical replay is still fine


# an AI reader that invents a location the e-mail does not contain never picks a contract
class _InventingReader:
    name = "groq"

    def understand(self, email, rules):
        from intake.providers.offline import OfflineProvider
        u = OfflineProvider().understand(email, rules)
        ext = u.extraction.model_copy(update={"floor_raw": "3. OG", "side_raw": "rechts"})
        return u.model_copy(update={"extraction": ext, "provider": "groq"})


def test_ai_location_not_in_the_email_forces_review():
    from intake.context import Context
    from intake.pipeline import process
    from intake.scenarios import load_scenario
    sc = load_scenario(ROOT / "scenarios/S01_original.yaml")
    case = process(sc.email, Context.build(provider=_InventingReader()))
    assert case.status.value == "NEEDS_REVIEW" and case.match.selected_contract is None
    assert any("nicht im Text gefunden" in w for w in case.warnings)


def test_ai_location_quoted_from_the_email_is_accepted():
    from intake.context import Context
    from intake.pipeline import process
    from intake.scenarios import load_scenario

    class QuotingReader(_InventingReader):
        def understand(self, email, rules):
            from intake.providers.offline import OfflineProvider
            u = OfflineProvider().understand(email, rules)
            return u.model_copy(update={"provider": "groq"})

    sc = load_scenario(ROOT / "scenarios/S01_original.yaml")
    case = process(sc.email, Context.build(provider=QuotingReader()))
    assert case.status.value == "READY_FOR_APPROVAL" and case.match.selected_contract == "MV-10245"


def _read_with(update, body):
    from intake.context import Context
    from intake.pipeline import process

    class Reader:
        name = "groq"

        def understand(self, email, rules):
            from intake.providers.offline import OfflineProvider
            u = OfflineProvider().understand(email, rules)
            return u.model_copy(update={"extraction": u.extraction.model_copy(update=update), "provider": "groq"})

    return process(InboundEmail(subject="Wasser", body=body), Context.build(provider=Reader()))


def test_ai_values_must_match_whole_words():
    case = _read_with({"house_no": "12"}, "Wasser läuft aus der Spüle. Musterstraße 123, zweite Etage links. Max Mustermann")
    assert case.match.selected_contract is None and any("Hausnummer '12'" in w for w in case.warnings)
    case = _read_with({"floor_raw": "EG"}, "Wasser läuft aus der Spüle wegen eines Defekts. Musterstraße 12 rechts. Erika Musterfrau")
    assert case.status.value == "NEEDS_REVIEW" and any("Etage 'EG'" in w for w in case.warnings)


def test_invented_floor_keeps_the_building_for_emergencies():
    case = _read_with({"floor_raw": "drittes Obergeschoss"}, "Gasgeruch im Treppenhaus. Musterstraße 12, zweite Etage links. Max Mustermann")
    assert case.status.value == "NEEDS_REVIEW"
    assert case.match.object_id == "OBJ-MS12" and not case.match.building_uncertain
