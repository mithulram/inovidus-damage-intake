"""Step 8: bilingual templates, no delivery, no ERP facts in tenant replies."""

from pathlib import Path

import yaml

from ..context import Context
from ..models import CaseRecord, Gate, ReplyDraft, Status, Urgency
from ..rules import ROOT

TEMPLATES_PATH = ROOT / "config" / "templates.yaml"


def load_templates(path: Path | str | None = None) -> dict:
    return yaml.safe_load(Path(path or TEMPLATES_PATH).read_text(encoding="utf-8"))


def route_to(case: CaseRecord, ctx: Context) -> str:
    route = ctx.rules.classification.out_of_scope.get(case.understanding.classification.type.value)
    fallback = ctx.rules.classification.out_of_scope.get("SONSTIGES")
    return route.route_to if route else (fallback.route_to if fallback else "Kundenservice")


def render_reply(case: CaseRecord, ctx: Context, variant: str | None = None,
                 language: str | None = None) -> ReplyDraft:
    if case.understanding is None or case.match is None or case.urgency is None or case.status is None:
        raise ValueError("Antwortentwurf braucht Verständnis, Zuordnung, Status und Dringlichkeit")
    if variant not in (None, "ask_registered_email"):
        raise ValueError(f"Unbekannte explizite Antwortvariante: {variant}")
    language = language or case.understanding.extraction.language  # override = reading translation only
    templates = load_templates()
    texts = templates["reply"][language]
    translations = templates.get("translations", {}).get(language, {})
    paragraphs = []
    emergency = case.urgency.level == Urgency.NOTFALL and case.status != Status.OUT_OF_SCOPE
    if emergency:
        paragraphs.extend(translations.get(s, s) for s in case.urgency.safety_instructions)
        paragraphs.append(texts["emergency"])
    if variant == "ask_registered_email":
        variants = [variant]
    elif case.status == Status.OUT_OF_SCOPE:
        variants = ["out_of_scope"]
    elif case.status == Status.READY_FOR_APPROVAL:
        variants = ["NOTFALL"] if emergency else ["standard"]
    else:
        gates = set(case.match.failed_gates)
        variants = []
        unit_gates = {Gate.FLOOR_MISSING, Gate.FLOOR_AMBIGUOUS, Gate.UNIT_AMBIGUOUS,
                      Gate.THRESHOLD, Gate.MARGIN, Gate.VETO_UNIT}
        if emergency or gates & unit_gates:
            variants.append("confirm_unit")
        if Gate.IDENTITY in gates:
            variants.append("confirm_identity")
        if case.match.building_uncertain or gates & {Gate.VETO_ADDRESS, Gate.NO_CANDIDATE}:
            variants.append("confirm_address")
        if Gate.ELIGIBILITY in gates or not variants:
            variants.append("eligibility")
    if case.status != Status.OUT_OF_SCOPE and not emergency and variant is None:
        paragraphs.append(texts["receipt"])
    values = {
        "route_to": translations.get(route_to(case, ctx), route_to(case, ctx)),
        "response_target": translations.get(case.urgency.response_target, case.urgency.response_target),
    }
    paragraphs.extend(texts[v].format(**values) for v in variants if v != "NOTFALL")
    if (case.status == Status.READY_FOR_APPROVAL and variant is None
            and case.understanding.extraction.photos_mentioned and not case.input.attachments):
        paragraphs.append(texts["photos"])
    body = "\n\n".join([texts["greeting"], *paragraphs, texts["closing"]])
    return ReplyDraft(language=language, variant=variant or ("NOTFALL" if emergency else "+".join(variants)),
                      to=case.input.sender_email, subject=f"Re: {case.input.subject}", body=body)


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    case = case.model_copy(deep=True)
    case.reply_draft = render_reply(case, ctx)
    return case
