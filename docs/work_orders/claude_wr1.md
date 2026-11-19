# Task plan (/claude-wr) – own probe review before Codex round 17 (trimmed)

Project plan: `docs/PLAN.md` (unchanged). This file only plans this task.

## Why trimmed
A generic "unexplained words" guard was reviewed 5 times (5 → 6 → 7 → 6 → 6) and kept growing special cases, the same plateau as the Codex rounds. Instead, the reviewers' problem e-mails were run against today's code (scratch script, no repo change). Only these produce a **material** wrong `READY_FOR_APPROVAL` (MV-10245, OBJ-MS12) today:

| Group | E-mail text (location part) | Today |
|---|---|---|
| A town/PLZ | "Musterstraße 12 in Anderstadt, 2. OG links" · "Ich wohne in der Musterstraße 12 in Anderstadt im 2. OG links" · "54321 Anderstadt, Musterstraße 12, 2. OG links" · "Musterstraße 12 in 54321 Anderstadt, 2. OG links" | READY (wrong) |
| A (side effect) | "Musterstraße 12, 12345 Musterstadt, 2. OG links" (correct PLZ) | review (PLZ read as 2nd house no.) |
| B building part | "Musterstraße 12, Hinterhaus, 2. OG links" · "Musterstraße 12\nHinterhaus\n2. OG links" · "Musterstraße 12, Haus B, 2. OG links" | READY (wrong) |
| C flat number | "Musterstraße 12, Wohnung 5, 2. OG links" · "…, 2. OG links, Wohnung 5" · "2. OG Wohnung 5 links" | READY (wrong) |

Controls that are correct today and must stay so: "Musterstraße 12, im ganzen Haus riecht es nach Gas, 2. OG links" (READY, NOTFALL, OBJ-MS12) · "In der Musterstraße 12 ist im 2. OG links ein Rohr geplatzt" (READY, NOTFALL).

## Goal
Fix groups A, B, C with three narrow, explainable checks; keep every existing test and scenario result.

## Acceptance criteria
1. Every group A/B/C e-mail above → `NEEDS_REVIEW`, no selected contract. A and B → `building_uncertain`, `object_id` None; C → unit doubt only (`object_id == "OBJ-MS12"`).
2. "Musterstraße 12, 12345 Musterstadt, 2. OG links" → READY MV-10245 (correct PLZ/city is accepted).
3. The two controls above keep status, contract, urgency, `object_id`; S5b keeps `task_scope: object`.
4. Full suite + 14 scenarios pass; no existing expectation changes except the exact-dict test getting the new key `postal_raw: None`.

## Approach (3 targeted fixes)
**A – PLZ/town (provider-independent check in matching).**
- Reader: the house-number continuation stops before a 5-digit number (`\d{5}(?!\d)`), so "12, 12345 Musterstadt" keeps house no. "12" (tests: "12, 14", "12-14", "12, 2. OG", all 20 cases of the house-number list in `tests/test_offline_provider.py` unchanged).
- Reader: new optional `Extraction.postal_raw` (default None; not in the Groq schema – Groq unchanged), read only directly around `addresses[0]` in the body: after it `(?:in\s+)?(\d{5})(?:\s+City)?` or `in\s+City` followed by comma/line break/end/`im|in|am|auf`/digit; before it `(\d{5})\s+City[\s,]*`. `City` = capitalised word, **case-sensitive**, never an article, room, floor or building-part word.
- Matching: before the alternatives block, if `postal_raw` is set and `_address_certain(loc, erp)` finds the property: each given part (PLZ exact, city folded) must equal the property; otherwise flag "PLZ/Ort … passt nicht zu …" → `unit_ambiguous` + `building_uncertain`.

**B – building part (reader).** In the sentence/address block of `addresses[0]` (block = lines without a blank line between), a building-part designator → address alternative "<address> <designator>" → existing `street_word` rule → building uncertain. Designators: `Hinterhaus, Vorderhaus, Seitenflügel, Quergebäude, Gartenhaus, Rückgebäude` alone, or `Haus|Aufgang|Eingang|Block|Treppenhaus` **+ letter/number** ("Haus B", "Aufgang 2"). Bare "Haus"/"Eingang" (as in "im ganzen Haus riecht es nach Gas") never count. Word list in `config/rules.yaml` (`normalize.building_part_words`), editable live.

**C – flat number (reader).** "Wohnung|Whg.|WE|Apartment|Flat + number" in the sentence of the primary floor/side → unit-only alternative built as "Wohnung 5, <floor/side text>" (ends with a floor/side word, so matching keeps the building certain and only raises `unit_ambiguous`).

## Files
`src/intake/providers/offline.py`, `src/intake/models.py` (`postal_raw`), `src/intake/matching.py` (postal check), `src/intake/rules.py` + `config/rules.yaml` (`building_part_words`), tests: new `tests/test_probe_review.py` (all A/B/C e-mails + controls, parametrised; full-email and raw-`Extraction` cases for the postal check), `docs/BUILD-REVIEW-LOG.md`.

## Test command
`uv run pytest -p no:warnings -q && uv run intake-scenarios`

## Handover to Codex (10:22)
Codex round 17 runs from a separate worktree at a fixed commit, so ongoing edits cannot spoil it. Without "push" before then, it inspects **79d202e** (pushed, not yet deployed on Render); this build is inspected only if Mithul says "push" first.

## Risks / non-goals
- Narrow checks catch only these phrasings; other wordings may still slip (the design answer stays "if in doubt, review"; production needs a real test set).
- Known limitation: a real town that ends like a room/state word (e.g. "Karlsbad") is not read as a town → no postcode/town check for it (behaviour as before).
- Not fixed (extra reviews only, not material): "12, I live…" single-letter house-number continuation; "links kein Wasser" read as negation.
- Non-goals: Groq prompt, UI, hosting. No commit/push until Mithul says "push"; this root `PLAN.md` then moves to `docs/work_orders/claude_wr1.md`.

## Review status
Plan review (/claude-wr, fresh Opus reviewer each round, same model as the builder – logged as Claude self-review): 5 → 6 → 7 → 6 → 6 on the generic-guard design; stopped by the no-improvement rule. This trimmed plan replaces it, based on probe evidence; it is re-checked in the build-phase review.
