"""Rule checks shared by several steps (no provider involved)."""

from __future__ import annotations

from .models import CaseRecord, Urgency
from .normalize import fold
from .rules import Rules, UrgencyRule


def matched_urgency_rules(case: CaseRecord, rules: Rules) -> list[UrgencyRule]:
    """Urgency rules whose keywords occur in subject/body, respecting the heating season."""
    text = fold(f"{case.input.subject}\n{case.input.body}")
    cfg = rules.urgency
    month = (case.input.received_at or case.received_at).month
    return [r for r in cfg.rules
            if (not r.only_in_heating_season or month in cfg.heating_season_months)
            and any(fold(k) in text for k in r.any)]


def is_rule_emergency(case: CaseRecord, rules: Rules) -> bool:
    return any(r.level == Urgency.NOTFALL for r in matched_urgency_rules(case, rules))
