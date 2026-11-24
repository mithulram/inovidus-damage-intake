"""Every German text the system generates must have an English translation (Mithul reads English)."""

from __future__ import annotations

import pytest

from intake.i18n import translate
from intake.providers import get_provider
from intake.scenarios import load_scenarios, run_scenario


def system_texts(case) -> list[str]:
    m = case.match
    out = [m.reason, *(f.message for f in m.flags), *case.warnings, case.understanding.classification.reason,
           case.urgency.reason, *case.urgency.triggers, case.urgency.response_target, *case.urgency.safety_instructions,
           case.internal_task.title, *case.internal_task.checklist, case.internal_task.assignee_role,
           *(o.label for o in case.staff_options), *(p.reason for p in case.prior_cases)]
    for c in m.candidates:
        out += [s.reason for s in c.signals] + list(c.vetoes)
    if case.understanding.classification.category:
        out += [case.understanding.classification.category, case.understanding.classification.trade]
    return [t for t in out if t]


@pytest.mark.parametrize("sc", load_scenarios(), ids=lambda s: s.id)
def test_every_system_text_of_every_scenario_has_english(sc):
    case, _ = run_scenario(sc, provider=get_provider("offline"))
    missing = [t for t in system_texts(case) if translate(t) is None]
    assert missing == []


def test_examples():
    assert translate("Etage widerspricht: 2. OG ≠ 3. OG") == "Floor contradicts: floor 2 (German count: 2. OG) ≠ floor 3 (German count: 3. OG)"
    assert translate("Name stimmt überein (100 %)") == "Name matches (100 %)"
    assert translate("völlig unbekannter Satz") is None


def test_translate_endpoint():
    from fastapi.testclient import TestClient
    from intake.web.app import create_app
    client = TestClient(create_app())
    r = client.post("/api/translate", json={"texts": ["Hausmeister informieren", "xyz"]}).json()
    assert r["translations"] == {"Hausmeister informieren": "Inform the caretaker", "xyz": None}


def test_reply_preview_in_english_is_read_only(tmp_path):
    from fastapi.testclient import TestClient
    from intake.actions import AuditLog
    from intake.store import CaseStore
    from intake.web.app import create_app
    from intake.scenarios import load_scenarios
    c = TestClient(create_app(store=CaseStore(tmp_path / "c"), audit=AuditLog(tmp_path / "a.jsonl"), static_dir=tmp_path))
    sc = next(s for s in load_scenarios() if s.id == "S1")
    case = c.post("/api/process", json={"email": sc.email.model_dump(mode="json"), "scenario_id": "S1"}).json()
    en = c.post("/api/reply-preview", json={"case": case, "language": "en"}).json()
    assert en["language"] == "en" and en["body"].startswith("Hello") and en["auto_send"] is False
    assert c.get("/api/cases").json() == []  # nothing stored
