"""Steps 2+3: ask the configured provider to classify and extract."""

from __future__ import annotations

from ..context import Context
from ..models import CaseRecord


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    understanding = ctx.provider.understand(case.input, ctx.rules)
    case = case.model_copy(deep=True)
    case.understanding = understanding
    case.processing.provider = understanding.provider
    case.processing.model = understanding.model
    case.processing.fallback_used = understanding.fallback_used
    case.warnings.extend(understanding.warnings)
    return case
