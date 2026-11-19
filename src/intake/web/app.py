"""One local process serves the review UI and the shared pipeline API."""

from __future__ import annotations

import base64
import hmac
import os
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException
from fastapi import Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict

from .. import actions, pipeline
from ..actions import Approval, AuditLog
from ..context import Context
from ..env import load_dotenv
from ..i18n import translate_many
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


class TranslateRequest(RequestModel):
    texts: list[str]


class StepRequest(RequestModel):
    case: CaseRecord | None = None
    email: InboundEmail | None = None
    provider: str | None = None
    scenario_id: str | None = None


SUPERSEDED = "neu verarbeitet (Regeln geändert) – frühere Freigaben gelten nicht mehr"
ACTION_EVENTS = {"approve_assignment", "order_contractor", "object_action", "approve_reply", "choose_staff_option"}


class ApproveRequest(Approval):
    option: str | None = None
    scenario_id: str | None = None  # ignored: the stored case remembers its own processing context
    revision: int | None = None     # number of audit events the client saw; mismatch = stale view


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
    load_dotenv()
    app = FastAPI(title="Schadenmeldungen – Prüfliste")

    # Hosted demo protection (Render): a shared password for people (HTTP Basic, any user name)
    # and a service token for n8n. Unset locally = open, as before. /api/health stays open for health checks.
    password = os.getenv("INTAKE_ACCESS_PASSWORD") or ""
    service_token = os.getenv("INTAKE_SERVICE_TOKEN") or ""

    @app.middleware("http")
    async def access_guard(request: Request, call_next):
        if (not password and not service_token) or request.url.path == "/api/health":
            return await call_next(request)
        token = request.headers.get("x-intake-token", "")
        if service_token and token and hmac.compare_digest(token, service_token):
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        if password and auth.lower().startswith("basic "):
            try:
                given = base64.b64decode(auth[6:]).decode("utf-8").split(":", 1)[1]
            except Exception:  # noqa: BLE001 – malformed header = not authenticated
                given = ""
            if hmac.compare_digest(given, password):
                return await call_next(request)
        return PlainTextResponse("Anmeldung erforderlich / Login required", status_code=401,
                                 headers={"WWW-Authenticate": 'Basic realm="Schadenmeldungen-Demo", charset="UTF-8"'})
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

    lock = threading.RLock()  # serialises every read-modify-write of a stored case

    def store_case(case: CaseRecord) -> CaseRecord:
        with lock:
            return _store_case(case)

    def _store_case(case: CaseRecord) -> CaseRecord:
        # Approval history is server-owned: no action event in a submitted case is ever trusted,
        # whoever it claims as actor. Only pipeline bookkeeping (eingegangen, schritt:*) is kept.
        case = case.model_copy(deep=True)
        case.audit = [e for e in case.audit if e.actor == "system" and e.event not in ACTION_EVENTS]
        if case.match is not None:
            case.match.approved_contract = None
        try:
            existing = app.state.store.get(case.case_id)
        except ValueError:
            raise HTTPException(422, "Ungültige Vorgangs-ID") from None
        label = "in Prüfliste übernommen"
        if existing is not None:
            old_gen, new_gen = existing.processing.generation, case.processing.generation
            if old_gen is not None:
                newer = new_gen is not None and new_gen > old_gen
            else:
                newer = bool(case.processed_at and (existing.processed_at is None or case.processed_at > existing.processed_at))
            if not newer:
                return existing  # a run that STARTED earlier never overwrites a newer one, however late it finishes
            volatile = {"audit": True, "processed_at": True, "received_at": True, "processing": {"generation"}}
            if existing.model_dump(exclude=volatile) == case.model_dump(exclude=volatile):
                existing.processing.generation = new_gen  # same result: keep it, but advance the watermark
                return app.state.store.save(existing)
            human = any(e.actor != "system" for e in existing.audit)
            if human and case.processing.rules_version == existing.processing.rules_version:
                return existing  # a human already acted and the rules did not change: frozen
            label = (SUPERSEDED if human else "neu verarbeitet (Regeln oder Leser geändert)")
        case = case.model_copy(deep=True)
        event = AuditEvent(ts=datetime.now(timezone.utc), actor="system", event=label,
                           details={"case_id": case.case_id})
        if existing is not None:
            case.audit = [*existing.audit, event]
        else:
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
                 "expected": s.expected, "rule_overrides": s.rule_overrides or {},
                 "has_overrides": bool(s.rule_overrides or s.data_overrides)}
                for s in load_scenarios()]

    @app.get("/api/rules")
    def rules():
        raw = DEFAULT_RULES_PATH.read_text(encoding="utf-8")
        return {"version": load_rules().version, "yaml": raw, "parsed": yaml.safe_load(raw)}

    @app.post("/api/process", response_model=CaseRecord)
    def process(body: ProcessRequest):
        generation = time.time_ns()  # taken BEFORE the (possibly slow) reader runs
        case = pipeline.process(body.email, _context(body.provider, body.scenario_id), body.scenario_id)
        case.processing.generation = generation
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
            case = pipeline.new_case(body.email, ctx, body.scenario_id)
            case.processing.generation = time.time_ns()
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
                 "sender": c.input.sender_email, "status": c.status,
                 "urgency": c.urgency.level if c.urgency else None,
                 "winner": c.match.winner if c.match else None,
                 "selected_contract": c.match.selected_contract if c.match else None,
                 "failed_gates": c.match.failed_gates if c.match else []} for c in app.state.store.list()]

    @app.get("/api/cases/{case_id}", response_model=CaseRecord | None)
    def case_by_id(case_id: str, allow_missing: bool = False):
        if allow_missing:
            try:
                return app.state.store.get(case_id)
            except ValueError:
                raise HTTPException(422, "Ungültige Vorgangs-ID") from None
        return get_case(case_id)

    @app.get("/api/cases/{case_id}/reply", response_model=ReplyDraft)
    def reply(case_id: str, variant: str | None = None):
        try:
            return render_reply(get_case(case_id), _context(), variant=variant)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/approve", response_model=CaseRecord)
    def approve(body: ApproveRequest):
        approval = Approval.model_validate(body.model_dump(exclude={"option", "scenario_id", "revision"}))
        if body.action == "choose_staff_option" and body.option is not None:
            approval.reason = body.option
        with lock:
            case = get_case(body.case_id)
            if body.revision is not None and body.revision != len(case.audit):
                raise HTTPException(409, "Der Vorgang wurde inzwischen geändert – bitte neu laden und erneut prüfen.")
            ctx = _context(scenario_id=case.processing.scenario_id)
            if case.processing.rules_version and case.processing.rules_version != ctx.rules.version:
                raise HTTPException(409, "Die Regeln wurden seit der Verarbeitung geändert – bitte den Vorgang neu verarbeiten und erneut prüfen.")
            if body.action == "choose_staff_option" and approval.reason in {"ask_registered_email", "reply_anyway"}:
                # the reply the staff member will approve and copy is stored on the case itself
                variant = "ask_registered_email" if approval.reason == "ask_registered_email" else None
                case = case.model_copy(deep=True)
                case.reply_draft = render_reply(case, ctx, variant=variant)
            if body.action == "approve_assignment" and approval.contract_id:
                # Validate and regenerate BEFORE anything is audited: a failure leaves no trace of success.
                try:
                    actions.execute(case, approval, AuditLog(os.devnull))  # dry run of the permission checks
                except PermissionError as exc:
                    raise HTTPException(403, str(exc)) from None
                if ctx.erp.contract(approval.contract_id) is None:
                    raise HTTPException(422, "Vertrag ist im ERP nicht vorhanden")
                case = pipeline.apply_human_assignment(case, approval.contract_id, ctx)
            try:
                case = actions.execute(case, approval, app.state.audit)
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from None
            return app.state.store.save(case)

    @app.post("/api/translate")
    def translate_texts(body: TranslateRequest):
        """German system texts → English (deterministic, offline). Unknown text maps to null."""
        return {"translations": translate_many(body.texts[:500])}

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
    # Locally 127.0.0.1:8000; on a host set INTAKE_HOST=0.0.0.0 (Render provides PORT).
    uvicorn.run(app, host=os.getenv("INTAKE_HOST", "127.0.0.1"),
                port=int(os.getenv("PORT") or os.getenv("INTAKE_PORT") or "8000"))
