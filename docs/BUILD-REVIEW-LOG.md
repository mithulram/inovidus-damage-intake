# Build review log (append-only)

Builder/inspector pairs per module. Codex = Codex CLI 0.164.0 (gpt-6.1-sol, effort high); Claude = Claude Code (Opus 5.5).

## WO1 – offline reader, steps 5/6/8/9, actions, scenarios, CLI (built by Codex)
- Round 1 (Codex, 362 s): implementation done; Codex correctly **stopped** on an invalid YAML scenario file written by Claude (S04a) instead of working around the shared contract. Claude fixed it.
- Round 2 (WO1b, Codex, 435 s): 6 test files, 252 tests total, all 14 scenarios green.
- **Inspection by Claude – score 9/10.** Code is clean, privacy and approval rules hold, tests assert the work-order rules. Findings:
  - F1 (medium, spec gap by Claude): ambiguous matches showed prior cases of only one arbitrary candidate → fixed in WO2.
  - F2 (low): building-level task title showed the internal object id instead of the address → fixed in WO2.
  - Own fix (Claude, rules): offline urgency missed "läuft … Wasser unter der Spüle aus" (S4b) → keyword added, S4b now expects DRINGEND.
