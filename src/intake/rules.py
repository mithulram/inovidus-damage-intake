"""Load and validate config/rules.yaml (+ optional per-scenario overrides)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Urgency

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_PATH = ROOT / "config" / "rules.yaml"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Weights(_M):
    name: float
    address: float
    floor: float
    side: float
    contact: float

    @model_validator(mode="after")
    def _sum_to_one(self) -> "Weights":
        total = self.name + self.address + self.floor + self.side + self.contact
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"match.weights müssen zusammen 1.0 ergeben (aktuell {total:.2f})")
        return self


class MatchRules(_M):
    threshold: float = Field(ge=0, le=1)
    min_margin: float = Field(ge=0, le=1)
    candidate_name_min: int = Field(ge=0, le=100)
    name_full_min: int = Field(ge=0, le=100)
    name_partial_min: int = Field(ge=0, le=100)
    weights: Weights
    unknown_sender_forces_review: bool = False


class NormalizeRules(_M):
    english_floor_counting: Literal["ask", "european"] = "ask"
    ordinal_words: dict[str, int]
    ground_floor_terms: list[str]
    unclear_floor_terms: list[str]
    side_terms: dict[Literal["L", "R", "M"], list[str]]


class OutOfScopeType(_M):
    keywords: list[str]
    route_to: str


class Category(_M):
    name: str
    trade: str
    keywords: list[str]


class ClassificationRules(_M):
    out_of_scope: dict[str, OutOfScopeType]
    damage_keywords: list[str]
    categories: list[Category]
    rooms: list[str]


class UrgencyLevelCfg(_M):
    response_target: str
    due_hours: int


class UrgencyRule(_M):
    level: Urgency
    label: str
    any: list[str]
    safety: Literal["gas", "water", "electric"] | None = None
    only_in_heating_season: bool = False


class UrgencyRules(_M):
    levels: dict[Urgency, UrgencyLevelCfg]
    heating_season_months: list[int]
    rules: list[UrgencyRule]
    tenant_urgency_words: list[str]
    safety_instructions: dict[str, list[str]]
    # when a hazard's instructions are active, drop other instructions containing these words
    # (e.g. gas: never advise operating fuses or switches)
    safety_conflicts: dict[str, list[str]] = {}


class PriorCaseRules(_M):
    related_categories: dict[str, list[str]]


class Rules(_M):
    match: MatchRules
    normalize: NormalizeRules
    classification: ClassificationRules
    urgency: UrgencyRules
    prior_cases: PriorCaseRules
    version: str = ""  # sha256 of the effective rules, filled by load_rules


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_rules(path: Path | str | None = None, overrides: dict[str, Any] | None = None) -> Rules:
    raw = yaml.safe_load(Path(path or DEFAULT_RULES_PATH).read_text(encoding="utf-8"))
    effective = deep_merge(raw, overrides or {})
    digest = hashlib.sha256(json.dumps(effective, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    rules = Rules.model_validate(effective)
    rules.version = f"sha256:{digest[:12]}"
    return rules
