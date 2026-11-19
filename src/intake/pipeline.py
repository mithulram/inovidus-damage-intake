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
    seed = email.message_id or (f"{email.subject}\n{email.body}\n{email.sender_email}"
                                + (f"\n{email.sender_display_name}" if email.sender_display_name else ""))
    if scenario_id:  # demo scenarios share e-mails but differ in ERP/rule overrides
        seed = f"{scenario_id}\n{seed}"
    short = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6].upper()
    case = CaseRecord(case_id=f"SM-{received:%Y%m%d}-{short}", received_at=received, input=email)
    case.processing.rules_version = ctx.rules.version
    case.processing.erp_version = getattr(ctx.erp, "version", None)
    case.processing.scenario_id = scenario_id
    case.audit.append(AuditEvent(ts=now, actor="system", event="eingegangen",
                                 details={"subject": email.subject, "sender": email.sender_email}))
    return case


class VersionMismatch(ValueError):
    """Rules or ERP data changed while the case was being processed – restart the chain."""


def check_versions(case: CaseRecord, ctx: Context) -> None:
    erp_version = getattr(ctx.erp, "version", None)
    if not case.processing.rules_version or not case.processing.erp_version:
        # never trust (or silently stamp) a record without its basis: it must be processed again
        raise VersionMismatch("Der Vorgang nennt keinen Stand der Regeln und ERP-Daten – bitte neu verarbeiten.")
    if case.processing.rules_version != ctx.rules.version:
        raise VersionMismatch("Die Regeln wurden während der Verarbeitung geändert – bitte neu verarbeiten.")
    if case.processing.erp_version != erp_version:
        raise VersionMismatch("Die ERP-Daten wurden seit der Verarbeitung geändert – bitte neu verarbeiten.")


def last_step(case: CaseRecord) -> str | None:
    return next((e.event.split(":", 1)[1] for e in reversed(case.audit) if e.event.startswith("schritt:")), None)


def is_complete(case: CaseRecord) -> bool:
    """Every step ran, in order, to the end – only such a record may enter the inbox or be acted on."""
    return (case.processed_at is not None and last_step(case) == LAST_STEP
            and None not in (case.understanding, case.match, case.status, case.urgency, case.reply_draft,
                             case.internal_task))


def run_step(name: str, case: CaseRecord, ctx: Context) -> CaseRecord:
    if name not in STEPS:
        raise KeyError(f"Unbekannter Schritt '{name}' (erlaubt: {', '.join(STEPS)})")
    check_versions(case, ctx)
    order = list(STEPS)
    expected = order[order.index(last_step(case)) + 1] if last_step(case) in order[:-1] else (
        order[0] if last_step(case) is None else None)
    if name != expected:
        # steps run once, in order; re-running an earlier step would leave later results inconsistent
        raise ValueError(f"Schritt '{name}' passt nicht – als Nächstes ist "
                         f"{repr(expected) if expected else 'kein Schritt'} dran. Bitte neu verarbeiten.")
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
    # contact state (warning, options, action checks) follows the approved contract consistently
    out.match.unknown_sender = view.match.unknown_sender
    out.staff_options = view.staff_options
    warning = "Nicht von der registrierten E-Mail-Adresse"
    out.warnings = [w for w in out.warnings if w != warning] + ([warning] if out.match.unknown_sender else [])
    return out
