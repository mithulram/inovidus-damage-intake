"""The single, simulated action boundary. Every success is audited; nothing sends mail.

For ``choose_staff_option``, Approval.reason carries the available option's code.
Reply approval is represented by an audit event with approved_for_copy=True because
ReplyDraft deliberately has no mutable approval or delivery field.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import AuditEvent, CaseRecord, Status
from .rules import ROOT

SIMULATED = "im Prototyp simuliert – kein echter ERP-Schreibzugriff"


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    case_id: str = Field(min_length=1)
    actor: str = Field(min_length=1)
    action: Literal["approve_assignment", "order_contractor", "object_action", "approve_reply", "choose_staff_option"]
    contract_id: str | None = None
    reason: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLog:
    """Append-only JSONL action log; tests inject a temporary path."""

    def __init__(self, path: Path | str = ROOT / "var" / "audit.jsonl"):
        self.path = Path(path)

    def append(self, event: AuditEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(event.model_dump_json() + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]


def execute(case: CaseRecord, approval: Approval, audit: AuditLog) -> CaseRecord:
    if not isinstance(approval, Approval) or approval.case_id != case.case_id:
        raise PermissionError("Freigabe fehlt oder gehört zu einem anderen Vorgang")
    if case.status is None or case.match is None:
        raise PermissionError("Nur verarbeitete Vorgänge dürfen freigegeben werden")
    action = approval.action
    details = {"case_id": case.case_id, "contract_id": approval.contract_id,
               "reason": approval.reason, "simulated": True, "effect": SIMULATED}
    if action in {"approve_assignment", "order_contractor"}:
        if case.status == Status.OUT_OF_SCOPE:
            raise PermissionError("Keine Vertragsaktion bei fachfremder Nachricht")
        if approval.contract_id not in {c.contract_id for c in case.match.candidates}:
            raise PermissionError("Vertrag ist kein Kandidat dieses Vorgangs")
        if ((case.status == Status.NEEDS_REVIEW or approval.contract_id != case.match.selected_contract)
                and not approval.reason):
            raise PermissionError("Manuelle Zuordnung braucht eine Begründung")
        if action == "order_contractor" and not any(
            event.event == "approve_assignment"
            and event.details.get("case_id") == case.case_id
            and event.details.get("contract_id") == approval.contract_id
            for event in case.audit
        ):
            raise PermissionError("Handwerkerauftrag braucht eine vorherige Zuordnungsfreigabe für diesen Vertrag")
    elif action == "object_action":
        if case.status == Status.OUT_OF_SCOPE or not case.match.object_id or approval.contract_id is not None:
            raise PermissionError("Gebäudeaktion braucht eine sichere Objektzuordnung, ohne Vertragsbezug")
        details["object_id"] = case.match.object_id
    elif action == "approve_reply":
        if case.reply_draft is None:
            raise PermissionError("Kein Antwortentwurf zur Freigabe vorhanden")
        details["approved_for_copy"] = True
        details["reply_sha256"] = hashlib.sha256(case.reply_draft.model_dump_json().encode()).hexdigest()
    elif action == "choose_staff_option":
        option = next((o for o in case.staff_options if o.code == approval.reason and o.available), None)
        if not case.match.unknown_sender or option is None:
            raise PermissionError("Diese Mitarbeiteroption ist nicht verfügbar")
        details["staff_option"] = option.code
        details["detail"] = option.detail
    event = AuditEvent(ts=approval.ts, actor=approval.actor, event=action, details=details)
    result = case.model_copy(deep=True)
    # Persist before returning the changed case; a failed write must not look successful.
    audit.append(event)
    result.audit.append(event)
    return result
