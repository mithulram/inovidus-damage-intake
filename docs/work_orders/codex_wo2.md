# Work order WO2 – Codex (builder) · inspected by Claude

Derived from the Codex-approved plan `docs/PLAN.md` (§3, §4, §5.4, §12, §18). Builds on WO1 (already merged).
Shared contract – do **not** modify (report needed changes instead): everything under `src/intake/` that you did not create in WO1 or below, `config/rules.yaml`, `data/*`, `scenarios/*`, `examples/llm_recorded/*`.
Environment: `uv sync` done; **no network** – Groq is never called live in this work order. Run `uv run pytest`.

## Inputs prepared by Claude (verified online 2026-11-18)
- `docs/reference/groq_api.md` – endpoint, model, strict structured-output format, limits.
- `examples/llm_recorded/schema.json` – the strict JSON schema used for the live calls.
- `examples/llm_recorded/system_prompt.txt` – the system prompt used for the live calls.
- `examples/llm_recorded/<scenario>.groq.json` – 5 real responses (`request` + `response`, no key).

## Files you own
| File | What |
|---|---|
| `config/prompts/understanding_system.txt` | system prompt (copy of the recorded one; business-editable) |
| `src/intake/providers/llm_schema.py` | the strict schema (load from / identical to `examples/llm_recorded/schema.json`), `build_user_message(email)`, `parse_llm_content(content: str, provider, model) -> Understanding` |
| `src/intake/providers/groq.py` | `GroqProvider` |
| `src/intake/providers/recorded.py` | `RecordedProvider` |
| `src/intake/store.py` | `CaseStore` (JSON file per case under `var/cases/`, path injectable, idempotent `save`, `get`, `list` newest first) |
| `src/intake/web/__init__.py`, `src/intake/web/app.py` | FastAPI app + `run()` |
| `tests/test_llm_providers.py`, `tests/test_api.py` | tests |
Do **not** create files under `src/intake/web/static/` (Claude builds the UI); mount it only if it exists.

## 1. GroqProvider
- `from_env()`: `GROQ_API_KEY` (required → clear German error if missing), `GROQ_MODEL` (default `openai/gpt-oss-120b`), optional `GROQ_BASE_URL`. Constructor accepts an injectable `httpx.Client` (tests use `httpx.MockTransport`).
- Request exactly as in the reference: `temperature 0`, system prompt from `config/prompts/understanding_system.txt`, user message via `build_user_message`, `response_format` strict json_schema, timeout 30 s.
- Parse `choices[0].message.content` → validate → `Understanding(provider="groq", model=<response model>)`; `Extraction.language` etc. map 1:1; `confidence` clamp to [0,1].
- Robustness: on HTTP 400 / invalid JSON / validation error → retry once; on second failure, on HTTP 429, timeout or network error → **fall back** to `OfflineProvider().understand(...)` with `fallback_used=True`, provider string `"groq→offline"` and a German warning (`"KI-Ausgabe ungültig – Regelmodus verwendet"`, `"KI-Dienst nicht erreichbar – Regelmodus verwendet"`, `"KI-Limit erreicht (429) – Regelmodus verwendet"`). Never log or return the API key.

## 2. RecordedProvider
- Replays `examples/llm_recorded/*.groq.json`: index fixtures by the **user message** text (`request.messages[1].content`); `understand(email)` builds the same user message and looks it up; parse via `parse_llm_content` with `provider="recorded(groq)"`, model from the fixture.
- Unknown email → offline fallback with warning `"Keine Aufzeichnung für diese E-Mail – Regelmodus verwendet"`.

## 3. API (`src/intake/web/app.py`) – one process serves API + UI
Context per request: `Context.build(provider=get_provider(provider or env), rule_overrides, data_overrides)`; when a `scenario_id` is given, take overrides from that scenario file.
- `GET /api/health` → `{status, provider_default, rules_version}`
- `GET /api/scenarios` → id, title, description, email, expected, has_overrides (file order)
- `GET /api/rules` → `{version, yaml: <raw text>, parsed}`
- `POST /api/process` body `{email: InboundEmail, provider?: str, scenario_id?: str, store?: bool=false}` → full `CaseRecord` (all steps via `pipeline.process`). Read-only unless `store=true`.
- `POST /api/steps/{name}` body `{case?: CaseRecord, email?: InboundEmail, provider?, scenario_id?}` → `CaseRecord`. For `understand` without `case`: create via `pipeline.new_case(email)`. Uses `pipeline.run_step` – **the same functions** as `/api/process`. Unknown step → 404 with allowed names.
- `POST /api/cases` body `CaseRecord` → stores it (review inbox, idempotent by `case_id`) and appends audit event `in Prüfliste übernommen`. This is where n8n ends.
- `GET /api/cases` (summary list: case_id, received_at, subject, status, urgency, winner, selected_contract, failed_gates) · `GET /api/cases/{id}`
- `GET /api/cases/{id}/reply?variant=…` → `render_reply` (e.g. `ask_registered_email`)
- `POST /api/approve` body `{case_id, actor, action, contract_id?, reason?, option?}` → loads the stored case, calls `actions.execute`, saves, returns the case. `PermissionError` → HTTP 403 with the German message. **No other endpoint changes contract state. No endpoint sends anything.**
- `GET /api/audit` → last 200 audit-log lines.
- `GET /` → `static/index.html` if present, else a short JSON hint. CORS off (same origin). Bind `127.0.0.1`, port `INTAKE_PORT` (default 8000). `run()` starts uvicorn.

## 3b. Fixes from Claude's WO1 inspection (you own these two files for this work order)
- **F1 (medium) `src/intake/steps/prior_cases.py`:** when Stage A did not single out one contract (`threshold` or `margin` in `failed_gates`), show prior cases of **all non-vetoed candidates** (max 3), not only `winner` (which is an arbitrary tie-break there). Keep: `selected_contract` → only that; otherwise (e.g. identity/eligibility/floor flags with a clear winner) → `winner`. Add a test with S2 (both MV-10245 and MV-10487 histories listed).
- **F2 (low) `src/intake/steps/task.py` + `config/templates.yaml`:** object-scope / clarification titles show the building's address (e.g. "Musterstraße 12") instead of the internal `object_id`; keep `object_id` in the field. Add/adjust a test.

## 4. Tests
- Providers (MockTransport): valid response → Understanding; malformed then valid → success after retry; malformed twice → offline fallback + warning; 429 → fallback; timeout → fallback; key never appears in any warning/exception text; every recorded fixture parses; RecordedProvider on S01 → full pipeline selects MV-10245.
- **Scenario suite with RecordedProvider** for the 5 recorded scenarios: all expectations hold (same as offline).
- API (`TestClient`, temp store/audit paths): **parity** – for every scenario, chaining `/api/steps/{understand,match,prior_cases,urgency,draft,task}` equals `/api/process` (compare `model_dump` excluding `audit`, `processed_at`, `received_at`); `/api/process` does not write the store; `/api/cases` round-trip; `/api/approve` refuses contract actions without approval rules (403) and accepts a valid one; no route path contains "send".

## Proof (must pass)
```
uv run pytest
uv run intake-scenarios
LLM_PROVIDER=recorded uv run intake process scenarios/S01_original.yaml
```
Do not commit.
