"""The business steps. Each step is ``run(case, ctx) -> case`` and only fills its own part.

The order here is the single source of truth: ``/api/process``, the CLI, the scenario
runner and the n8n workflow (one HTTP node per step) all use exactly this sequence.
"""

from __future__ import annotations

from collections.abc import Callable

from ..context import Context
from ..models import CaseRecord
from . import draft, match, prior_cases, task, understand, urgency

Step = Callable[[CaseRecord, Context], CaseRecord]

STEPS: dict[str, Step] = {
    "understand": understand.run,      # 2+3 Art erkennen, Infos extrahieren (KI oder Regeln)
    "match": match.run,                # 4   ERP-Zuordnung + Status (deterministisch)
    "prior_cases": prior_cases.run,    # 5   bestehende Vorgänge
    "urgency": urgency.run,            # 6   Dringlichkeit (Regel-Untergrenze + KI-Hinweis)
    "draft": draft.run,                # 8   Antwortentwurf (nie automatisch versendet)
    "task": task.run,                  # 9   interne Folgeaufgabe + Optionen für Sachbearbeiter
}

__all__ = ["STEPS", "Step"]
