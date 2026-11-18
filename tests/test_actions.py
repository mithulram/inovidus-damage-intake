"""WO1: the approval boundary, isolated JSONL audit and no-mail guarantee."""

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from intake.actions import Approval, AuditLog, execute
from intake.models import Status
from intake.providers.offline import OfflineProvider
from intake.scenarios import load_scenario, run_scenario


ROOT = Path(__file__).resolve().parents[1]
STAMP = datetime(2026, 11, 18, 10, tzinfo=timezone.utc)
ACTIONS = ["approve_assignment", "order_contractor", "object_action", "approve_reply", "choose_staff_option"]


@pytest.fixture
def cases():
    return {name: run_scenario(load_scenario(ROOT / "scenarios" / filename), provider=OfflineProvider())[0]
            for name, filename in {
                "ready": "S01_original.yaml", "review": "S02_no_unit.yaml",
                "outside": "S06_rent_question.yaml", "object": "S05b_gas.yaml",
                "unknown": "S04c_unknown_sender.yaml",
            }.items()}


@pytest.fixture
def audit(tmp_path):
    return AuditLog(tmp_path / "injected" / "actions.jsonl")


def approval(case, action="approve_assignment", **changes):
    fields = dict(case_id=case.case_id, actor="Sachbearbeitung Test", action=action,
                  contract_id=case.match.selected_contract or case.match.winner, ts=STAMP)
    fields.update(changes)
    return Approval(**fields)


def assert_refused_without_effects(case, request, audit):
    before = case.model_dump(mode="json")
    existed = audit.path.exists()
    contents = audit.path.read_bytes() if existed else b""
    with pytest.raises(PermissionError):
        execute(case, request, audit)
    assert case.model_dump(mode="json") == before
    assert audit.path.exists() is existed
    assert (audit.path.read_bytes() if existed else b"") == contents


@pytest.mark.parametrize("action", ACTIONS)
def test_wrong_case_id_is_refused_for_every_action(cases, audit, action):
    case = cases["unknown"]
    assert_refused_without_effects(case, approval(case, action, case_id="OTHER-CASE", reason="reply_anyway"), audit)


@pytest.mark.parametrize("unvalidated", [None, {"actor": "unvalidated"}])
def test_missing_or_unvalidated_approval_is_refused(cases, audit, unvalidated):
    assert_refused_without_effects(cases["ready"], unvalidated, audit)


@pytest.mark.parametrize("action", ["approve_assignment", "order_contractor"])
def test_out_of_scope_contract_actions_are_refused(cases, audit, action):
    case = cases["outside"]
    assert case.status == Status.OUT_OF_SCOPE
    assert_refused_without_effects(case, approval(case, action, reason="Manuell geprüft"), audit)


@pytest.mark.parametrize("action", ["approve_assignment", "order_contractor"])
@pytest.mark.parametrize("contract_id", [None, "MV-NOT-A-CANDIDATE"])
def test_contract_must_be_a_candidate(cases, audit, action, contract_id):
    case = cases["ready"]
    assert_refused_without_effects(case, approval(case, action, contract_id=contract_id, reason="Manuell geprüft"), audit)


def test_order_requires_prior_assignment_approval(cases, audit):
    case = cases["ready"]
    assert_refused_without_effects(case, approval(case, "order_contractor"), audit)


@pytest.mark.parametrize("mismatch", ["case_id", "contract_id"])
def test_other_case_or_contract_assignment_does_not_authorize_order(cases, audit, mismatch):
    case = cases["ready"]
    result = execute(case, approval(case), audit)
    result.audit[-1].details[mismatch] = "OTHER"
    assert_refused_without_effects(result, approval(result, "order_contractor"), audit)


@pytest.mark.parametrize("action", ["approve_assignment", "order_contractor"])
@pytest.mark.parametrize("reason", [None, "", "   "])
def test_review_requires_nonempty_reason_even_after_assignment_approval(cases, audit, action, reason):
    case = cases["review"]
    if action == "order_contractor":
        case = execute(case, approval(case, reason="Einheit telefonisch bestätigt"), audit)
    assert_refused_without_effects(case, approval(case, action, reason=reason), audit)


def test_overriding_selected_contract_requires_reason(cases, audit):
    case = cases["ready"]
    alternative = next(c.contract_id for c in case.match.candidates if c.contract_id != case.match.selected_contract)
    assert_refused_without_effects(case, approval(case, contract_id=alternative), audit)
    result = execute(case, approval(case, contract_id=alternative, reason="Andere Einheit nach Rückfrage bestätigt"), audit)
    assert result.audit[-1].details["contract_id"] == alternative
    assert result.audit[-1].details["reason"] == "Andere Einheit nach Rückfrage bestätigt"


