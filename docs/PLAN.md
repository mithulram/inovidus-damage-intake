# PLAN – AI damage-report intake (Inovidus Praxisaufgabe)

Status: **Codex-reviewed – awaiting Mithul's approval. No implementation code before "approved".**
Context: `TASK.md`, `CLAUDE.md`, `docs/00_UNDERSTANDING.md`.

---

## 1. Goal and acceptance criteria

**Goal:** A small, runnable prototype that turns a tenant email into a checked, explainable case record: category, extracted facts, ERP match with reasons, related prior cases, urgency, JSON, a reply **draft** (never sent) and an internal follow-up task. Unclear cases never act on a contract.

**Acceptance criteria (observable):**
- A1 – `uv run pytest` is green, fully offline, no API key.
- A2 – The original email → `selected_contract = MV-10245`, status `READY_FOR_APPROVAL`, urgency `DRINGEND`, related closed case "Rohrverstopfung Küche" flagged, MV-10487 shown as rejected with reason "Etage widerspricht (3. OG ≠ 2. OG)".
- A3 – All 7+ scenarios in §10 produce their expected outcome (`uv run python -m intake.scenarios` prints a pass/fail table).
- A4 – Every candidate and every decision has a German, human-readable reason.
- A5 – No code path sends email. No contract-level action is executed without a human approval event in the audit log – enforced in one shared action handler used by UI and API, and covered by a test (call without approval → refused).
- A6 – Changing a rule (threshold, weight, urgency keyword, response time) = editing one line in `config/rules.yaml`; adding a scenario = adding one YAML file.
- A7 – The custom web UI (served by the same FastAPI app) starts with one command, has German labels, shows the reasoning step by step, and passes the design checks in §11.

---

## 2. Prioritisation of the 9 steps

| # | Step | Priority | Reason (one line) |
|---|---|---|---|
| 4 | ERP matching (tenant/object/unit) | **Must** | The explicit test: two active contracts, only the unit decides; a wrong match = wrong action. |
| 7 | Structured JSON | **Must** | Interface to ERP/workflow; makes every decision traceable and testable. |
| 3 | Extraction | **Must** | Matching and urgency need address, floor, side, room, facts. |
| 2 | Classification | **Must** | Routes damage vs. non-damage; picks craftsman trade. |
| 6 | Urgency | **Must** | Water is running now → wrong priority costs real money (consequential damage). |
| 8 | Reply draft (never auto-sent) | **Must** | Explicitly required; shows the human-in-the-loop boundary. |
| 5 | Prior cases | **Should** | Data is given on purpose (recurrence hint); cheap lookup, high value for the craftsman. |
| 9 | Internal follow-up task | **Should** | Turns the result into work; simple template per category/urgency. |
| 1 | Read message | **Should (minimal)** | For the prototype: paste/file/scenario input. Real mailbox ingestion (IMAP/Graph) is production work. |

Explicitly **not** in the core: live mailbox connection, real ERP API, attachment/photo analysis (OCR/vision), multi-message threads, auth/roles.

---

## 3. Tech decision

### Options compared

| Option | Strengths | Weaknesses | Fit here |
|---|---|---|---|
| **Python core + Pydantic + FastAPI + custom web UI** | Fully testable (pytest), deterministic matching is easy to write and explain, schema validation, runs offline, one repo = full source; full design control; the same API serves UI and n8n | More UI work than Streamlit; needs Python (uv) on reviewer's machine | **Chosen** |
| Python core + Streamlit UI | Fastest UI | Every Streamlit app looks alike ("AI demo" look); little design control | Rejected for the UI (Mithul: must look unique, no "AI slop") |
| n8n only | Visual, business-friendly, self-hostable (EU), common in DACH property-management automation | Matching/scoring logic in Code nodes is hard to unit-test and to version; reviewer must run n8n | Good **orchestration shell**, not the logic home |
| LangChain / LangGraph | Agent graphs, retries, many providers | Heavy for a linear pipeline; abstraction hides the simple logic we must explain | Overkill; graph adds nothing for 9 linear steps |
| Dify | Fast LLM app UI, RAG built in | Logic in platform config, weak for deterministic scoring + tests; needs hosting | Better for the *knowledge assistant* follow-up |

