"""Steps 2+3: ask the configured provider to classify and extract."""

from __future__ import annotations

import re

from ..context import Context
from ..models import CaseRecord
from ..providers.offline import OfflineProvider, location_qualifiers, postal_for


NOT_IN_TEXT = "KI-Angabe nicht im Text gefunden, nicht verwendet: {field} '{value}'"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ß", "ss")).strip(" .,;:")


def _unquoted(case: CaseRecord, ext) -> dict[str, tuple[str, str]]:
    """Location values an AI reader returned that do not appear in the e-mail as whole words. The AI must only copy text."""
    text = _norm(f"{case.input.subject or ''} {case.input.body}")
    fields = {"street_raw": ("Straße", ext.street_raw), "house_no": ("Hausnummer", ext.house_no),
              "floor_raw": ("Etage", ext.floor_raw), "side_raw": ("Seite", ext.side_raw)}
    out = {}
    for key, (label, value) in fields.items():
        v = _norm(value or "")
        if v and not re.search(rf"(?<!\w){re.escape(v)}(?!\w)", text):
            out[key] = (label, value)
    return out


def run(case: CaseRecord, ctx: Context) -> CaseRecord:
    understanding = ctx.provider.understand(case.input, ctx.rules)
    if understanding.provider != OfflineProvider.name:
        # Deterministic safety facts for EVERY reader: "writes for someone else" and the postcode/town next to
        # the address are checked by fixed rules, also when an AI read the e-mail (the AI schema has no such fields).
        rules_view = OfflineProvider().understand(case.input, ctx.rules).extraction  # proxy check
        ext = understanding.extraction
        understanding = understanding.model_copy(update={"extraction": ext.model_copy(update={
            "on_behalf_of": ext.on_behalf_of or rules_view.on_behalf_of,
            # postcode/town next to the address THIS reader chose (not the rules reader's first address)
            "postal_raw": ext.postal_raw or postal_for(case.input, ctx.rules, ext.street_raw, ext.house_no),
            # building parts / flat numbers anywhere in the e-mail are doubt for this reader too
            "location_alternatives": list(dict.fromkeys([*ext.location_alternatives, *location_qualifiers(
                case.input, ctx.rules, " ".join(x for x in (ext.floor_raw, ext.side_raw) if x))]))})})
        # Evidence check: an address, floor or side the AI returns must be a quote from the e-mail. Otherwise the
        # value counts as unsure (review needed) – an invented "3. OG rechts" can never pick a contract.
        unquoted = _unquoted(case, understanding.extraction)
        if unquoted:
            ext = understanding.extraction
            # invented street/house number: the building itself is unsure; invented floor/side: the value is dropped
            # (a missing floor always means review; a missing side is no evidence either way)
            building_doubt = [v for k, (_, v) in unquoted.items() if k in ("street_raw", "house_no")]
            dropped = {k: None for k in unquoted if k in ("floor_raw", "side_raw")}
            understanding = understanding.model_copy(update={
                "extraction": ext.model_copy(update={**dropped, "location_alternatives": list(dict.fromkeys(
                    [*ext.location_alternatives, *building_doubt]))}),
                "warnings": [*understanding.warnings,
                             *(NOT_IN_TEXT.format(field=label, value=v) for label, v in unquoted.values())]})
    case = case.model_copy(deep=True)
    case.understanding = understanding
    case.processing.provider = understanding.provider
    case.processing.model = understanding.model
    case.processing.fallback_used = understanding.fallback_used
    case.warnings.extend(understanding.warnings)
    return case
