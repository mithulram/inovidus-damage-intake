"""One local process serves the review UI and the shared pipeline API."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from .. import actions, pipeline
from ..actions import Approval, AuditLog
from ..context import Context
from ..models import AuditEvent, CaseRecord, InboundEmail, ReplyDraft
from ..providers import get_provider
from ..rules import DEFAULT_RULES_PATH, load_rules
from ..scenarios import load_scenarios
from ..steps import STEPS
from ..steps.draft import render_reply
from ..store import CaseStore


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcessRequest(RequestModel):
    email: InboundEmail
    provider: str | None = None
    scenario_id: str | None = None
    store: bool = False


class StepRequest(RequestModel):
    case: CaseRecord | None = None
    email: InboundEmail | None = None
    provider: str | None = None
    scenario_id: str | None = None


class ApproveRequest(Approval):
    option: str | None = None


def _context(provider: str | None = None, scenario_id: str | None = None) -> Context:
    scenario = None
    if scenario_id is not None:
        scenario = next((s for s in load_scenarios() if s.id == scenario_id), None)
        if scenario is None:
            raise HTTPException(404, "Unbekanntes Szenario")
    try:
        return Context.build(provider=get_provider(provider),
                             rule_overrides=scenario.rule_overrides if scenario else None,
                             data_overrides=scenario.data_overrides if scenario else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


def create_app(*, store: CaseStore | None = None, audit: AuditLog | None = None,
               static_dir: Path | str | None = None) -> FastAPI:
    app = FastAPI(title="Schadenmeldungen – Prüfliste")
    app.state.store = store if store is not None else CaseStore()
    app.state.audit = audit if audit is not None else AuditLog()
    static = Path(static_dir) if static_dir is not None else Path(__file__).parent / "static"

    def get_case(case_id: str) -> CaseRecord:
        try:
            case = app.state.store.get(case_id)
        except ValueError:
            raise HTTPException(422, "Ungültige Vorgangs-ID") from None
        if case is None:
            raise HTTPException(404, "Vorgang nicht gefunden")
        return case

    def store_case(case: CaseRecord) -> CaseRecord:
        try:
            existing = app.state.store.get(case.case_id)
        except ValueError:
            raise HTTPException(422, "Ungültige Vorgangs-ID") from None
        if existing is not None:
            return existing
        case = case.model_copy(deep=True)
        event = AuditEvent(ts=datetime.now(timezone.utc), actor="system", event="in Prüfliste übernommen",
                           details={"case_id": case.case_id})
        case.audit.append(event)
        app.state.store.save(case)
        app.state.audit.append(event)
        return case

    @app.get("/api/health")
    def health():
        return {"status": "ok", "provider_default": (os.getenv("LLM_PROVIDER") or "offline").strip().lower(),
                "rules_version": load_rules().version}

    @app.get("/api/scenarios")
    def scenarios():
        return [{"id": s.id, "title": s.title, "description": s.description, "email": s.email,
                 "expected": s.expected, "has_overrides": bool(s.rule_overrides or s.data_overrides)}
                for s in load_scenarios()]

    @app.get("/api/rules")
    def rules():
        raw = DEFAULT_RULES_PATH.read_text(encoding="utf-8")
        return {"version": load_rules().version, "yaml": raw, "parsed": yaml.safe_load(raw)}

    @app.post("/api/process", response_model=CaseRecord)
    def process(body: ProcessRequest):
        case = pipeline.process(body.email, _context(body.provider, body.scenario_id))
        return store_case(case) if body.store else case

    @app.post("/api/steps/{name}", response_model=CaseRecord)
    def step(name: str, body: StepRequest):
        if name not in STEPS:
            raise HTTPException(404, f"Unbekannter Schritt '{name}' (erlaubt: {', '.join(STEPS)})")
        ctx = _context(body.provider, body.scenario_id)
        case = body.case
        if case is None:
            if name != "understand" or body.email is None:
                raise HTTPException(422, "Vorgang fehlt; 'understand' braucht mindestens eine E-Mail")
            case = pipeline.new_case(body.email, ctx)
        try:
            return pipeline.run_step(name, case, ctx)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/cases", response_model=CaseRecord)
    def add_case(case: CaseRecord):
        return store_case(case)

    @app.get("/api/cases")
    def cases():
        return [{"case_id": c.case_id, "received_at": c.received_at, "subject": c.input.subject,
                 "status": c.status, "urgency": c.urgency.level if c.urgency else None,
                 "winner": c.match.winner if c.match else None,
                 "selected_contract": c.match.selected_contract if c.match else None,
                 "failed_gates": c.match.failed_gates if c.match else []} for c in app.state.store.list()]

    @app.get("/api/cases/{case_id}", response_model=CaseRecord)
    def case_by_id(case_id: str):
        return get_case(case_id)

    @app.get("/api/cases/{case_id}/reply", response_model=ReplyDraft)
    def reply(case_id: str, variant: str | None = None):
        try:
            return render_reply(get_case(case_id), _context(), variant=variant)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/approve", response_model=CaseRecord)
    def approve(body: ApproveRequest):
        approval = Approval.model_validate(body.model_dump(exclude={"option"}))
        if body.action == "choose_staff_option" and body.option is not None:
            approval.reason = body.option
        try:
            case = actions.execute(get_case(body.case_id), approval, app.state.audit)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from None
        return app.state.store.save(case)

    @app.get("/api/audit")
    def audit_lines():
        return app.state.audit.read()[-200:]

    @app.get("/")
    def index():
        if (static / "index.html").is_file():
            return FileResponse(static / "index.html")
        return {"hint": "Die Oberfläche ist noch nicht installiert. API: /docs"}

    if static.is_dir():
        app.mount("/static", StaticFiles(directory=static), name="static")
    return app


app = create_app()


def run() -> None:
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("INTAKE_PORT", "8000")))
