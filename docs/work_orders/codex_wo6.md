# Work order WO6 – Codex (builder) · inspected by Claude

Finding R5-01 from Codex's inspection round 5. Files you own: `src/intake/providers/offline.py` and `tests/test_offline_provider.py` only.

**R5-01 (high):** "Gasgeruch. Vielleicht Musterstr. 12. Viele Grüße, Max Mustermann" keeps only "Vielleicht" in `location_alternatives`; the address token is not recognised inside the uncertainty clause, so matching cannot mark the building uncertain and a building-level action is allowed.
Fix: when an uncertainty marker applies to a clause that contains an address (any supported street spelling + number), a floor or a side, keep the **whole clause including that location text** (e.g. "Vielleicht Musterstr. 12"). `matching.py` already treats an alternative containing a street word or ending in a house number as building uncertainty. Add end-to-end regressions (Context + pipeline, offline provider):
- the example above → `match.building_uncertain is True`, `match.object_id is None`, task scope not "object";
- "Wasser läuft aus. Vielleicht 2. OG, Musterstr. 12, links. Max Mustermann" → `unit_ambiguous` in failed gates;
- S1 and "Bitte kommen Sie vielleicht morgen. Musterstr. 12, 2. OG links. Max Mustermann" (uncertainty about time, separate clause) → no alternatives.
Proof: `uv run pytest && uv run intake-scenarios`. Do not commit.