### Decision
- **Python 3.12 core pipeline**: each of the 9 steps is a plain, swappable function with Pydantic in/out models. Libraries: `pydantic` v2, `rapidfuzz` (fuzzy name match), `pyyaml` (rules), `fastapi` + `uvicorn` (API + UI server), `pytest`. Frontend: hand-written HTML/CSS + small vanilla JS (no build step, no framework), served as static files by FastAPI. Managed with **uv**, developed on Python 3.12, `requires-python >=3.11`. Inovidus does not prescribe a version; 3.12 is the most widely installed mature release, and uv downloads it automatically, so a reviewer needs no matching system Python (this Mac has 3.14.7).
- **Custom "Sachbearbeiter" web UI** on top of the same core: one FastAPI app (`uv run intake-ui`) serves the page and the JSON API (`GET /api/scenarios`, `POST /api/process`, `POST /api/approve`, `GET /api/rules`, `GET /api/audit`). One process, one command.
- **n8n workflow = the visible process** (core showcase, see §18): one n8n node per business step, each calling a Python step endpoint; sticky notes explain each step in German. n8n only **routes**; Python **decides**. The workflow **never** writes to a contract: it ends by storing a proposal in the review inbox (`POST /api/cases`); contract-level actions go only through `POST /api/approve` (see §5.4), which needs a human approval event. This mirrors how Inovidus integrates systems: tested logic as a service, n8n as visible glue. Run in a **local n8n** (`npx n8n`; Node 22 via nvm if Node 24 is rejected – verify at build). Only claimed as "tested" after real executions.
- Why this maps to Inovidus: their focus is ERP integration + AI agents for real-estate clients. A clean service boundary (`ERPConnector` interface, JSON contract) is what plugs into ERP/DMS/CAFM; the business sees the n8n flow, the team tests the core.

---

## 4. LLM strategy (free only)

**One interface**: `LLMProvider.understand(email) -> Understanding` (classification + extraction + urgency hint, one call, structured output).

