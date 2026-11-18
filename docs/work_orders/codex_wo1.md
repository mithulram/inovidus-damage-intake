# Work order WO1 – Codex (builder) · inspected by Claude

Derived from the Codex-approved plan `docs/PLAN.md` (sha256 738ae076…, 10/10). Read §4–§10, §12, §18 of the plan first.
Shared contract (do **not** modify – report needed changes instead): `src/intake/models.py`, `rules.py`, `erp.py`, `context.py`, `pipeline.py`, `steps/__init__.py`, `steps/understand.py`, `steps/match.py`, `matching.py`, `normalize.py`, `providers/base.py`, `providers/__init__.py`, `config/rules.yaml`, `data/*`, `scenarios/*`, `tests/test_matching.py`.
Environment: `uv sync` is done (Python 3.12, deps in `pyproject.toml`); no network needed. Run tests with `uv run pytest`.

## Files you own (create/replace)
| File | What |
|---|---|
| `src/intake/providers/offline.py` | `OfflineProvider` (name `offline`, model `None`) implementing `LLMProvider.understand` with rules only |
| `src/intake/steps/prior_cases.py` | step 5 |
| `src/intake/steps/urgency.py` | step 6 |
| `src/intake/steps/draft.py` | step 8 + public `render_reply(case, ctx, variant: str | None = None) -> ReplyDraft` |
| `src/intake/steps/task.py` | step 9 + staff options |
| `config/templates.yaml` | all reply texts (de + en) and task checklist texts – business people edit texts here |
| `src/intake/actions.py` | the ONE action handler + append-only audit log |
| `src/intake/scenarios.py` | load + run scenarios, check expectations, `main()` prints a table, exit 1 on any failure |
| `src/intake/cli.py` | `main()` for `uv run intake …` |
| `tests/test_offline_provider.py`, `test_urgency.py`, `test_prior_cases.py`, `test_draft_task.py`, `test_actions.py`, `test_scenarios.py` | tests |

## 1. OfflineProvider (no key, deterministic) – uses `rules.classification`
- **Type:** damage keyword present → `SCHADENMELDUNG`; else an `out_of_scope` type whose keywords match (e.g. `ANFRAGE_MIETE`); else `SONSTIGES`. Compare on `normalize.fold()` text (subject + body).
- **Category/trade:** first entry of `classification.categories` (list order = priority) with a keyword hit. Confidence: 0.9 with a category hit, 0.6 without; reason in German naming the matched keywords.
- **Extraction (raw spans, never normalised values):**
  - `street_raw`/`house_no`: street name ending in `str.|straße|strasse|weg|platz|allee|gasse|ring` + number (`Musterstr. 12`, `Musterstraße 16`, `Musterstrasse 12`).
  - `floor_raw`: the floor phrase as written (`zweite Etage`, `2. OG`, `2. Etage`, `3. OG`, `EG`, `2nd floor`, `Hochparterre`, `im dritten Stock`); `None` if absent. `side_raw`: `links|li.|rechts|re.|left|right|Mitte` near the address/floor. Feed both through `normalize.normalize_floor/normalize_side` in your tests to prove they parse.
  - `sender_name`: the signature – the name after a closing (`Viele Grüße,`, `Grüße`, `LG`, `Best regards,`, `Regards,`) or the trailing capitalised name at the very end (`… Bitte schnell kommen. Max Mustermann`).
  - `tenant_name`: an explicitly named contract holder (`Wohnung von Max Mustermann`, `für meinen Partner Max Mustermann`); otherwise = `sender_name`.
  - `room` (first of `classification.rooms`), `damage_description` (first sentence with a damage keyword), `since` (`seit gestern`, `seit heute Morgen`, `since yesterday`), `photos_mentioned` (Foto/Fotos/Bilder/photo), `phone` (if present), `language` (`en` if English stop words dominate, else `de`).
- `urgency_hint = None` (rules decide offline). `provider="offline"`.

## 2. Step `prior_cases`
- Contracts to look at: `match.selected_contract`, else `match.winner`, else every non-vetoed candidate (max 3) – for the reviewer.
- `related = True` if the old case's category is in `rules.prior_cases.related_categories[current category]` **or** same room (fold-compare). `possible_duplicate = related and state == "open"`. German `reason` (e.g. "gleiche Einheit, gleicher Raum (Küche), verwandte Schadenart").
- Prior cases are internal only: never mentioned in the tenant reply.

## 3. Step `urgency`
- `rule_level` = highest level among `rules.urgency.rules` whose `any` keywords occur in fold(subject + body); `only_in_heating_season` rules count only if the month of `case.input.received_at` (fallback `case.received_at`) is in `heating_season_months`. No hit → `NORMAL`.
- `llm_level` = `understanding.urgency_hint`; final `level = Urgency.max(rule_level, llm_level)` (**the stricter wins; the LLM can only raise**).
- `triggers` = matched rule labels; `tenant_says_urgent` from `tenant_urgency_words` (recorded, does **not** raise the level); `safety_instructions` from `rules.urgency.safety_instructions[rule.safety]` of matched NOTFALL rules (dedupe, keep order); `response_target`/`due_hours` from `levels[level]`; German `reason`.

