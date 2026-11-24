"""Internal prior-case lookup and relation rules."""

from datetime import datetime, timezone

import pytest

from intake.context import Context
from intake.models import Candidate, Gate, InboundEmail, MatchResult, NormalizedLocation
from intake.pipeline import new_case
from intake.providers.offline import OfflineProvider
from intake.steps.prior_cases import run


def make_case(ctx, *, selected=None, winner=None, contract_ids=()):
    email = InboundEmail(body="Wasser läuft in der Küche aus.")
    case = new_case(email, ctx)
    case.understanding = ctx.provider.understand(email, ctx.rules)
    case.match = MatchResult(
        location=NormalizedLocation(), selected_contract=selected, winner=winner, reason="Testzuordnung",
        candidates=[Candidate(
            contract_id=c.contract_id, tenant_name=c.tenant_name, unit_label=c.unit_label,
            object_id=c.object_id, unit_id=c.unit_id, active=c.active, score=0.5, signals=[],
        ) for c in (ctx.erp.contract(cid) for cid in contract_ids)],
    )
    return case


def context(**kwargs):
    return Context.build(provider=OfflineProvider(), now=lambda: datetime(2026, 11, 18, tzinfo=timezone.utc), **kwargs)


@pytest.mark.parametrize("selected,winner,expected", [
    ("MV-10245", "MV-10487", "VG-2026-0412"),
    (None, "MV-10487", "VG-2026-0377"),
])
def test_selected_contract_precedes_winner_and_winner_precedes_candidates(selected, winner, expected):
    ctx = context()
    case = make_case(ctx, selected=selected, winner=winner, contract_ids=["MV-10245", "MV-10487"])
    result = run(case, ctx)
    assert [p.case_id for p in result.prior_cases] == [expected]
    assert case.prior_cases == []


@pytest.mark.parametrize("category,room,state,related", [
    ("Rohrverstopfung", "Bad", "closed", True),
    ("Elektrik", "KÜCHE", "open", True),
    ("Rohrverstopfung", "Küche", "open", True),
    ("Elektrik", "Bad", "open", False),
    ("Elektrik", None, "closed", False),
])
def test_related_category_or_folded_room_and_only_open_related_cases_are_duplicates(category, room, state, related):
    ctx = context(data_overrides={"cases": [{
        "case_id": "VG-2026-0412", "category": category, "room": room, "state": state,
    }]})
    result = run(make_case(ctx, selected="MV-10245"), ctx)
    prior, = result.prior_cases
    assert prior.related is related
    assert prior.possible_duplicate is (related and state == "open")
    assert prior.contract_id == "MV-10245"
    assert prior.state == state
    assert prior.closed_at == "2026-08-05"
    assert prior.contractor == "Sanitär Beispiel GmbH"
    assert "gleiche Einheit" in prior.reason
    if room and room.lower() == "küche":
        assert "gleicher Raum" in prior.reason
    if category == "Rohrverstopfung":
        assert "verwandte Schadenart" in prior.reason


def test_relation_table_is_configurable_and_wrong_unit_is_excluded():
    ctx = context(
        rule_overrides={"prior_cases": {"related_categories": {"Wasserschaden": ["Elektrik"]}}},
        data_overrides={"cases": [
            {"case_id": "VG-2026-0412", "category": "Elektrik", "room": "Bad"},
            {"case_id": "WRONG-UNIT", "contract_id": "MV-10245", "unit_id": "OBJ-MS12-3R",
             "title": "Fremder Vorgang", "category": "Elektrik", "room": "Küche", "state": "open"},
        ]},
    )
    result = run(make_case(ctx, selected="MV-10245"), ctx)
    assert [p.case_id for p in result.prior_cases] == ["VG-2026-0412"]
    assert result.prior_cases[0].related is True


def test_candidate_fallback_skips_both_veto_forms_and_caps_lookup_at_three():
    base = context()
    contracts = base.erp.contracts()
    extra = contracts[-1].model_dump()
    extra.update(contract_id="MV-EXTRA", unit_id="EXTRA-UNIT")
    records = [*contracts, type(contracts[-1]).model_validate(extra)]
    old_cases = [{
        "case_id": f"PRIOR-{i}", "contract_id": c.contract_id, "unit_id": c.unit_id,
        "title": f"Testvorgang {i}", "category": "Wasserschaden", "room": "Küche", "state": "open",
    } for i, c in enumerate(records)]
    # Remove seed cases from these units, so the returned IDs prove the lookup cap.
    old_cases.extend({"case_id": cid, "unit_id": "OTHER-UNIT"} for cid in ["VG-2026-0412", "VG-2026-0377"])
    ctx = context(data_overrides={"contracts": [extra], "cases": old_cases})
    case = make_case(ctx, contract_ids=[c.contract_id for c in records])
    case.match.candidates[0].vetoes = ["Adresse widerspricht"]
    case.match.candidates[1].veto_gates = [Gate.VETO_UNIT]
    assert [p.case_id for p in run(case, ctx).prior_cases] == ["PRIOR-2", "PRIOR-3", "PRIOR-4"]


def test_no_candidate_produces_no_prior_cases():
    ctx = context()
    assert run(make_case(ctx), ctx).prior_cases == []


def test_s02_ambiguous_stage_a_shows_both_contract_histories():
    from intake.scenarios import load_scenario, run_scenario

    case, _ = run_scenario(load_scenario("scenarios/S02_no_unit.yaml"), provider="offline")
    assert {Gate.THRESHOLD, Gate.MARGIN} & set(case.match.failed_gates)
    assert {p.contract_id for p in case.prior_cases} == {"MV-10245", "MV-10487"}


@pytest.mark.parametrize("gate", [Gate.THRESHOLD, Gate.MARGIN])
def test_ambiguous_stage_a_ignores_arbitrary_winner_but_selected_still_wins(gate):
    ctx = context()
    case = make_case(ctx, winner="MV-10245", contract_ids=["MV-10245", "MV-10487"])
    case.match.failed_gates = [gate]
    assert {p.contract_id for p in run(case, ctx).prior_cases} == {"MV-10245", "MV-10487"}
    case.match.selected_contract = "MV-10487"
    assert {p.contract_id for p in run(case, ctx).prior_cases} == {"MV-10487"}


@pytest.mark.parametrize("missing", ["match", "understanding"])
def test_lookup_requires_matching_and_understanding(missing):
    ctx = context()
    case = make_case(ctx)
    setattr(case, missing, None)
    with pytest.raises(ValueError):
        run(case, ctx)
