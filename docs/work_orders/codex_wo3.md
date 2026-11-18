# Work order WO3 – Codex (builder) · inspected by Claude

Fixes from Codex's own inspection of the reader layer (findings R03, R04 in docs/BUILD-REVIEW-LOG.md) plus two text issues Claude found. Shared contract is fixed – do not modify `models.py`, `matching.py`, `rules.py`, `pipeline.py`, `web/`, scenarios.
Environment: no network; `uv run pytest`.

## Files you own
`src/intake/providers/offline.py`, `src/intake/providers/llm_schema.py`, `config/prompts/understanding_system.txt`, `config/templates.yaml`, `src/intake/steps/task.py`, `config/rules.yaml` (only the `classification` section), their tests (`tests/test_offline_provider.py`, `tests/test_llm_providers.py`, `tests/test_draft_task.py`).

## R03 (high) – an emergency must never become "not a damage report"
An email containing only e.g. "Burst pipe. Musterstr. 12, 2. OG links. Max Mustermann" is classified SONSTIGES → OUT_OF_SCOPE, which suppresses emergency instructions and lowers the task priority.
Fix: a message is `SCHADENMELDUNG` when **any** of these match: `damage_keywords`, any `classification.categories[*].keywords`, or any `urgency.rules[*].any` keyword. Only then fall back to out-of-scope types. Add tests for every NOTFALL rule phrase (each must classify as SCHADENMELDUNG with NOTFALL urgency end-to-end) and keep S6 (rent question) OUT_OF_SCOPE.

## R04 (high) – several or uncertain locations must force review
New shared field (already added by Claude): `Extraction.location_alternatives: list[str]` (default `[]`); `matching.py` raises gate `unit_ambiguous` when it is non-empty.
- OfflineProvider: fill it when the email names **more than one distinct** floor and/or side or address (e.g. "2. OG links oder 3. OG rechts"), or contains an uncertainty marker near the location ("unsicher", "weiß nicht genau", "oder", "not sure", "either"). Put the extra/uncertain spans (as written) into the list; keep the first location in `floor_raw`/`side_raw`.
- LLM: add `location_alternatives` (array of strings, required, may be empty) to the strict schema in `llm_schema.py` and one sentence to the system prompt ("Nennt die E-Mail mehrere oder unsichere Ortsangaben, liste die weiteren/unsicheren wörtlich in location_alternatives"). `parse_llm_content` must still accept the 5 recorded fixtures (which lack the field → default `[]`). Keep `examples/llm_recorded/schema.json` untouched (it documents what was recorded); the live schema may differ – add a test that asserts recorded fixtures parse.
- Tests: the inspection example ("Wasser läuft aus. Musterstr. 12, 2. OG links oder 3. OG rechts; ich bin bei der Etage unsicher. Viele Grüße, Max Mustermann") ends `NEEDS_REVIEW` with `unit_ambiguous` in failed gates; S1 is unaffected.

## T1 (low) – room casing
The offline reader returns the rule term in lower case ("küche"), which shows in task titles ("Wasserschaden küche"). Return the room as written in the email (original casing), falling back to a capitalised rule term.

## T2 (low) – task text
`book_contractor` currently renders "Handwerker beauftragen: Handwerker innerhalb von 24 Stunden (Ziel: 24 Stunden)". Rephrase the template so it reads naturally for every urgency level, e.g. "Handwerker beauftragen – Ziel: {response_target}". Same for the English reply `standard` text if needed. Keep all other wording.

## Proof
```
uv run pytest && uv run intake-scenarios
```
Do not commit.
