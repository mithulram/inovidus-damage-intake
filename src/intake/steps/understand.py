"""Steps 2+3: ask the configured provider to classify and extract."""

from __future__ import annotations

from ..context import Context
from ..models import CaseRecord
from ..providers.offline import OfflineProvider, postal_for


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    understanding = ctx.provider.understand(case.input, ctx.rules)
    if understanding.provider != OfflineProvider.name:
        # Deterministic safety facts for EVERY reader: "writes for someone else" and the postcode/town next to
        # the address are checked by fixed rules, also when an AI read the e-mail (the AI schema has no such fields).
        rules_view = OfflineProvider().understand(case.input, ctx.rules).extraction
        ext = understanding.extraction
        understanding = understanding.model_copy(update={"extraction": ext.model_copy(update={
            "on_behalf_of": ext.on_behalf_of or rules_view.on_behalf_of,
            # postcode/town next to the address THIS reader chose (not the rules reader's first address)
            "postal_raw": ext.postal_raw or postal_for(case.input, ctx.rules, ext.street_raw, ext.house_no)})})
    case = case.model_copy(deep=True)
    case.understanding = understanding
    case.processing.provider = understanding.provider
    case.processing.model = understanding.model
    case.processing.fallback_used = understanding.fallback_used
    case.warnings.extend(understanding.warnings)
    return case
