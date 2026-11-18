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


def new_case(email: InboundEmail, ctx: Context) -> CaseRecord:
    now = ctx.now()
    received = email.received_at or now
    seed = email.message_id or f"{email.subject}\n{email.body}\n{email.sender_email}"
    short = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6].upper()
    case = CaseRecord(case_id=f"SM-{received:%Y%m%d}-{short}", received_at=received, input=email)
    case.processing.rules_version = ctx.rules.version
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


def process(email: InboundEmail, ctx: Context) -> CaseRecord:
    case = new_case(email, ctx)
    for name in STEPS:
        case = run_step(name, case, ctx)
    return case
