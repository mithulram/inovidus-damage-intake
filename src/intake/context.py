"""Everything a step needs besides the case itself: rules, ERP, LLM provider, clock."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .erp import ERPConnector, JsonERP
from .rules import Rules, load_rules

if TYPE_CHECKING:
    from .providers.base import LLMProvider


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Context:
    rules: Rules
    erp: ERPConnector
    provider: "LLMProvider"
    now: Callable[[], datetime] = field(default=_utcnow)

    @classmethod
    def build(
        cls,
        provider: "LLMProvider | None" = None,
        rule_overrides: dict[str, Any] | None = None,
        data_overrides: dict[str, Any] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> "Context":
        from .providers import get_provider

        return cls(
            rules=load_rules(overrides=rule_overrides),
            erp=JsonERP(overrides=data_overrides),
            provider=provider or get_provider(),
            now=now or _utcnow,
        )
