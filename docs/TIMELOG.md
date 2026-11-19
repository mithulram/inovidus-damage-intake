# Timelog (honest, real timestamps)

Who: **Mithul** (human), **Claude** (Claude Code, Opus 5.5), **Codex** (Codex CLI reviewer/builder).
Times are local (Europe/Berlin). "Core" = work within the spirit of the 90-min task; "Extra" = docs, review loops, UI polish, interview prep.

| Date | From | To | Who | What | Core/Extra |
|---|---|---|---|---|---|
| 2026-11-18 | ~19:08 | – | Mithul | Set up project folder: TASK.md, CLAUDE.md, KICKOFF_PROMPT.md, .env.example (time spent before 19:08 not logged here – Mithul to add) | Extra |
| 2026-11-18 | 19:08 | 19:11 | Claude | Read task + rules; researched inovidus.de (services, focus areas) | Core |
| 2026-11-18 | 19:11 | 19:12 | Claude | Wrote docs/00_UNDERSTANDING.md | Core |
| 2026-11-18 | 19:12 | 19:21 | Claude + Codex | Drafted docs/PLAN.md (Claude); 4 Codex review rounds, 4 findings accepted, final 10/10 | Core (plan) / Extra (review rounds) |
| 2026-11-18 | 19:21 | 19:30 | Mithul + Claude + Codex | Mithul answered Q1–Q6; Claude updated plan, found frontend-design skill + Groq key location; Codex round 5: 10/10 | Extra |
| 2026-11-18 | 19:30 | 19:53 | Mithul + Claude + Codex | Decisions (custom UI, strict floors, Q5); plan updated; skill search; Codex rounds 6–7 → 10/10 | Extra |
| 2026-11-18 | 19:53 | 20:07 | Claude + Codex | Searched/installed design skills (Impeccable, UI/UX Pro Max, Taste); plan §18 build revision; Codex rounds 8–9 → 10/10 | Extra |
| 2026-11-18 | 20:07 | 20:15 | Claude | Scaffold: git, uv, data model, rules.yaml, ERP seed, 14 scenarios, matching engine (47 tests) | Core |
| 2026-11-18 | 20:15 | 20:30 | Codex (+ Claude review) | WO1: offline reader, steps 5/6/8/9, action handler, scenario runner, CLI, tests (252) | Core |
| 2026-11-18 | 20:15 | 20:30 | Claude | Groq: verified docs, created key in Mithul's browser, recorded 5 live responses | Extra |
| 2026-11-18 | 20:30 | 20:39 | Codex (+ Claude review) | WO2: Groq/recorded providers, FastAPI API + step endpoints, case store | Extra |
| 2026-11-18 | 20:00 | 20:43 | Claude | UI design with Impeccable (product record, roll, direction contract), fonts, build | Extra |
| 2026-11-18 | 20:43 | 20:50 | Claude | n8n 2.48.5 installed locally, workflow built, run, exported; screenshots | Extra |
| 2026-11-18 | 20:50 | 21:01 | Codex → Claude | Codex inspection of Claude's code (6/10, 13 findings); Claude fixed 11 | Extra |
| 2026-11-18 | 21:01 | 21:09 | Codex (+ Claude review) | WO3: reader fixes (emergencies, ambiguous locations) | Extra |
| 2026-11-18 | 21:09 | 21:18 | Codex → Claude | Re-inspection (6/10, 11 findings); Claude fixed 7 | Extra |
| 2026-11-18 | 21:18 | 21:24 | Codex (+ Claude review) | WO4: reader/draft fixes | Extra |
| 2026-11-18 | 21:10 | 21:30 | Claude | Deliverables (German), examples, README, explainer (private) | Extra |

Note: rows overlap because Claude and Codex worked in parallel. Mithul's own time (reading, answering the plan questions 19:21–20:07, reviewing) is not measured here – Mithul to add.
| 2026-11-18 | 21:30 | 21:39 | Codex → Claude | Inspection round 3 (7/10, 6 findings); WO5 (Codex) + Claude fixes | Extra |
| 2026-11-18 | 21:45 | 21:50 | Claude | Round 4 fixes, end-to-end browser check, fresh examples + screenshots; Codex round 5 blocked (Codex usage limit) | Extra |
| 2026-11-19 | 00:17 | 00:29 | Codex → Claude | Inspection round 5 (7/10, 3 findings); fixes by Claude + Codex WO6 | Extra |
| 2026-11-19 | 00:29 | 00:36 | Codex → Claude | Inspection round 6 (7/10, 5 findings); Claude fixes | Extra |
| 2026-11-19 | 00:45 | 00:46 | Codex → Claude | Inspection round 7 (8/10, 2 findings); fixes (Claude + Codex WO7) | Extra |
| 2026-11-19 | 00:50 | 02:00 | Claude (+ Codex WO8–WO10, inspections 8–10) | Takeover from forked session; §19: translation layer + language switch, bilingual n8n, English deliverables, Render blueprint + n8n start script (rehearsed), webhook token; fixes for rounds 8–10; screenshots. Codex usage limit again at ~01:45 (resets 05:17) | Extra |
| 2026-11-19 | 02:25 | 02:33 | Claude | Repo made public (Mithul's OK); Render blueprint deploy of both services started 02:27, live 02:37 | Extra |
| 2026-11-19 | 02:33 | 05:01 | – | Pause (usage limits); no work | – |
| 2026-11-19 | 05:01 | 05:11 | Claude | Verified hosted services without credentials (401/403, no n8n setup page); live URLs in README | Extra |
| 2026-11-19 | 05:11 | 06:17 | Codex → Claude | Inspection rounds 11–16 (8, 8, 7, 8, 7, 8 /10) and Claude's fixes after each (ERP fingerprint, compound/negated places, server seal, step order); redeploys on Render; checks through local n8n + browser. Codex usage limit again at 06:17 (resets 10:20) | Extra |
