# Work order WO4 – Codex (builder) · inspected by Claude

Reader/draft fixes from Codex's re-inspection (R2-04, R2-05, R2-08, R2-09). Shared contract fixed – do not modify models, matching, pipeline, actions, web, steps/match.py, rule_checks.py, scenarios.
Files you own: `src/intake/providers/offline.py`, `src/intake/steps/draft.py`, `config/templates.yaml`, `config/rules.yaml` (only `classification`), their tests.

- **R2-04 (high):** the address regex must accept every supported street spelling: `str`, `str.`, `straße`, `strasse` (+ weg/platz/allee/gasse/ring), with or without space before the number. If body and subject contain **different** addresses, the body wins for `street_raw`/`house_no` and the other goes into `location_alternatives` (so review is forced). Regression: subject "Wasserschaden Küche, Musterstraße 12", body "Wasser läuft aus. Musterstr 14, zweite Etage links. Viele Grüße, Max Mustermann" → not READY_FOR_APPROVAL for MV-10245.
- **R2-05 (high):** uncertainty in a separate sentence that explicitly refers to the location ("Bei der Etage bin ich unsicher", "Die Hausnummer weiß ich nicht genau", "not sure about the floor") must fill `location_alternatives`. Unrelated uncertainty ("Ich bin unsicher, ob die Versicherung zahlt") must not. Regressions for both.
- **R2-08 (medium):** the reply for gate `unit_ambiguous` must ask the tenant to confirm the exact location (address, floor, side) – privacy rules unchanged (no ERP data). If `match.building_uncertain`, explicitly ask for the full address too.
- **R2-09 (medium):** category keywords must not prove damage by substring: use word-boundary matching for short/broad terms (e.g. `kalt` must not match `Kaltmiete`; consider removing `kalt` from Heizungsausfall or requiring a word boundary). Regression: "Frage zur Kaltmiete … Musterstr. 12, 2. OG links … Max Mustermann" → OUT_OF_SCOPE (ANFRAGE_MIETE); all NOTFALL phrases still classify as damage.

Proof: `uv run pytest && uv run intake-scenarios`. Do not commit.
