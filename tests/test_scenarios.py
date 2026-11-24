"""Every YAML scenario, exact expectations and runner failure behaviour."""

from datetime import datetime
from pathlib import Path

import pytest
import yaml

from intake.providers.offline import OfflineProvider
from intake.scenarios import Scenario, load_scenario, load_scenarios, main, run_scenario


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATHS = sorted([*(ROOT / "scenarios").glob("*.yaml"), *(ROOT / "scenarios").glob("*.yml")])


@pytest.mark.parametrize("path", SCENARIO_PATHS, ids=lambda path: path.stem)
def test_every_offline_scenario_satisfies_every_declared_expectation(path):
    scenario = load_scenario(path)
    case, checks = run_scenario(scenario, provider=OfflineProvider())
    assert checks
    assert {check.key for check in checks} == set(scenario.expected)
    assert len(checks) == len(scenario.expected)
    assert all(check.passed for check in checks), [check.model_dump() for check in checks if not check.passed]
    assert case.processing.provider == "offline"
    assert case.reply_draft.auto_send is False
    # Independently assert set comparisons; a subset comparison in the runner is unsafe.
    if "failed_gates" in scenario.expected:
        assert {gate.value for gate in case.match.failed_gates} == set(scenario.expected["failed_gates"])
    if "staff_options_available" in scenario.expected:
        assert {option.code for option in case.staff_options if option.available} == set(scenario.expected["staff_options_available"])
    clock = scenario.email.received_at or datetime.fromisoformat("2026-11-18T09:00:00+01:00")
    assert case.received_at == clock
    assert case.processed_at == clock
    assert all(event.ts == clock for event in case.audit)
    repeated, repeated_checks = run_scenario(scenario, provider="offline")
    assert repeated == case
    assert repeated_checks == checks


def test_loader_discovers_all_yaml_and_yml_in_stable_order(tmp_path):
    raw = {"id": "A", "title": "Testfall A", "email": {"body": "Hallo"}, "expected": {"status": "OUT_OF_SCOPE"}}
    (tmp_path / "b.yaml").write_text(yaml.safe_dump({**raw, "id": "B"}), encoding="utf-8")
    (tmp_path / "a.yml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("not a scenario", encoding="utf-8")
    assert [sc.id for sc in load_scenarios(tmp_path)] == ["A", "B"]
    assert len(load_scenarios()) == len(SCENARIO_PATHS) > 0


def test_loader_refuses_empty_directory_and_duplicate_ids(tmp_path):
    with pytest.raises(ValueError):
        load_scenarios(tmp_path)
    raw = {"id": "DUPLICATE", "title": "Doppelt", "email": {"body": "Hallo"}}
    for filename in ["one.yaml", "two.yml"]:
        (tmp_path / filename).write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_scenarios(tmp_path)


@pytest.mark.parametrize("expected_gates,passed", [
    (["floor_missing", "threshold", "margin"], True),
    (["floor_missing", "threshold"], False),
    (["floor_missing", "threshold", "margin", "identity"], False),
])
def test_gate_expectations_require_exact_set(expected_gates, passed):
    scenario = load_scenario(ROOT / "scenarios" / "S02_no_unit.yaml")
    scenario.expected = {"failed_gates": expected_gates}
    _, checks = run_scenario(scenario, provider="offline")
    assert checks[0].passed is passed


@pytest.mark.parametrize("expected_options,passed", [
    (["call_tenant", "reply_anyway", "ask_registered_email"], True),
    (["reply_anyway", "ask_registered_email"], False),
    (["call_tenant", "reply_anyway", "ask_registered_email", "extra"], False),
])
def test_staff_option_expectations_require_exact_set(expected_options, passed):
    scenario = load_scenario(ROOT / "scenarios" / "S04c_unknown_sender.yaml")
    scenario.expected = {"staff_options_available": expected_options}
    _, checks = run_scenario(scenario, provider="offline")
    assert checks[0].passed is passed


def test_unknown_expectation_is_rejected_instead_of_silently_ignored():
    scenario = Scenario(id="BAD", title="Unbekannte Erwartung", email={"body": "Hallo"}, expected={"typo": True})
    with pytest.raises(ValueError, match="typo"):
        run_scenario(scenario, provider="offline")


@pytest.mark.parametrize("key,correct,incorrect", [
    ("type", "SCHADENMELDUNG", "SONSTIGES"),
    ("category", "Wasserschaden", "Gasgeruch"),
    ("status", "READY_FOR_APPROVAL", "NEEDS_REVIEW"),
    ("contract", "MV-10245", "MV-10487"),
    ("winner", "MV-10245", "MV-10487"),
    ("urgency", "DRINGEND", "NORMAL"),
    ("failed_gates", [], ["identity"]),
    ("related_case", "VG-2026-0412", "VG-2026-0377"),
    ("reply_language", "de", "en"),
    ("warning_contains", "registrierten E-Mail-Adresse", "nonexistent warning"),
    ("staff_options_available", ["reply_anyway", "ask_registered_email", "call_tenant"], []),
    ("safety_instructions", False, True),
    ("task_scope", "contract", "object"),
])
def test_each_supported_expectation_accepts_correct_value_and_rejects_incorrect_value(key, correct, incorrect):
    scenario = load_scenario(ROOT / "scenarios" / "S04c_unknown_sender.yaml")
    for value, passed in [(correct, True), (incorrect, False)]:
        scenario.expected = {key: value}
        _, checks = run_scenario(scenario, provider="offline")
        check, = checks
        assert check.key == key
        assert check.expected == value
        assert check.passed is passed


@pytest.mark.parametrize("expected,passed", [("OUT_OF_SCOPE", True), ("READY_FOR_APPROVAL", False)])
def test_main_prints_german_table_and_exits_one_on_failure(monkeypatch, capsys, expected, passed):
    scenario = Scenario(id="CLI", title="Tabellentest", email={"body": "Hallo"}, expected={"status": expected})
    monkeypatch.setattr("intake.scenarios.load_scenarios", lambda: [scenario])
    if passed:
        assert main(["--provider", "offline"]) is None
    else:
        with pytest.raises(SystemExit) as exc:
            main(["--provider", "offline"])
        assert exc.value.code == 1
    output = capsys.readouterr().out
    assert all(heading in output for heading in ["ID", "Titel", "Status", "Vertrag", "Dringlichkeit", "Gates"])
    assert "CLI" in output and "Tabellentest" in output
    assert ("✔" if passed else "✖") in output
    assert f"1 Szenarien, {0 if passed else 1} fehlgeschlagen." in output
    if not passed:
        assert "Fehlgeschlagene Prüfungen" in output
        assert "status" in output


def test_main_reports_processing_exception_and_exits_one(monkeypatch, capsys):
    scenario = Scenario(id="ERROR", title="Fehlertest", email={"body": "Hallo"})
    monkeypatch.setattr("intake.scenarios.load_scenarios", lambda: [scenario])

    def fail(*args, **kwargs):
        raise ValueError("Injected scenario failure")

    monkeypatch.setattr("intake.scenarios.run_scenario", fail)
    with pytest.raises(SystemExit) as exc:
        main(["--provider", "offline"])
    assert exc.value.code == 1
    output = capsys.readouterr().out
    assert "FEHLER" in output and "Injected scenario failure" in output
