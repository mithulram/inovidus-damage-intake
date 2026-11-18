# AI usage (honest log)

Format: what the AI did → what Mithul checked or changed. Mithul fills the right column; Claude never fills it on his behalf.

| Date | Tool | What the AI did | Checked / changed by Mithul |
|---|---|---|---|
| 2026-11-18 | Claude Code (Opus 5.5) | Read the task, researched inovidus.de, wrote `docs/00_UNDERSTANDING.md` (task analysis, data trap, interview risks) | _open – to be filled by Mithul_ |
| 2026-11-18 | Claude Code (Opus 5.5) | Drafted `docs/PLAN.md` | _open_ |
| 2026-11-18 | Codex CLI 0.164.0 (gpt-6.1-sol, effort high) | Reviewed `docs/PLAN.md` in 4 rounds (REVISE → 10/10 → 9/10 → 10/10); 4 findings, all accepted (n8n approval boundary, inactive contracts in ambiguity check, address veto, S4b arithmetic). See `docs/PLAN-REVIEW-LOG.md` | _open_ |
| 2026-11-18 | Claude Code advisor | Pointed out that two test scenarios would pass for the wrong reason and that "unknown sender address" was uncovered → fixed in plan | _open_ |
| 2026-11-18 | Claude Code (Opus 5.5) | Built: data model, rules.yaml, ERP seed, scenarios, normalisation + matching, pipeline, UI (with Impeccable/UI-UX Pro Max/Taste skills), n8n workflow, fixes for Codex's findings, German deliverables, explainer | _open_ |
| 2026-11-18 | Codex CLI (gpt-6.1-sol) | Built: offline reader, steps 5/6/8/9, action handler, scenario runner, CLI, Groq + recorded providers, API, most tests (WO1–WO4); inspected Claude's code twice (13 + 11 findings) | _open_ |
| 2026-11-18 | Claude Code | Inspected Codex's code (WO1–WO4): 2 spec gaps, 2 text issues, 1 false-positive defect found and fixed via Codex | _open_ |
| 2026-11-18 | Claude Code (browser) | Created the Groq API key "inovidus-damage-intake" in Mithul's browser (with his permission), stored only in .env | _open_ |
| 2026-11-18 | Groq (openai/gpt-oss-120b) | Product LLM: read 5 demo emails (recorded in examples/llm_recorded/) | _open_ |
