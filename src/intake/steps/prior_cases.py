"""Step stub – implemented by Codex (see docs/work_orders/codex_wo1.md)."""

from __future__ import annotations

from ..context import Context
from ..models import CaseRecord


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    raise NotImplementedError("prior_cases: see docs/work_orders/codex_wo1.md")