## 4. Step `draft` (never sent) – texts in `config/templates.yaml`
- `language` from `understanding.extraction.language`; `to` = `input.sender_email`; `subject` = `Re: <original subject>`; `auto_send` stays `False`.
- Variant by situation (combine the "ask" paragraphs when several gates failed):
  - `out_of_scope`: forwarded to `<route_to>`, no damage promises.
  - `NOTFALL`: safety instructions first, then "wir kümmern uns umgehend"; if status is `NEEDS_REVIEW`, also ask for the unit.
  - `confirm_unit` (gates `floor_missing`, `floor_ambiguous`, `threshold`, `margin`, `veto_unit`): ask for floor + side (German counting explained in one short clause, e.g. "Erdgeschoss = EG, darüber 1. OG").
  - `confirm_identity` (`identity`): ask for full name of the contract holder / contract number.
  - `confirm_address` (`veto_address`, `no_candidate`): ask for full address and name.
  - `eligibility`: neutral "wir prüfen Ihre Angaben und melden uns" – never reveal contract status.
  - `standard` (`READY_FOR_APPROVAL`): confirm receipt, response target from urgency, ask to send photos if `photos_mentioned` and no attachments.
  - `ask_registered_email` (only via `render_reply(..., variant="ask_registered_email")`): ask the tenant to write again from the email address registered with us.
- **Privacy:** when the status is not `READY_FOR_APPROVAL`, the body must contain **no ERP data** (no contract ids, no unit labels, no names from the ERP). Never mention prior cases.

## 5. Step `task` + staff options
- `OUT_OF_SCOPE` → scope `routing`, assignee = `route_to`, priority `NORMAL`.
- `READY_FOR_APPROVAL` → scope `contract`, title like `Sanitär-Handwerker beauftragen – Wasserschaden Küche (MV-10245)`, assignee `Technik / <trade>`, priority = urgency level, `due_hours` from urgency, `contract_id`, `object_id`; checklist from templates: book contractor (time per urgency), request photos if mentioned, inform caretaker, **for each related prior case:** "Zusammenhang mit '<title>' (<case_id>, erledigt durch <contractor>) prüfen – ggf. Gewährleistung"; NOTFALL: "Notdienst sofort beauftragen". `related_cases` = ids. `requires_approval=True`.
- `NEEDS_REVIEW` → scope `clarification` ("Zuordnung klären: <gate messages>"), checklist: compare candidates, send prepared question to tenant, …; **if urgency is `NOTFALL` and `match.object_id` is known → scope `object`**: building-level actions (Notdienst/Hausmeister to the building) are allowed although the unit is unclear; contract_id stays `None`.
- `staff_options` (only when `match.unknown_sender`): `reply_anyway` (always available), `ask_registered_email` (available if the winner's ERP email is known), `call_tenant` (available **only if a phone number is known** – winner's ERP phone or `extraction.phone`; put the number in `detail`). German labels.

## 6. `actions.py` – the only way to act
- `Approval` (pydantic): `case_id`, `actor`, `action`, `contract_id | None`, `reason | None`, `ts`.
- `execute(case, approval, audit: AuditLog) -> CaseRecord`. Actions: `approve_assignment` (contract-level), `order_contractor` (contract-level), `object_action` (building-level), `approve_reply` (marks the draft approved for copying – **there is no send action**), `choose_staff_option`.
- Contract-level actions are **refused** (`PermissionError`) unless: approval.case_id == case.case_id; status is not `OUT_OF_SCOPE`; `contract_id` is one of the case's candidates; for `order_contractor`, an earlier `approve_assignment` event for the same contract exists in `case.audit`; if status is `NEEDS_REVIEW` or the contract differs from `selected_contract`, a non-empty `reason` is required.
- Every executed action appends an `AuditEvent` to the case **and** a JSON line to `AuditLog` (default `var/audit.jsonl`, path injectable for tests). Mark effects as simulated ("im Prototyp simuliert – kein echter ERP-Schreibzugriff").
- Test: no module in `src/` imports `smtplib`/`email.mime` or has a send function.

## 7. Scenarios runner + CLI
- `load_scenarios(dir="scenarios")`, `run_scenario(sc, provider=None) -> (CaseRecord, list[Check])`. Build the context with `Context.build(provider=…, rule_overrides=sc.rule_overrides, data_overrides=sc.data_overrides, now=<fixed: email.received_at or 2026-11-18T09:00+01:00>)`.
- Check every key present in `expected`: `type`, `category`, `status`, `contract` (= `match.selected_contract`), `winner`, `urgency`, `failed_gates` (**exact set**), `related_case` (in related prior cases), `reply_language`, `warning_contains`, `staff_options_available` (exact set of available codes), `safety_instructions` (non-empty), `task_scope`.
- `main()`: German table (ID, Titel, Status, Vertrag, Dringlichkeit, Gates, ✔/✖), exit code 1 on failure. `--provider` option.
- `cli.py`: `intake process FILE [--provider P]` (FILE = `.txt` body, `.json` InboundEmail or scenario `.yaml`) prints the `CaseRecord` JSON; `intake scenarios`.
- `tests/test_scenarios.py`: parametrised over all files in `scenarios/`, offline provider, every check passes.

## Proof (must pass)
```
uv run pytest
uv run intake-scenarios
```
Do not commit. Keep changes inside the files you own; if the shared contract blocks you, stop and say exactly what is needed.