Implementations:
- `OfflineProvider` (**default**, no key): regex + keyword dictionaries + normalisation tables from `config/rules.yaml`. Deterministic, used in all tests.
- `GroqProvider` (**primary live provider**, free tier, JSON / structured output; Mithul has a key). `GeminiProvider` (free tier) as optional second provider, only built if time allows. **No local LLM** (Mithul's decision). Exact SDK calls and model names are **verified against current docs at build time**, not assumed.
- `RecordedProvider`: replays a stored real **Groq** response from `examples/llm_recorded/` → lets a reviewer see/test LLM-mode output without a key.

Robustness: LLM output → Pydantic validation → on failure one retry → then fall back to `OfflineProvider` and add a warning "KI-Ausgabe ungültig, Regelmodus verwendet". Provider + model are recorded in the JSON.

**Deterministic vs. LLM – where and why:**

| Part | Mode | Why |
|---|---|---|
| Classification, extraction | LLM (offline rules as fallback) | Free text, many phrasings, other languages → LLM is strong; rules cover the demo. |
| Urgency | Rules **floor** + LLM **hint**, stricter wins | Safety: an LLM may under-rate; rules guarantee minimum; LLM catches phrasings rules miss. |
| ERP matching, scoring, gating, status | **Deterministic only** | Decides which contract gets an action → must be reproducible, auditable, explainable. LLM never picks the contract. |
| Prior-case relation | Deterministic (same unit + related category/room) | Simple, explainable. |
| Reply draft | **Templates** (de/en) filled from validated fields | A reply can contain promises (time frames) → wording must be business-approved; no hallucinated facts. LLM rephrasing = possible extra, off by default. |
| Internal task | Templates per category × urgency | Same reason; easy to change live. |

**Single source of truth for rules:** `config/rules.yaml` owns all business rules (incl. threshold). `.env` only holds provider choice and secrets. `MATCH_CONFIDENCE_THRESHOLD` is removed from `.env.example` and moved to YAML (documented).

**DSGVO note:** free tiers (Groq, Gemini) are non-EU and may use inputs for training → the demo uses **synthetic data only**. Production: EU-hosted model (e.g. Azure OpenAI EU, Mistral EU, or self-hosted via Ollama/vLLM) + DPA (AVV), data minimisation (send only email text, never the ERP data, to the LLM).

---

## 5. Uncertainty design (core)

### 5.1 Normalisation (config tables)
- Street: `str.`/`str`/`strasse`/`straße` → `straße`; case/whitespace/umlaut folding (`ss`↔`ß`, `ae`↔`ä`).
- Floor – **German counting** (Mithul's decision): `EG`/`Erdgeschoss`/`Parterre`/`ground floor` → 0; `erste Etage`/`1. Etage`/`1. OG`/`1. Stock`/`erster Stock` → 1; `zweite Etage`/`2. OG`/`2. Stock` → 2; … `DG`/`Dachgeschoss`, `UG`/`Keller` → own tokens. Unclear terms (`Hochparterre`, `Souterrain`, "oben", "ganz oben") → no floor value + flag → review.
- Side: `links`/`li.`/`li`/`l.`/`left` → `L`; `rechts`/`re.`/`r.`/`right` → `R`; `Mitte` → `M`.
- English ordinal floors ("2nd floor") are ambiguous (UK/EU counting = 2. OG, US counting = 1. OG). **Strict by default** (Mithul's decision): config `normalize.english_floor_counting: ask` – the floor counts as the German number, but a flag "Stockwerk-Zählweise unklar" forces `NEEDS_REVIEW` and the reply asks the tenant to confirm. Alternative `european` (treat as 2. OG, note only) is a one-line live switch.
- Rule of thumb: a floor that is missing, unclear, or contradicts every contract → never guessed; `NEEDS_REVIEW` and the reply asks the tenant.

### 5.2 Candidate search and signals
Candidates = **all** ERP contracts (active **and** inactive) where address matches **or** name similarity ≥ 0.80. Extraction keeps two names apart: `tenant_name` (the contract holder the email refers to) and `sender_name` (signature/sender). The name signal uses `tenant_name` (falls back to `sender_name` if no holder is named); the identity flag fires when `sender_name` ≠ contract holder. Each candidate gets signals with a result `match | mismatch | missing` and points (weights in YAML):

| Signal | Weight | Match rule |
|---|---|---|
| Name | 0.30 | rapidfuzz `token_sort_ratio` ≥ 92 → full; 80–91 → half + flag "Name weicht ab" |
| Address (street + no.) | 0.30 | normalised equal |
| Floor | 0.20 | normalised equal |
| Side | 0.10 | normalised equal |
| Sender contact (email/phone in ERP) | 0.10 | exact equal |

`missing` gives 0 points but is **not** a contradiction. A sender address that is present but **not in the ERP** counts as `missing` (tenants often write from other addresses) and adds a visible warning "Nicht von der registrierten E-Mail-Adresse" with three staff options (§5.4); whether this alone forces review is a config switch (`match.unknown_sender_forces_review`, default `false` – business decision, see §16). `mismatch` on **address (street or house no.), floor or side is a veto** – only when the email explicitly states that value. Vetoes do not depend on the configurable threshold, so lowering the threshold can never make a different building or unit "ready".

### 5.3 Two stages, four gates → status
**Stage A – which contract/unit does the email describe?** (active and inactive contracts compete together)
1. **Vetoes:** explicit contradiction of address, floor or side → candidate out (still shown with reason).
2. **Threshold:** best non-vetoed score ≥ `match.threshold` (default 0.85).
3. **Margin:** best − second-best non-vetoed score ≥ `match.min_margin` (default 0.15). Inactive contracts count here, so missing unit info can never hide an ambiguity between an inactive and an active unit.

**Stage B – may we act on it?**
4. **Eligibility:** the Stage-A winner's contract must be **active**. If the winner is inactive → `NEEDS_REVIEW` ("Einheit erkannt, Vertrag inaktiv – Mieterwechsel/Leerstand prüfen"). The system **never falls back** to the next active contract.

Plus **flags** that force review, independent of the threshold: name only partly matches or sender ≠ contract holder (`identity`); **floor missing or unclear German term** (`floor_missing`); English floor counting unclear (`floor_ambiguous`, while `ask` is set); unknown sender address (`identity`, only if switched on).

All gates pass → `READY_FOR_APPROVAL`. Any gate fails → `NEEDS_REVIEW` with the failing gate as reason. Not a damage report → `OUT_OF_SCOPE` (routed to the right team, no damage task).

Worked example (original email, no sender address): MV-10245 = name 0.30 + address 0.30 + floor 0.20 + side 0.10 = **0.90** ✔; MV-10487 = **veto** (3. OG ≠ 2. OG, rechts ≠ links). Margin vs. no valid competitor ✔; MV-10245 active ✔ → `READY_FOR_APPROVAL`.

### 5.4 Status model (no status acts by itself)
| Code (JSON) | UI label (German) | Meaning |
|---|---|---|
| `READY_FOR_APPROVAL` | "Zuordnung eindeutig – bitte freigeben" | All gates passed; pre-filled, a human clicks "Freigeben". |
| `NEEDS_REVIEW` | "Prüfung nötig" | At least one gate failed; human picks the contract (reason required) or asks the tenant. |
| `OUT_OF_SCOPE` | "Kein Schadensfall – weiterleiten" | e.g. rent question → routed to Mietbuchhaltung. |

- **Contract-level actions** (create case on MV-…, order craftsman for the unit) only after an approval event (who, when, which contract, case_id) in the audit log. This is enforced in **one shared action handler** (`actions.execute(case, action, approval)`), used by the UI and by `POST /api/approve`; it refuses any contract-level action without a matching approval event. `/api/process` and the n8n flow only produce proposals.
- **Unknown sender address** (Mithul's decision, Q5): the case is not blocked, but the UI shows a clear warning "Nicht von der registrierten E-Mail-Adresse" and the staff member picks one of three options, each recorded in the audit log: (a) approve and reply anyway, (b) use the prepared reply asking the tenant to write again from the registered address, (c) call the tenant – offered **only when a phone number is known** (from the ERP or the email). The ERP seed gets **synthetic** contact fields (email, phone) for this, clearly marked as added test data (the task's ERP rows have none).
- **Object-level actions** are allowed even in `NEEDS_REVIEW` when the address is certain (e.g. inform Hausmeister for Musterstraße 12) – the building is known even if the unit is not.
- **Urgency is independent of matching:** a `NOTFALL` with unclear unit is `NEEDS_REVIEW` **and** top of the queue with an emergency banner; it is never held back.

### 5.5 Reply privacy
If the match is not clear, the draft asks the tenant to confirm floor/side and contact data, and **never lists ERP data** (sender could be someone else). Prior cases never appear in the tenant reply.

---

## 6. Urgency logic

Levels, response times and trigger rules live in `config/rules.yaml`:

| Level | Meaning | Target response (configurable) | Example triggers (rule floor) |
|---|---|---|---|
| `NOTFALL` | Danger to people/building | Immediate, Notdienst ≤ 2 h | Gasgeruch; Rohrbruch / Wasser steht / läuft durch Decke; Wasser an Elektrik; Stromausfall Wohnung; kein Heizen in Heizperiode (Okt–Apr) |
| `DRINGEND` | Ongoing damage, gets worse | Craftsman within 24 h | Wasser läuft/tritt aus (active leak); Schimmel nach Wasser; kein Warmwasser |
| `NORMAL` | No progressing damage | Within 5 working days | Tropfender Hahn (no damage), cosmetic damage |

- Final level = max(rule floor, LLM hint). Each trigger is listed as reason.
- The tenant's word "dringend" alone is a recorded signal, not a trigger (facts decide). Original email: "läuft Wasser … seit gestern" + "aufgequollen" → `DRINGEND`.
- `NOTFALL` drafts include safety instructions (Wasser-Haupthahn zudrehen; bei Gasgeruch: kein Licht/Schalter, Gebäude verlassen, Notruf 112 / Gas-Notdienst) and the UI shows "Sofort telefonisch reagieren". Honest limitation: since nothing is auto-sent, emergency speed depends on a human; production needs a 24/7 hotline or an approved generic auto-acknowledgment (policy decision for the client, flagged for the interview).

---

## 7. Prior cases
- Lookup by contract and unit in `data/cases.json` (open and closed).
- **Related** if same unit and (same room or related category; relation table in YAML, e.g. `Rohrverstopfung` ↔ `Wasseraustritt`/`Sanitär`).
- Effect: flagged in JSON + UI ("Möglicher Zusammenhang mit abgeschlossenem Vorgang 'Rohrverstopfung Küche'"), added to the internal task ("Handwerker soll Zusammenhang prüfen; ggf. Gewährleistung des damaligen Auftrags prüfen"). **Not** in the tenant reply.
- An **open** case on the same unit + category → flag "mögliche Doppelmeldung".
- When `NEEDS_REVIEW`, prior cases of all candidates are shown internally to help the reviewer.

---

## 8. Output JSON schema and internal task

**Keys in English, values/reasons in German.** Why: English keys are the norm for APIs/ERP integration and make LLM structured output more reliable; German reason texts are for the Sachbearbeiter and the UI. (Decision documented; trivially switchable via Pydantic aliases.)

```jsonc
{
  "case_id": "SM-2026-0001",
  "received_at": "...", "processed_at": "...",
  "processing": { "provider": "offline", "model": null, "rules_version": "sha256:…" },
  "input": { "subject": "...", "body": "...", "sender": null, "language": "de" },
  "classification": { "type": "SCHADENMELDUNG", "category": "Wasserschaden", "trade": "Sanitär", "confidence": 0.9, "reason": "…" },
  "extraction": { "tenant_name": "Max Mustermann", "sender_name": "Max Mustermann", "street": "Musterstraße", "house_no": "12", "floor": 2, "side": "L", "room": "Küche",
                  "description": "…", "since": "gestern", "photos_mentioned": true, "attachments_present": false },
  "match": { "status": "READY_FOR_APPROVAL", "selected_contract": "MV-10245", "score": 0.90, "margin": 0.90,
             "candidates": [ { "contract_id": "MV-10245", "score": 0.90, "vetoes": [], "signals": [ { "name": "floor", "result": "match", "points": 0.20, "reason": "zweite Etage = 2. OG" } ] },
                             { "contract_id": "MV-10487", "score": 0.60, "vetoes": ["Etage widerspricht: 3. OG ≠ 2. OG"], "signals": [ … ] } ],
             "reason": "…" },
  "prior_cases": [ { "case_id": "VG-…", "title": "Rohrverstopfung Küche", "state": "closed", "related": true, "reason": "gleiche Einheit, gleicher Raum, verwandte Kategorie" } ],
  "urgency": { "level": "DRINGEND", "rule_level": "DRINGEND", "llm_level": null, "triggers": ["Wasser läuft aus", "Schaden schreitet fort"], "response_target": "24 h" },
  "status": "READY_FOR_APPROVAL",
  "reply_draft": { "language": "de", "subject": "…", "body": "…", "auto_send": false },
  "internal_task": { "title": "Sanitär-Handwerker beauftragen – Wasseraustritt Küche, MV-10245", "assignee_role": "Technik / Sanitär",
                     "priority": "DRINGEND", "due": "+24h", "checklist": ["Handwerker beauftragen, Termin heute/morgen", "Fotos beim Mieter anfordern",
                     "Hausmeister informieren (Wasser absperren falls nötig)", "Zusammenhang mit 'Rohrverstopfung Küche' prüfen"],
                     "requires_approval": true },
  "warnings": [], "audit": [ { "ts": "…", "actor": "system|<user>", "event": "…" } ]
}
```
In `NEEDS_REVIEW`, `selected_contract` is `null` and the internal task becomes "Zuordnung klären" (+ object-level actions if the address is certain).

---

## 9. Project structure

```
config/rules.yaml        # ALL business rules (weights, threshold, margin, normalisation, urgency, response times, templates)
data/erp_contracts.json  # seed ERP (MV-10245, MV-10487, + 2–3 distractors)
data/cases.json          # prior cases (closed "Rohrverstopfung Küche" on MV-10245)
scenarios/*.yaml         # input email + optional data overrides + expected outcome
src/intake/              # pipeline.py, models.py, normalize.py, matching.py, urgency.py, prior_cases.py, drafting.py, tasks.py,
                         # providers/{base,offline,groq,gemini,recorded}.py, erp.py (ERPConnector interface + JSON impl), scenarios.py, cli.py
src/intake/web/          # FastAPI app (API + static UI) – app.py, static/{index.html, styles.css, app.js}
workflows/                # n8n export (exported from a running n8n, not hand-written) + screenshots
tests/                   # unit + scenario tests
examples/                # sample outputs (JSON, reply, task) + llm_recorded/
deliverables/            # German deliverables (README, Architektur, Einschätzung, …)
docs/                    # plan, understanding, timelog, AI usage, explainer
```

---

## 10. Scenario suite (runnable, live-changeable)

Each scenario states the expected **status, contract, urgency and the exact set of failed gates** (`threshold`, `margin`, `veto_address`, `veto_unit`, `eligibility`, `identity`, `floor_missing`, `floor_ambiguous`, `out_of_scope`; `none` when all pass). Tests assert that set exactly, so a scenario cannot pass "for the wrong reason". The column below names the gate under test; where several fail, all are listed. Where a gate is under test, the input is built so that **only that gate** can stop it (e.g. sender contact matches, so the threshold is cleared).

| # | Scenario | Expected status / contract / urgency | Failed gates |
|---|---|---|---|
| S1 | Original email (no sender address, as in the task) | `READY_FOR_APPROVAL`, MV-10245, `DRINGEND`; related closed case flagged; MV-10487 vetoed (floor/side) | `none` |
| S2 | Same email without "zweite Etage links" | `NEEDS_REVIEW`, no contract (0.60/0.60); reply asks tenant to confirm floor/side; task "Zuordnung klären"; `DRINGEND` | `threshold`, `margin`, `floor_missing` |
| S3 | MV-10245 set inactive (data override) | `NEEDS_REVIEW`; Stage A identifies MV-10245 (0.90), MV-10487 vetoed → **no** fallback; reason "Einheit erkannt, Vertrag inaktiv – Mieterwechsel/Leerstand prüfen" | `eligibility` |
| S3b | MV-10245 inactive + extra **active** contract for Max at 2. OG rechts (override); Max's email stored on both; email sent from that address, says "2. Etage" without side | `NEEDS_REVIEW`; both 0.90 (above threshold), margin 0 – inactive unit stays in the ambiguity check | `margin` |
| S4a | Name spelled differently (exact string chosen at build so rapidfuzz lands in the 80–91 band), 2. OG li., sent from Max's ERP contact address | `NEEDS_REVIEW`, MV-10245 suggested; score 0.15+0.30+0.20+0.10+0.10 = 0.85 (clears threshold), stopped by "Name weicht ab" | `identity` |
| S4b | Partner reports for the tenant: "… Wohnung von Max Mustermann, Musterstr. 12, 2. OG li. … Grüße, Erika Muster" (unknown address) | `NEEDS_REVIEW`, MV-10245 suggested; named holder gives name 0.30 → 0.90 (clears threshold), stopped because sender (Erika Muster) ≠ contract holder | `identity` |
| S4c | Correct name + unit, sent from an email address not in the ERP | `READY_FOR_APPROVAL`, MV-10245, warning "Nicht von der registrierten E-Mail-Adresse" + the three staff options (§5.4) (with switch on → `NEEDS_REVIEW`, gate `identity`) | `none` |
| S5a | Burst pipe, water through ceiling, Max Mustermann, Musterstr. 12, 2. OG li. | `NOTFALL`, `READY_FOR_APPROVAL`, MV-10245, emergency instructions in draft, emergency banner | `none` |
| S5b | Gas smell, unit unclear | `NOTFALL` + `NEEDS_REVIEW`; object-level action allowed (Gas-Notdienst/Hausmeister for the building) | `threshold`, `margin`, `floor_missing` |
| S6 | Rent question | `OUT_OF_SCOPE`, routed to Mietbuchhaltung, no damage task | `out_of_scope` |
| S7 | English email, "2nd floor left" | `NEEDS_REVIEW` (default `ask`), MV-10245 suggested (0.90 – clears threshold, so only the floor flag stops it), English reply draft asking to confirm the floor; with rule override `european` → `READY_FOR_APPROVAL`, gate `none` | `floor_ambiguous` |
| S8 | Threshold lowered to 0.65 (rule override); sender contact matches MV-10245; email names "Musterstraße **14**", 2. OG li. | `NEEDS_REVIEW`: without the veto MV-10245 would score 0.70 ≥ 0.65 – only the address veto stops it | `veto_address` |
| S9 | Threshold lowered to 0.65 (rule override); "Max Mustermann, Musterstraße 12, links" – **no floor**, no sender address | `NEEDS_REVIEW`: MV-10245 scores 0.70 ≥ 0.65 and MV-10487 is vetoed (rechts), so only the missing-floor flag stops it; reply asks for the floor | `floor_missing` |

Run: `uv run python -m intake.scenarios` (table) and `uv run pytest` (each scenario is a test). The UI lists scenarios and shows expected vs. actual. New scenario = new YAML file; **data overrides** (contract inactive, extra contract) and **rule overrides** (e.g. threshold) per scenario, without editing seed data or the main rules.

---

## 11. UI design (custom web page, German)
- Design skills (Mithul's request – unique look, no generic "AI demo" style), installed globally in `~/.claude/skills` from their original repos: **Impeccable** (pbakaus/impeccable @d41d986) and **UI/UX Pro Max** (nextlevelbuilder @ed766d3) are primary (they fit app/dashboard UI); **Taste** (Leonxlnx @f6b7657) targets marketing sites, so only its anti-slop copy and consistency rules are used; Anthropic's **frontend-design**; bundled scripts are read before running (Python with `-I`); fonts self-hosted with checked licenses; `design:accessibility-review` (contrast, keyboard, readable on a shared screen) and `design:ux-copy` (German labels). Design direction is set at build start following these skills; the design check runs the skills' own review/anti-pattern commands where available.
- Priority is the **flow**: a non-programmer must see in one screen how an email becomes a decision.
- Layout: left = Eingang (scenario list + "eigene E-Mail einfügen"); main = 5 steps as connected cards: **1 Eingang → 2 Erkennung → 3 Zuordnung → 4 Dringlichkeit → 5 Antwort & Aufgabe**.
- Zuordnung card: traffic light (grün = eindeutig, gelb = Prüfung nötig, grau = kein Schadensfall), candidate table with per-signal ✔/✖/– and reason, vetoes in red.
- Actions: "Zuordnung bestätigen" / manual pick with mandatory reason; "Entwurf freigeben & kopieren" (copies text, records audit event; **no send button exists**). Audit log stored as local JSONL.
- View "Regeln" shows `rules.yaml` in readable form (for the live interview); view "Protokoll" shows the audit log.
- Large type for screen sharing; full JSON visible on demand; works without internet (no CDN-dependent assets).

---

## 12. Tests
- Unit: normalisation (Musterstr.↔Musterstraße, zweite Etage↔2. OG, li.↔links, English forms), each signal, vetoes (address/floor/side), threshold, margin incl. inactive candidates, eligibility (no fallback), action handler refuses without approval, urgency floor vs. hint (stricter wins), prior-case relation, schema validation, "no send" guarantee (no SMTP import anywhere; draft has `auto_send: false`).
- Scenario tests: all §10 scenarios, offline, deterministic.
- LLM mode: `RecordedProvider` fixture test (parsing + fallback on invalid JSON); live provider smoke test skipped when no key.
- Proof commands: `uv run pytest`; `uv run python -m intake.scenarios`; `uv run python -m intake.cli examples/email_original.txt > examples/output_original.json`; `uv run intake-ui` + screenshots of every step (S1, S2, S5b); n8n: `curl` the webhook with S1, S2, S5b → cases appear in the UI inbox with the expected status; screenshots of the canvas and of the execution view (data per node).

---

## 13. Scalability & production path (short)
- Ingestion: mailbox (Graph/IMAP) → queue (e.g. Redis/SQS/Service Bus); idempotency by Message-ID; retries + dead-letter.
- ERP: real connector behind `ERPConnector` (read-only for matching; writes only after approval), cached tenant index.
- DSGVO: EU hosting, AVV/DPA with LLM provider, data minimisation, retention + deletion, access roles, PII masked in logs.
- Ops: structured logs, metrics (auto-ready rate, override rate = how often humans change the suggestion, time-to-first-response, emergency SLA), alerting.
- Quality: evaluation set of real (anonymised) emails with labels; regression test on every rule change; threshold tuned on precision (wrong match must be ~0).
- Attachments: photo/vision analysis later; virus scan.
- Cost: offline rules ≈ 0; one LLM call per email (~1–2k tokens) ≈ fractions of a cent on paid EU tiers; measure per message.

## 14. Reuse for an internal knowledge assistant
| Component | Reuse |
|---|---|
| Ingestion + normalisation | Document ingestion (mail, PDF, DMS) |
| Provider interface + structured output + Pydantic validation | Same, for answers with citations |
| ERP connector / case history lookup | Retrieval sources (RAG) next to documents |
| Signal scoring + confidence gating + `NEEDS_REVIEW` | "Answer only with sources; otherwise say 'unsicher' and route to an expert" |
| Review UI + audit log | Feedback loop, answer approval, traceability |
| Rules config + scenario suite | Eval set for RAG answers, regression tests |

---

## 15. Time plan and honesty
- **Core (spirit of 90 min):** models + normalisation + matching/gating + urgency + prior cases + JSON + template reply + task + offline provider + scenario tests + CLI.
- **Extras (logged separately, labelled "Zusatz" in the deliverables):** UI design polish, live LLM providers, n8n showcase, deliverable docs, explainer/PDF, review loops. The README leads with the prioritisation so the scope never hides the 90-minute brief.
- `deliverables/` reports **core time and total time separately**, from `docs/TIMELOG.md`.
- Work split: see §18.

## 16. Decisions from Mithul (18 Nov 2026) and open points
- Q1 ✔ UI: custom web page instead of Streamlit (Mithul: unique, no "AI slop", flow first). Skills: Impeccable + Taste (installed at build), frontend-design, accessibility-review, ux-copy.
- Q2 ✔ LLM: **Groq** free tier (Mithul's key, copied into this project's `.env` only after his OK). No local LLM. Gemini optional.
- Q3 ✔ n8n: install and run locally via `npx n8n`; export tested for real.
- Q4 ✔ Python: Inovidus prescribes none → 3.12 via uv (reason in §3).
- Q6 ✔ Floors: German counting (EG = ground floor, 1. OG = first floor up). Strict: English ordinals and unclear floor terms → review and ask the tenant (`ask` default); `european` is a live switch.
- Q5 ✔ Unknown sender address: staff member decides, with a visible warning and three options (reply anyway / ask tenant to write from registered address / call) – see §5.4. Switch `match.unknown_sender_forces_review` (default `false`) remains for the interview.

## 18. Build revision (Mithul's go-ahead, 18 Nov 2026)

**n8n design rules**
- **Python decides, n8n routes.** Switch/IF nodes read only `status` and `urgency.level` from API responses – never thresholds or keywords. Changing a rule stays a one-line edit in `rules.yaml`.
- **One node per step**, each `POST /api/steps/{understand|match|prior_cases|urgency|draft|task}` with the accumulated case JSON. `/api/process` composes **the same functions in the same order**. **Parity test:** for every scenario, chaining the step endpoints equals `/api/process` (ignoring ids/timestamps).
- **LLM call stays in Python** (`understand`): offline mode, validation and fallback keep working; the Groq key never appears in the n8n export.
- Trigger: **Webhook "E-Mail eingegangen"** for the demo + a **disabled IMAP trigger** showing the production swap. End: `POST /api/cases` (review inbox in the UI). A NOTFALL branch marks the case "sofort" (and shows where a phone/SMS alert would go in production – disabled node).
- No node ever calls `/api/approve`. HTTP Request nodes only (no Execute Command).
- Built in a running n8n, then exported (`n8n export:workflow`) and committed. Local n8n owner login = generated test credentials in a gitignored file.

**Build split (Claude + Codex, both visible)**
- Claude first: scaffold, `pyproject.toml`, `uv sync`, Pydantic models, `rules.yaml` schema, scenario format, step-function signatures → committed as the shared contract.
- Codex (via the claudex runner, `builder=codex`, explicit file ownership, never parallel on the same files): providers (offline/Groq/recorded), urgency, prior cases, drafting, tasks, action handler + audit, FastAPI app + step endpoints + case store, CLI, scenario runner, their tests.
- Claude: normalisation, matching + gating, pipeline composition, scenarios, UI, n8n workflow, deliverables.
- Every module inspected by the other provider in a fresh session, scored, looped to 10/10. Authorship in `AI_USAGE.md` and commit bodies ("Implemented by Codex, inspected by Claude") – no Co-Authored-By trailer.

**Repository and privacy**
- Git from the first commit with a `.gitignore` that keeps personal/interview material out: `CLAUDE.md`, `TASK.md`, `KICKOFF_PROMPT.md`, `private/` (explainer, interview prep, draft email to Sascha Wolf). Mithul can add any of them later; removing from history is not possible.
- GitHub repo created **private**; public/invites only on Mithul's word. Before every push: secrets grep (`gsk_`, `.env`) over tree and history; recorded Groq responses contain only the response body.

**Groq:** key created in Mithul's browser (Dia, after confirming the connected browser), written straight into `.env`, never echoed. **Before the Codex handoff, Claude (network-enabled host)** verifies the current Groq docs and writes `docs/reference/groq_api.md` (model id, endpoint/SDK version, structured-output request and response format, rate limits, short doc excerpts with links), installs the chosen client dependency via `uv sync`, and makes one live call whose response body is saved as the `RecordedProvider` fixture. Codex builds `GroqProvider` offline against that reference + fixture; live calls and real-response capture stay with the host.

## 17. Review protocol
Reviewer (Codex): give verdict + findings, and state **"Score: X/10"** in the summary. Loop until 10/10; minor/optional scope additions are flagged to Mithul rather than added. Log: `docs/PLAN-REVIEW-LOG.md`.

## 19. Additions (Mithul, 19 Nov 2026)

**Hosting (free, always reachable link):** Oracle Cloud Free Tier sign-up was blocked by Oracle's fraud check (generic "error occurred while creating your account", twice). Decision: host on **Render** (free, no card, Mithul signs in with GitHub himself).
- Service 1: the existing FastAPI app (UI + API), Python 3.12 via uv, offline/recorded provider only (no Groq key on the host unless Mithul decides otherwise), synthetic data only.
- Service 2: n8n 2.48.5 (Docker image) that imports and publishes `workflows/n8n_schadenmeldung.json` on every start (Render free has no persistent disk); its `api_url` points to service 1.
- Known limits: services sleep when idle (~30–60 s wake-up), demo state resets on restart, n8n on 512 MB may be slow – fallback: host only the app, keep n8n as export + screenshots.
- Links become public only after Mithul's explicit OK.

**Bilingual DE/EN:**
- UI: language switch in the header, German default, choice remembered per browser; all labels from one dictionary. Data-driven reasons from the API stay German (business language), with the English UI explaining the labels.
- n8n: sticky notes German first, English below; node names "German (English)".
- Unchanged: tenant reply follows the email's language; Inovidus deliverables stay German.
