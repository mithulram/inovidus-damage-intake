"""Matching + gating tests, independent of how the email was read (extraction given directly)."""

from __future__ import annotations

import pytest

from intake.erp import JsonERP
from intake.matching import match
from intake.models import Extraction, Gate, InboundEmail
from intake.normalize import normalize_floor, normalize_side, normalize_street
from intake.rules import load_rules

RULES = load_rules()


def ext(**kw) -> Extraction:
    base = dict(tenant_name="Max Mustermann", sender_name="Max Mustermann", street_raw="Musterstr.", house_no="12",
                floor_raw="zweite Etage", side_raw="links")
    base.update(kw)
    return Extraction(**base)


def run(extraction: Extraction, sender: str | None = None, rule_overrides=None, data_overrides=None):
    rules = load_rules(overrides=rule_overrides) if rule_overrides else RULES
    email = InboundEmail(body="(test)", sender_email=sender)
    return match(extraction, email, JsonERP(overrides=data_overrides), rules)


def gates(result) -> set[str]:
    return {g.value for g in result.failed_gates}


# --- normalisation -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Musterstr.", "musterstrasse"), ("Musterstraße", "musterstrasse"), ("Musterstrasse", "musterstrasse"),
    ("musterstr", "musterstrasse"), ("Muster-Straße", "musterstrasse"), ("Beispielweg", "beispielweg"),
])
def test_street(raw, expected):
    assert normalize_street(raw) == expected


@pytest.mark.parametrize("raw,floor,status", [
    ("zweite Etage", 2, "ok"), ("2. OG", 2, "ok"), ("2.OG", 2, "ok"), ("im 2. Stock", 2, "ok"),
    ("im dritten Stock", 3, "ok"), ("erste Etage", 1, "ok"), ("1. OG", 1, "ok"),
    ("EG", 0, "ok"), ("Erdgeschoss", 0, "ok"), ("Parterre", 0, "ok"), ("ground floor", 0, "ok"),
    ("2nd floor", 2, "english_ordinal"), ("second floor", 2, "english_ordinal"),
    ("Hochparterre", None, "unclear"), ("ganz oben", None, "unclear"), (None, None, "missing"), ("", None, "missing"),
])
def test_floor_german_counting(raw, floor, status):
    value, st, _ = normalize_floor(raw, RULES.normalize)
    assert (value, st) == (floor, status)


@pytest.mark.parametrize("raw,side", [("links", "L"), ("li.", "L"), ("li", "L"), ("left", "L"), ("re.", "R"),
                                      ("rechts", "R"), ("right", "R"), ("Mitte", "M"), (None, None), ("oben", None)])
def test_side(raw, side):
    assert normalize_side(raw, RULES.normalize) == side


# --- the task's trap ------------------------------------------------------------

def test_original_email_selects_mv_10245_and_vetoes_mv_10487():
    r = run(ext())
    assert r.selected_contract == "MV-10245"
    assert r.failed_gates == []
    assert r.score == pytest.approx(0.90)
    other = next(c for c in r.candidates if c.contract_id == "MV-10487")
    assert any("3. OG" in v for v in other.vetoes)
    assert Gate.VETO_UNIT in other.veto_gates
    assert r.object_id == "OBJ-MS12"


def test_every_signal_has_a_german_reason():
    r = run(ext())
    for cand in r.candidates:
        assert all(s.reason for s in cand.signals)
    assert r.reason


def test_without_unit_two_candidates_tie():
    r = run(ext(floor_raw=None, side_raw=None))
    assert r.selected_contract is None
    assert gates(r) == {"floor_missing", "threshold", "margin"}
    scores = {c.contract_id: c.score for c in r.candidates}
    assert scores["MV-10245"] == scores["MV-10487"] == pytest.approx(0.60)


def test_inactive_contract_never_falls_back():
    r = run(ext(), data_overrides={"contracts": [{"contract_id": "MV-10245", "active": False}]})
    assert r.winner == "MV-10245"
    assert r.selected_contract is None
    assert gates(r) == {"eligibility"}


def test_inactive_unit_stays_in_ambiguity_check():
    extra = {"contract_id": "MV-10999", "tenant_name": "Max Mustermann", "object_id": "OBJ-MS12", "street": "Musterstraße",
             "house_no": "12", "floor": 2, "floor_label": "2. OG", "side": "R", "side_label": "re.",
             "unit_id": "OBJ-MS12-2R", "active": True,
             "contact": {"email": "max.mustermann@example.org", "phone": None, "synthetic": True}}
    r = run(ext(floor_raw="2. Etage", side_raw=None), sender="max.mustermann@example.org",
            data_overrides={"contracts": [{"contract_id": "MV-10245", "active": False}, extra]})
    scores = {c.contract_id: c.score for c in r.candidates}
    assert scores["MV-10245"] == scores["MV-10999"] == pytest.approx(0.90)  # both clear the threshold
    assert gates(r) == {"margin"}
    assert r.selected_contract is None


def test_partial_name_forces_review_even_above_threshold():
    r = run(ext(tenant_name="M. Musterman", sender_name="M. Musterman"), sender="max.mustermann@example.org")
    assert r.score == pytest.approx(0.85)
    assert gates(r) == {"identity"}


def test_sender_not_contract_holder():
    r = run(ext(sender_name="Erika Muster"))
    assert r.score == pytest.approx(0.90)
    assert gates(r) == {"identity"}


def test_unknown_sender_is_warning_not_block_by_default():
    r = run(ext(), sender="max.privat@example.net")
    assert r.selected_contract == "MV-10245"
    assert r.unknown_sender is True
    assert r.failed_gates == []


def test_unknown_sender_switch_forces_review():
    r = run(ext(), sender="max.privat@example.net", rule_overrides={"match": {"unknown_sender_forces_review": True}})
    assert gates(r) == {"identity"}


def test_english_floor_asks_by_default_and_switch_accepts():
    r = run(ext(floor_raw="2nd floor", side_raw="left"))
    assert r.score == pytest.approx(0.90)
    assert gates(r) == {"floor_ambiguous"}
    r2 = run(ext(floor_raw="2nd floor", side_raw="left"), rule_overrides={"normalize": {"english_floor_counting": "european"}})
    assert r2.selected_contract == "MV-10245"


def test_lower_threshold_cannot_make_other_building_ready():
    r = run(ext(street_raw="Musterstraße", house_no="16"), sender="max.mustermann@example.org",
            rule_overrides={"match": {"threshold": 0.65}})
    top = r.candidates[0]
    assert top.contract_id == "MV-10245" and top.score == pytest.approx(0.70)  # would pass 0.65 without the veto
    assert gates(r) == {"veto_address"}
    assert r.selected_contract is None


def test_lower_threshold_cannot_skip_missing_floor():
    r = run(ext(floor_raw=None), rule_overrides={"match": {"threshold": 0.65}})
    assert r.score == pytest.approx(0.70)
    assert gates(r) == {"floor_missing"}


def test_unknown_tenant_no_candidate():
    r = run(ext(tenant_name="Mithul G", sender_name="Mithul G", street_raw="Unbekanntweg", house_no="1"))
    assert gates(r) >= {"no_candidate"}
    assert r.selected_contract is None


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        load_rules(overrides={"match": {"weights": {"name": 0.5}}})
