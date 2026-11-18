# Plan review log (append-only)

- Host/planner: Claude Code (Opus 5.5). Reviewer: Codex CLI 0.164.0 (model: CLI default, recorded per round).
- Scope: review of `docs/PLAN.md` only. Building is **not** authorized (Mithul must say "approved").
- Round limit: 5. Target: Codex score 10/10; minor/optional findings flagged to Mithul.
- Runner diagnostics kept outside the repo (session scratchpad).

## Round 1 – Codex (gpt-6.1-sol, effort high), plan sha256 de685136…, 136 s
Verdict: **REVISE** (no numeric score given). Summary: approval-boundary conflict in n8n flow; two matching paths could mark an uncertain assignment as ready.
- R1 (high) n8n branches from READY_FOR_APPROVAL straight into task creation → contract write without approval. → **Accepted**: proposals only; shared action handler enforces approval.
- R2 (high) Excluding inactive contracts from the margin can hide ambiguity (inactive 2. OG li. vs active 2. OG re., side missing). → **Accepted**: Stage A (identify unit incl. inactive) / Stage B (eligibility, no fallback); scenario S3b.
- R3 (medium) Address contradiction only loses points; with threshold 0.65 a different building could pass. → **Accepted**: address veto; scenario S8.

## Round 2 – Codex (same session, resumed), plan sha256 bebe0278…, 24 s
Verdict: **APPROVED – Score: 10/10.** "R1–R3 are resolved in the revised design. No additional material defects found within the prototype scope."
Limitation noted by Codex: approval covers the plan only; runtime enforcement can only be checked after build.
Note (Claude): round 2 was a short resumed re-check focused on the R1–R3 fixes, not a second full fresh review.

## Host self-check after round 2 (Claude + advisor)
Found that S3b/S8 would pass "for the wrong reason" (already below threshold), KICKOFF §4 "unknown email address" uncovered, S7 floor ambiguity only a note. Fixed: matching sender contact in S3b/S8, expected deciding gate per scenario, new S4c + config switch (Q5), S7 default `ask` (Q6).

## Round 3 – Codex (resumed), plan sha256 9f107214…, 65 s
Verdict: **REVISE – Score: 9/10.**
- R4 (medium) S4b expected `identity` gate, but an unknown name gives ≤ 0.70 → threshold fails first. → **Accepted**: tenant_name vs sender_name separated; S4b rewritten (0.90). Same fix applied to S4a (0.85 with contact).

## Round 4 – Codex (resumed), plan sha256 c112636a…, 20 s
Verdict: **APPROVED – Score: 10/10.** "R4 is resolved, and R1–R3 remain resolved. No material unresolved defects found."
Approval check: "Approval matches the current plan." Rounds 2–4 were resumed re-checks of the fixes (same Codex session), not fresh full reviews.
Next: Mithul's approval ("approved") required before any build. If his answers to Q1–Q6 change the plan, one more short Codex round is needed (approval is bound to the plan hash).

## Mithul's answers (18 Nov 2026) → plan updated
Groq (no local LLM), n8n locally via npx, Python left to Claude (3.12), European floor counting, frontend-design skill found on disk. Q5 re-explained, still open.

## Round 5 – Codex (resumed), plan sha256 34ac68a2…, 66 s
Verdict: **APPROVED – Score: 10/10.** "The revised plan consistently reflects the recorded decisions. R1–R4 remain resolved." Approval check: matches current plan.
Noted for build: `.env.example` still has Ollama lines and MATCH_CONFIDENCE_THRESHOLD → migrate at scaffold.
Round budget (5) used up. Any further plan change → ask Mithul before another round.

## Mithul's further decisions (18 Nov 2026)
Custom web UI instead of Streamlit (unique look, flow first; Impeccable + Taste skills), German floor counting + strict (English ordinals / unclear terms → review), Q5 = staff decides with warning + 3 options. Rounds 6–7 run beyond the default 5 under Mithul's "loop until 10/10" rule.

## Round 6 – Codex (resumed), plan sha256 e6e4ff0b…, 59 s
Verdict: **REVISE – Score: 9/10.**
- R5 (medium) "Missing floor → review" stated in §5.1 but no gate enforced it; with threshold 0.65 a no-floor email could be READY. → **Accepted**: `floor_missing` flag, exact failed-gate sets per scenario, new S9.

## Round 7 – Codex (resumed), plan sha256 18325601…, 31 s
Verdict: **APPROVED – Score: 10/10.** Approval check: matches current plan.

## Mithul's go-ahead (18 Nov 2026, chat)
"You and Codex have a conversation, and then you can start implementing. I think all our questions are clear." Changes agreed with Codex from here on are pre-authorized by this go-ahead. Q5 refinement: call option only when a phone number is known. Plan revised (§18: n8n showcase rules, Codex build split, repo privacy, design skills).

## Round 8 – Codex (resumed), plan sha256 b8fe461a…, 126 s
Verdict: **REVISE – Score: 9/10.** R6 (medium): GroqProvider assigned to the offline builder, but checking current Groq docs needs network. → **Accepted**: Claude verifies docs, writes `docs/reference/groq_api.md`, installs the client and records one live response before handoff.

## Round 9 – Codex (resumed), plan sha256 738ae076…, 18 s
Verdict: **APPROVED – Score: 10/10.** Approval check: matches current plan. **Build starts.**