@pytest.mark.parametrize("name", ["ready", "review"])
def test_assignment_then_order_accepted_and_each_action_appends_jsonl(cases, audit, name):
    case = cases[name]
    original = case.model_dump(mode="json")
    reason = "Einheit telefonisch bestätigt" if name == "review" else None
    assigned = execute(case, approval(case, reason=reason), audit)
    first_line = audit.path.read_bytes()
    ordered = execute(assigned, approval(assigned, "order_contractor", reason=reason), audit)
    assert case.model_dump(mode="json") == original
    assert len(assigned.audit) == len(case.audit) + 1
    assert len(ordered.audit) == len(case.audit) + 2
    raw = audit.path.read_bytes()
    assert raw.startswith(first_line) and raw.endswith(b"\n")
    assert len(raw.splitlines()) == 2
    records = [json.loads(line) for line in raw.splitlines()]
    assert [r["event"] for r in records] == ["approve_assignment", "order_contractor"]
    assert audit.read() == records
    assert records == [event.model_dump(mode="json") for event in ordered.audit[-2:]]
    for record in records:
        assert record["actor"] == "Sachbearbeitung Test"
        assert datetime.fromisoformat(record["ts"]) == STAMP
        assert record["details"]["case_id"] == case.case_id
        assert record["details"]["contract_id"] == (case.match.selected_contract or case.match.winner)
        assert record["details"]["reason"] == reason
        assert record["details"]["simulated"] is True
        assert record["details"]["effect"] == "im Prototyp simuliert – kein echter ERP-Schreibzugriff"


def test_object_action_accepted_for_review_with_building_without_contract(cases, audit):
    case = cases["object"]
    assert case.status == Status.NEEDS_REVIEW
    assert case.internal_task.scope == "object"
    result = execute(case, approval(case, "object_action", contract_id=None), audit)
    event = result.audit[-1]
    assert event.details["object_id"] == "OBJ-MS12"
    assert event.details["contract_id"] is None
    assert audit.read() == [event.model_dump(mode="json")]


@pytest.mark.parametrize("invalid", ["outside", "no_building", "contract_reference"])
def test_object_action_refuses_invalid_scope(cases, audit, invalid):
    case = cases["outside"] if invalid == "outside" else cases["object"]
    if invalid == "no_building":
        case.match.object_id = None
    request = approval(case, "object_action", contract_id="MV-10245" if invalid == "contract_reference" else None)
    assert_refused_without_effects(case, request, audit)


def test_reply_approval_is_audited_for_copying_and_draft_is_never_sent(cases, audit):
    case = cases["ready"]
    before = case.reply_draft.model_dump()
    result = execute(case, approval(case, "approve_reply", contract_id=None), audit)
    assert result.reply_draft.model_dump() == before
    assert result.reply_draft.auto_send is False
    assert result.audit[-1].details["approved_for_copy"] is True
    assert audit.read() == [result.audit[-1].model_dump(mode="json")]
    case.reply_draft = None
    assert_refused_without_effects(case, approval(case, "approve_reply", contract_id=None), audit)


@pytest.mark.parametrize("code", ["reply_anyway", "ask_registered_email", "call_tenant"])
def test_available_staff_option_is_accepted_and_audited(cases, audit, code):
    case = cases["unknown"]
    result = execute(case, approval(case, "choose_staff_option", reason=code), audit)
    assert result.audit[-1].details["staff_option"] == code
    assert audit.read() == [result.audit[-1].model_dump(mode="json")]


@pytest.mark.parametrize("invalid", ["unavailable", "unknown_option", "registered_sender"])
def test_staff_option_must_be_available_for_unknown_sender(cases, audit, invalid):
    case = cases["ready"] if invalid == "registered_sender" else cases["unknown"]
    code = "reply_anyway"
    if invalid == "unavailable":
        next(o for o in case.staff_options if o.code == code).available = False
    if invalid == "unknown_option":
        code = "invented_option"
    assert_refused_without_effects(case, approval(case, "choose_staff_option", reason=code), audit)


def test_failed_audit_write_does_not_mutate_case(cases, audit, monkeypatch):
    case = cases["ready"]
    before = case.model_dump(mode="json")

    def fail_write(event):
        raise OSError("Injected disk failure")

    monkeypatch.setattr(audit, "append", fail_write)
    with pytest.raises(OSError, match="Injected disk failure"):
        execute(case, approval(case), audit)
    assert case.model_dump(mode="json") == before
    assert not audit.path.exists()


def test_send_is_not_an_approval_action(cases):
    with pytest.raises(ValidationError):
        approval(cases["ready"], "send")


def test_source_has_no_smtp_or_mime_imports_or_send_functions():
    violations = []
    sources = sorted((ROOT / "src").rglob("*.py"))
    assert sources
    for source in sources:
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or "", *[f"{node.module or ''}.{alias.name}" for alias in node.names]]
            if any(module == "smtplib" or module.startswith("smtplib.")
                   or module == "email.mime" or module.startswith("email.mime.") for module in modules):
                violations.append(f"{source.relative_to(ROOT)}:{node.lineno}: mail import")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name.lower().lstrip("_")
                if name.startswith("send") or "_send" in name:
                    violations.append(f"{source.relative_to(ROOT)}:{node.lineno}: send function {node.name}")
    assert violations == [], "\n".join(violations)
