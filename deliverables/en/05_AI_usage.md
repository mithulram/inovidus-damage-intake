# AI usage – what for, and what I checked or changed myself

*English version of [../05_KI_Nutzung.md](../05_KI_Nutzung.md). Full logs: `docs/AI_USAGE.md`, `docs/PLAN-REVIEW-LOG.md`, `docs/BUILD-REVIEW-LOG.md`.*

The task explicitly allows AI tools. I used them intensively – and organised the work so that two different AI systems **check each other**.

## Tools

| Tool | Role |
|---|---|
| **Claude Code** (Anthropic, Opus 5.5) | planning, data model, rules, matching logic, UI, translation layer, n8n workflow, documentation, coordination |
| **Codex CLI** (OpenAI, gpt-6.1-sol) | plan reviewer; built the rule-based reader, steps 5/6/8/9, the approval check, the API, the Groq connection and many tests; inspected Claude's code |
| **Groq** (`openai/gpt-oss-120b`) | the AI **inside the product**: reads e-mails (demo data only) |
| Design skills (Impeccable, UI/UX Pro Max, Taste) | design rules for the UI |

## Way of working: two AIs, cross-checking

1. **Plan:** Claude writes the plan, Codex scores it (0–10) with concrete defects. Several rounds to 10/10.
2. **Build:** every module is checked by the other AI. Codex inspected the code in eight independent rounds and found real defects each time (e.g. a forged approval could be injected, gas + power outage gave contradictory safety advice, a slow old run could overwrite a newer result). All were fixed with regression tests. Claude checked Codex's code the same way.
3. **Rules for the AIs:** never send automatically, make uncertainty visible, free tools only, keys only in `.env`, log the work honestly.

## What I decided, checked or changed myself

**Decisions (documented in the logs):** Groq as AI provider, no local AI; German floor counting and a strict rule (missing or unclear floor → always ask); unknown sender address: don't block, but a clear warning and three options; own UI instead of Streamlit, focus on a traceable flow; n8n as the visible process; everything readable in German **and** English; hosting on Render.

**Checked myself:** *[Mithul: please fill in honestly before sending.]*

**Changed myself:** *[Mithul: fill in if texts/rules were changed by hand.]*
