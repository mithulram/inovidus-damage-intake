"""Shared data contract for the whole pipeline.

Every step reads and writes a :class:`CaseRecord`. JSON keys are English (API/ERP
convention, more reliable LLM structured output); human-readable reasons and labels
are German, because they are shown to the Sachbearbeiter.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MessageType(str, Enum):
    SCHADENMELDUNG = "SCHADENMELDUNG"
    ANFRAGE_MIETE = "ANFRAGE_MIETE"
    SONSTIGES = "SONSTIGES"


class Urgency(str, Enum):
    NOTFALL = "NOTFALL"
    DRINGEND = "DRINGEND"
    NORMAL = "NORMAL"

    @property
    def rank(self) -> int:
        return {"NORMAL": 0, "DRINGEND": 1, "NOTFALL": 2}[self.value]

    @classmethod
    def max(cls, *levels: "Urgency | None") -> "Urgency":
        present = [lvl for lvl in levels if lvl is not None]
        return max(present, key=lambda lvl: lvl.rank) if present else cls.NORMAL


class Status(str, Enum):
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class Gate(str, Enum):
    """Why a case did not pass automatically. Scenario tests assert the exact set."""

    THRESHOLD = "threshold"
    MARGIN = "margin"
    VETO_ADDRESS = "veto_address"
    VETO_UNIT = "veto_unit"
    ELIGIBILITY = "eligibility"
    IDENTITY = "identity"
    FLOOR_MISSING = "floor_missing"
    FLOOR_AMBIGUOUS = "floor_ambiguous"
    OUT_OF_SCOPE = "out_of_scope"
    NO_CANDIDATE = "no_candidate"
    UNIT_AMBIGUOUS = "unit_ambiguous"


FloorStatus = Literal["ok", "missing", "unclear", "english_ordinal"]
Side = Literal["L", "R", "M"]
SignalName = Literal["name", "address", "floor", "side", "contact"]
SignalResult = Literal["match", "partial", "mismatch", "missing"]


# ---------------------------------------------------------------------------
# Step 1 – input
# ---------------------------------------------------------------------------


class InboundEmail(Strict):
    message_id: str | None = None
    subject: str = ""
    body: str
    sender_email: str | None = None
    sender_display_name: str | None = None
    received_at: datetime | None = None
    attachments: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Steps 2+3 – understanding (provider output: LLM or offline rules)
# ---------------------------------------------------------------------------


class Classification(Strict):
    type: MessageType
    category: str | None = Field(None, description="Schadenart, z. B. 'Wasserschaden'")
    trade: str | None = Field(None, description="Gewerk, z. B. 'Sanitär'")
    confidence: float = Field(ge=0, le=1)
    reason: str


class Extraction(Strict):
    """Raw facts as written in the email. Normalisation happens deterministically later."""

    tenant_name: str | None = Field(None, description="Vertragsinhaber, auf den sich die Mail bezieht")
    sender_name: str | None = Field(None, description="Wer die Mail geschrieben/unterschrieben hat")
    street_raw: str | None = None
    house_no: str | None = None
    floor_raw: str | None = None
    side_raw: str | None = None
    room: str | None = None
    damage_description: str | None = None
    since: str | None = None
    photos_mentioned: bool = False
    phone: str | None = None
    language: Literal["de", "en"] = "de"
    location_alternatives: list[str] = Field(
        default_factory=list,
        description="Weitere oder unsichere Ortsangaben (z. B. '3. OG rechts', 'bin unsicher'); nicht leer = Prüfung")


class Understanding(Strict):
    classification: Classification
    extraction: Extraction
    urgency_hint: Urgency | None = Field(None, description="Einschätzung des Modells; Regeln setzen die Untergrenze")
    urgency_hint_reason: str | None = None
    provider: str
    model: str | None = None
    fallback_used: bool = False
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 4 – ERP matching (deterministic)
# ---------------------------------------------------------------------------


class NormalizedLocation(Strict):
    street: str | None = None
    house_no: str | None = None
    floor: int | None = None
    floor_status: FloorStatus = "missing"
    floor_note: str | None = None
    side: Side | None = None


class Signal(Strict):
    name: SignalName
    result: SignalResult
    weight: float
    points: float
    email_value: str | None = None
    erp_value: str | None = None
    reason: str


class Candidate(Strict):
    contract_id: str
    tenant_name: str
    unit_label: str
    object_id: str
    unit_id: str
    active: bool
    score: float
    signals: list[Signal]
    vetoes: list[str] = Field(default_factory=list, description="Deutsche Begründungen")
    veto_gates: list[Gate] = Field(default_factory=list)


class Flag(Strict):
    gate: Gate
    message: str


class MatchResult(Strict):
    location: NormalizedLocation
    candidates: list[Candidate]
    winner: str | None = Field(None, description="Bester Kandidat nach Stufe A (auch wenn Prüfung nötig)")
    selected_contract: str | None = Field(None, description="Nur gesetzt, wenn alle Prüfungen bestanden sind")
    score: float | None = None
    margin: float | None = None
    failed_gates: list[Gate] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    object_id: str | None = Field(None, description="Gebäude, wenn die Adresse sicher ist")
    unknown_sender: bool = False
    building_uncertain: bool = Field(False, description="E-Mail nennt mehrere/unsichere Gebäude – keine Gebäudeaktion")
    approved_contract: str | None = Field(None, description="Von einem Menschen freigegebener Vertrag (überschreibt nie den Vorschlag)")
    reason: str


# ---------------------------------------------------------------------------
# Step 5 – prior cases
# ---------------------------------------------------------------------------


class PriorCase(Strict):
    case_id: str
    contract_id: str
    title: str
    category: str
    room: str | None
    state: Literal["open", "closed"]
    closed_at: str | None = None
    contractor: str | None = None
    related: bool
    possible_duplicate: bool = False
    reason: str


# ---------------------------------------------------------------------------
# Step 6 – urgency
# ---------------------------------------------------------------------------


class UrgencyResult(Strict):
    level: Urgency
    rule_level: Urgency
    llm_level: Urgency | None = None
    triggers: list[str]
    tenant_says_urgent: bool = False
    response_target: str
    due_hours: int
    safety_instructions: list[str] = Field(default_factory=list)
    reason: str


# ---------------------------------------------------------------------------
# Steps 8+9 – reply draft, internal task, staff options
# ---------------------------------------------------------------------------


class ReplyDraft(Strict):
    language: Literal["de", "en"]
    variant: str
    to: str | None
    subject: str
    body: str
    auto_send: Literal[False] = False


class InternalTask(Strict):
    title: str
    scope: Literal["contract", "object", "routing", "clarification"]
    assignee_role: str
    priority: Urgency
    due_hours: int
    contract_id: str | None = None
    object_id: str | None = None
    checklist: list[str]
    related_cases: list[str] = Field(default_factory=list)
    requires_approval: bool = True


class StaffOption(Strict):
    code: Literal["reply_anyway", "ask_registered_email", "call_tenant"]
    label: str
    available: bool
    detail: str | None = None


class AuditEvent(Strict):
    ts: datetime
    actor: str
    event: str
    details: dict[str, Any] = Field(default_factory=dict)


class Processing(Strict):
    provider: str | None = None
    model: str | None = None
    rules_version: str | None = None
    fallback_used: bool = False
    scenario_id: str | None = Field(None, description="Nur Demo: Testfall, dessen Daten-/Regeländerungen galten")
    generation: int | None = Field(None, description="Server-Zeitstempel (ns) beim START der Verarbeitung – neuere Läufe gewinnen")


# ---------------------------------------------------------------------------
# Step 7 – the structured record
# ---------------------------------------------------------------------------


class CaseRecord(Strict):
    case_id: str
    received_at: datetime
    processed_at: datetime | None = None
    processing: Processing = Field(default_factory=Processing)
    input: InboundEmail
    understanding: Understanding | None = None
    match: MatchResult | None = None
    prior_cases: list[PriorCase] = Field(default_factory=list)
    urgency: UrgencyResult | None = None
    status: Status | None = None
    reply_draft: ReplyDraft | None = None
    internal_task: InternalTask | None = None
    staff_options: list[StaffOption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit: list[AuditEvent] = Field(default_factory=list)
