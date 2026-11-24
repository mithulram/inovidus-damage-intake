"""Urgency floors, model hints, received dates and safety instructions."""

from datetime import datetime, timezone

import pytest

from intake.context import Context
from intake.models import InboundEmail, Urgency
from intake.pipeline import new_case
from intake.providers.offline import OfflineProvider
from intake.steps.urgency import run


def urgency_case(body, *, hint=None, received_at=None, case_month=11, overrides=None):
    ctx = Context.build(provider=OfflineProvider(), rule_overrides=overrides,
                        now=lambda: datetime(2030, 7, 1, tzinfo=timezone.utc))
    email = InboundEmail(body=body, received_at=received_at)
    case = new_case(email, ctx)
    case.received_at = datetime(2026, case_month, 18, tzinfo=timezone.utc)
    case.understanding = ctx.provider.understand(email, ctx.rules)
    case.understanding.urgency_hint = hint
    return case, ctx


@pytest.mark.parametrize("body,rule_level", [
    ("Der Fenstergriff ist kaputt.", Urgency.NORMAL),
    ("Wasser läuft aus.", Urgency.DRINGEND),
    ("Gasgeruch und Wasser läuft aus.", Urgency.NOTFALL),
])
@pytest.mark.parametrize("hint", [None, Urgency.NORMAL, Urgency.DRINGEND, Urgency.NOTFALL])
def test_stricter_wins_for_every_rule_and_hint_combination(body, rule_level, hint):
    case, ctx = urgency_case(body, hint=hint)
    result = run(case, ctx).urgency
    order = [Urgency.NORMAL, Urgency.DRINGEND, Urgency.NOTFALL]
    expected = order[max(order.index(rule_level), order.index(hint or Urgency.NORMAL))]
    assert result.rule_level == rule_level
    assert result.llm_level == hint
    assert result.level == expected
    assert result.due_hours == {Urgency.NORMAL: 120, Urgency.DRINGEND: 24, Urgency.NOTFALL: 2}[expected]
    assert result.response_target == ctx.rules.urgency.levels[expected].response_target
    assert "Regel" in result.reason


@pytest.mark.parametrize("month", range(1, 13))
@pytest.mark.parametrize("use_input_date", [True, False], ids=["input-date", "case-date-fallback"])
def test_heating_season_uses_received_month_not_processing_clock(month, use_input_date):
    case, ctx = urgency_case(
        "Heizung ausgefallen.",
        received_at=datetime(2026, month, 18, tzinfo=timezone.utc) if use_input_date else None,
        case_month=(7 if month in {10, 11, 12, 1, 2, 3, 4} else 11) if use_input_date else month,
    )
    result = run(case, ctx).urgency
    winter = month in {10, 11, 12, 1, 2, 3, 4}
    assert result.level == (Urgency.NOTFALL if winter else Urgency.DRINGEND)
    assert ("Heizungsausfall in der Heizperiode" in result.triggers) == winter


def test_heating_season_months_and_deadline_are_configurable():
    case, ctx = urgency_case("Heizung ausgefallen.", case_month=7, overrides={"urgency": {
        "heating_season_months": [7], "levels": {"NOTFALL": {"due_hours": 1, "response_target": "jetzt"}},
    }})
    result = run(case, ctx).urgency
    assert result.level == Urgency.NOTFALL
    assert (result.due_hours, result.response_target) == (1, "jetzt")


@pytest.mark.parametrize("word", ["dringend", "sofort", "urgent", "ASAP"])
def test_tenant_urgency_words_are_recorded_without_raising_level(word):
    case, ctx = urgency_case(f"Der Fenstergriff ist kaputt, {word}!")
    result = run(case, ctx).urgency
    assert result.tenant_says_urgent is True
    assert result.level == Urgency.NORMAL
    assert result.triggers == []
    assert result.safety_instructions == []


def test_all_matched_triggers_and_safety_instructions_are_ordered_and_deduplicated():
    case, ctx = urgency_case("GASGERUCH, Rohrbruch, Wasser in der Steckdose!", overrides={"urgency": {
        "safety_instructions": {
            "gas": ["Gebäude verlassen.", "112 anrufen."],
            "water": ["Wasser abstellen.", "112 anrufen."],
            "electric": ["Sicherung ausschalten.", "Gebäude verlassen."],
        },
    }})
    result = run(case, ctx).urgency
    assert result.triggers == ["Gasgeruch", "Rohrbruch / Wasser läuft durch Decke oder steht", "Wasser an Elektrik / Stromausfall"]
    # gas is active: advice to operate fuses/switches from other hazards is dropped
    assert result.safety_instructions == ["Gebäude verlassen.", "112 anrufen.", "Wasser abstellen."]


def test_subject_is_considered_and_missing_understanding_is_refused():
    case, ctx = urgency_case("Bitte helfen.")
    case.input.subject = "Gasgeruch"
    assert run(case, ctx).urgency.level == Urgency.NOTFALL
    case.understanding = None
    with pytest.raises(ValueError):
        run(case, ctx)
