"""Load YAML examples and evaluate every declared expectation, without a live clock."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .context import Context
from .models import CaseRecord, InboundEmail
from .pipeline import process
from .providers import LLMProvider, get_provider
from .rules import ROOT

FIXED_NOW = datetime.fromisoformat("2026-11-18T09:00:00+01:00")


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    description: str = ""
    email: InboundEmail
    rule_overrides: dict[str, Any] = Field(default_factory=dict)
    data_overrides: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] = Field(default_factory=dict)


class Check(BaseModel):
    key: str
    expected: Any
    actual: Any
    passed: bool


def load_scenario(path: Path | str) -> Scenario:
    return Scenario.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def load_scenarios(dir: Path | str = "scenarios") -> list[Scenario]:
    directory = Path(dir)
    if not directory.is_absolute():
        directory = ROOT / directory
    paths = sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")])
    if not paths:
        raise ValueError(f"Keine Szenarien gefunden: {directory}")
    scenarios = [load_scenario(path) for path in paths]
    if len({sc.id for sc in scenarios}) != len(scenarios):
        raise ValueError("Szenario-IDs müssen eindeutig sein")
    return scenarios


def run_scenario(sc: Scenario, provider: LLMProvider | str | None = None) -> tuple[CaseRecord, list[Check]]:
    clock = sc.email.received_at or FIXED_NOW
    ctx = Context.build(provider=get_provider(provider) if isinstance(provider, str) else provider,
                        rule_overrides=sc.rule_overrides, data_overrides=sc.data_overrides, now=lambda: clock)
    case = process(sc.email, ctx, sc.id)
    actuals = {
        "type": case.understanding.classification.type.value,
        "category": case.understanding.classification.category,
        "status": case.status.value,
        "contract": case.match.selected_contract,
        "winner": case.match.winner,
        "urgency": case.urgency.level.value,
        "failed_gates": sorted(g.value for g in case.match.failed_gates),
        "related_case": [p.case_id for p in case.prior_cases if p.related],
        "reply_language": case.reply_draft.language,
        "warning_contains": case.warnings,
        "staff_options_available": sorted(o.code for o in case.staff_options if o.available),
        "safety_instructions": bool(case.urgency.safety_instructions),
        "task_scope": case.internal_task.scope,
    }
    checks = []
    for key, expected in sc.expected.items():
        if key not in actuals:
            raise ValueError(f"Unbekannte Szenario-Erwartung: {key}")
        actual = actuals[key]
        if key in {"failed_gates", "staff_options_available"}:
            passed = set(actual) == set(expected)
        elif key == "related_case":
            passed = expected in actual
        elif key == "warning_contains":
            passed = any(expected in warning for warning in actual)
        else:
            passed = actual == expected
        checks.append(Check(key=key, expected=expected, actual=actual, passed=passed))
    return case, checks


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Schadenmeldungen: Szenarien prüfen")
    parser.add_argument("--provider", default=None)
    args = parser.parse_args(argv)
    rows = [["ID", "Titel", "Status", "Vertrag", "Dringlichkeit", "Gates", "✔/✖"]]
    failures = []
    for sc in load_scenarios():
        try:
            case, checks = run_scenario(sc, provider=args.provider)
            passed = all(c.passed for c in checks)
            rows.append([sc.id, sc.title, case.status.value, case.match.selected_contract or "–",
                         case.urgency.level.value, ", ".join(g.value for g in case.match.failed_gates) or "–",
                         "✔" if passed else "✖"])
            failures.extend(f"{sc.id} / {c.key}: erwartet {c.expected!r}, erhalten {c.actual!r}"
                            for c in checks if not c.passed)
        except Exception as exc:
            rows.append([sc.id, sc.title, "FEHLER", "–", "–", "–", "✖"])
            failures.append(f"{sc.id}: {exc}")
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    for row in rows:
        print(" | ".join(cell.ljust(width) for cell, width in zip(row, widths)))
    if failures:
        print("\nFehlgeschlagene Prüfungen:")
        print("\n".join(failures))
    print(f"\n{len(rows) - 1} Szenarien, {sum(row[-1] == '✖' for row in rows[1:])} fehlgeschlagen.")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
