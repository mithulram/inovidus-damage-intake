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
| 2026-11-19 | Claude Code (Opus 5.5) | Took over §19 from a forked session: German→English translation layer, UI language switch, bilingual n8n, English deliverables, Render hosting (blueprint, n8n bootstrap, access protection), fixes for Codex inspection rounds 5–10 | _open_ |
| 2026-11-19 | Codex CLI (gpt-6.1-sol) | Inspection rounds 5–10 (scores 7, 7, 8, 8, 7, 7); built reader fixes WO6–WO10 (WO10 cut off by usage limit, result inspected and proved by Claude) | _open_ |
| 2026-11-19 | Claude Code (Opus 5.5 + browser) | Deployed both services on Render (public repo, Frankfurt, free plan) and verified them without credentials; fixed the findings of Codex inspection rounds 11–16 (ERP version per case, compound and negated places, server seal against edited proposals, strict step order, header name in identity check) | _open_ |
| 2026-11-19 | Codex CLI (gpt-6.1-sol) | Inspection rounds 11–16 (scores 8, 8, 7, 8, 7, 8) in fresh sessions; round 17 stopped by the Codex usage limit | _open_ |
| 2026-11-19 | Claude Code (Opus 5.5) + Opus reviewer (/claude-wr, approved by Mithul because Codex was at its limit; same model family = self-review, not independent) | Probed the rules reader with unusual e-mails; planned and built postcode/town, building-part and flat-number checks; plan review 5 rounds, build review 6 rounds | _open_ |
| 2026-11-19 | Codex CLI (gpt-6.1-sol) | Inspection rounds 17 (8/10) and 18 (7/10) in separate worktrees; all 6 findings fixed by Claude; stopped after round 18 by the agreed stop rule | _open_ |
