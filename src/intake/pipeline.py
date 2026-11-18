"""Compose the steps. Used by the CLI, the API (/api/process), the scenario runner and the tests.

The n8n workflow calls the same steps one by one via /api/steps/{name}; a parity test
guarantees both paths give the same result.
"""

from __future__ import annotations

import hashlib

from .context import Context
from .models import AuditEvent, CaseRecord, InboundEmail
from .steps import STEPS

LAST_STEP = list(STEPS)[-1]


def new_case(email: InboundEmail, ctx: Context, scenario_id: str | None = None) -> CaseRecord:
    now = ctx.now()
    received = email.received_at or now
    seed = email.message_id or f"{email.subject}\n{email.body}\n{email.sender_email}"
    if scenario_id:  # demo scenarios share e-mails but differ in ERP/rule overrides
        seed = f"{scenario_id}\n{seed}"
    short = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6].upper()
    case = CaseRecord(case_id=f"SM-{received:%Y%m%d}-{short}", received_at=received, input=email)
    case.processing.rules_version = ctx.rules.version
    case.processing.scenario_id = scenario_id
    case.audit.append(AuditEvent(ts=now, actor="system", event="eingegangen",
                                 details={"subject": email.subject, "sender": email.sender_email}))
    return case


def run_step(name: str, case: CaseRecord, ctx: Context) -> CaseRecord:
    if name not in STEPS:
        raise KeyError(f"Unbekannter Schritt '{name}' (erlaubt: {', '.join(STEPS)})")
    case = STEPS[name](case, ctx)
    case.audit.append(AuditEvent(ts=ctx.now(), actor="system", event=f"schritt:{name}"))
    if name == LAST_STEP:
        case.processed_at = ctx.now()
    return case


def process(email: InboundEmail, ctx: Context, scenario_id: str | None = None) -> CaseRecord:
    case = new_case(email, ctx, scenario_id)
    for name in STEPS:
        case = run_step(name, case, ctx)
    return case


def apply_human_assignment(case: CaseRecord, contract_id: str, ctx: Context) -> CaseRecord:
    """After a human approved a contract: keep the system proposal untouched, record the
    approved contract and regenerate the contract-dependent outputs (history, task)."""
    from .models import Status

    view = case.model_copy(deep=True)
    view.match.selected_contract = contract_id
    view.match.winner = contract_id
    view.status = Status.READY_FOR_APPROVAL
    contract = ctx.erp.contract(contract_id)
    registered = (contract.contact.email or "").strip().lower() if contract else ""
    sender = (case.input.sender_email or "").strip().lower()
    view.match.unknown_sender = bool(sender) and sender != registered
    view = STEPS["prior_cases"](view, ctx)
    view = STEPS["task"](view, ctx)
    out = case.model_copy(deep=True)
    out.match.approved_contract = contract_id
    out.prior_cases = view.prior_cases
    out.internal_task = view.internal_task
    out.staff_options = view.staff_options  # contact options belong to the approved contract
    return out
