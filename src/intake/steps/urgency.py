"""Step 6: rules set the minimum urgency; a provider may only raise it."""

from __future__ import annotations

from ..context import Context
from ..models import CaseRecord, Urgency, UrgencyResult
from ..normalize import fold
from ..rule_checks import matched_urgency_rules


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    if case.understanding is None:
        raise ValueError("Schritt 'urgency' braucht das Verständnis")
    case = case.model_copy(deep=True)
    text = fold(f"{case.input.subject}\n{case.input.body}")
    cfg = ctx.rules.urgency
    matched = matched_urgency_rules(case, ctx.rules)
    rule_level = Urgency.max(*(r.level for r in matched))
    llm_level = case.understanding.urgency_hint
    level = Urgency.max(rule_level, llm_level)
    safety = list(dict.fromkeys(instruction for r in matched if r.level == Urgency.NOTFALL and r.safety
                               for instruction in cfg.safety_instructions.get(r.safety, [])))
    reason = "Regel-Untergrenze: " + rule_level.value + "; " + (
        ", ".join(r.label for r in matched) if matched else "keine Dringlichkeitsregel getroffen"
    )
    if llm_level:
        reason += f". KI-Hinweis: {llm_level.value}; die strengere Einstufung gewinnt"
    case.urgency = UrgencyResult(
        level=level, rule_level=rule_level, llm_level=llm_level,
        triggers=[r.label for r in matched],
        tenant_says_urgent=any(fold(k) in text for k in cfg.tenant_urgency_words),
        response_target=cfg.levels[level].response_target, due_hours=cfg.levels[level].due_hours,
        safety_instructions=safety, reason=reason + ".",
    )
    return case
