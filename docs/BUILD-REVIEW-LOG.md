# Build review log (append-only)

Builder/inspector pairs per module. Codex = Codex CLI 0.164.0 (gpt-6.1-sol, effort high); Claude = Claude Code (Opus 5.5).

## WO1 – offline reader, steps 5/6/8/9, actions, scenarios, CLI (built by Codex)
- Round 1 (Codex, 362 s): implementation done; Codex correctly **stopped** on an invalid YAML scenario file written by Claude (S04a) instead of working around the shared contract. Claude fixed it.
- Round 2 (WO1b, Codex, 435 s): 6 test files, 252 tests total, all 14 scenarios green.
- **Inspection by Claude – score 9/10.** Code is clean, privacy and approval rules hold, tests assert the work-order rules. Findings:
  - F1 (medium, spec gap by Claude): ambiguous matches showed prior cases of only one arbitrary candidate → fixed in WO2.
  - F2 (low): building-level task title showed the internal object id instead of the address → fixed in WO2.
  - Own fix (Claude, rules): offline urgency missed "läuft … Wasser unter der Spüle aus" (S4b) → keyword added, S4b now expects DRINGEND.

## WO2 – Groq/recorded providers, API, store (built by Codex)
- Codex, 386 s, 327 tests. **Inspection by Claude – 9/10**: clean; API needed three additions for the UI (rule_overrides, sender, .env loading) and a store refresh rule – Claude added them with a test.

## Inspection 1 of Claude's code (by Codex, fresh session, 315 s) – **Score 6/10, 13 findings**
R01 forged approval via POST /api/cases (high) · R02 unescaped HTML (high) · R03 emergency phrase → not a damage report (high, reader) · R04 alternative locations ignored (high, reader) · R05 phone match hid unknown sender · R06 crash with one candidate + strict margin · R07 vetoed contract blocked a valid winner · R08 no locking · R09 stale UI responses · R10 copied reply ≠ approved reply · R11 manual assignment did not regenerate task · R12 same case id for S1/S3 · R13 n8n dropped received_at/attachments.
- Claude fixed R01, R02, R05–R13 (commit "fix: Codex inspection findings…", 12 regression tests). Codex fixed R03, R04 in WO3 (one fix round after Claude found false positives on "oder").

## Inspection 2 – full build (by Codex, fresh session, 327 s) – **Score 6/10, 11 findings**
Fixes partly incomplete: R2-01 forged approval with actor "system" still accepted · R2-02 two buildings still allowed a building action · R2-03 emergency protection only in the offline reader · R2-04 "Musterstr 14" (no dot) not parsed · R2-05 uncertainty in the next sentence ignored · R2-06 stale/old approval could still order · R2-07 stored case lost scenario context · R2-08 no clarification text for unit_ambiguous · R2-09 "Kaltmiete" matched "kalt" · R2-10 unbounded floor could hang the grid · R2-11 handoff docs missing.
- Claude fixed R2-01/02/03/06/07/10 (+ 5 regression tests) and the Impeccable detector findings. Codex fixed R2-04/05/08/09 in WO4 (inspected by Claude with probes). R2-11: deliverables added.

## Inspection 3 – full build + docs (by Codex, fresh session, 368 s) – **Score 7/10, 6 findings**
R3-01 "Musterstraße 12 oder 14" not seen as two buildings · R3-02 "bei der Hausnummer unsicher" kept only "unsicher" · R3-03 stale tab could overwrite a newer result and approve it · R3-04 gas + power outage gave contradictory safety advice · R3-05 reader "SONSTIGES" + hint NOTFALL still downgraded · R3-06 effort numbers did not follow the timelog's own categories.
- Codex fixed R3-01/02 (WO5) and correctly **stopped** on R3-04 because it needed a field in Claude's `rules.py`. Claude fixed R3-03, R3-04 (config `safety_conflicts`, gas advice first), R3-05, R3-06 (effort rewritten: core 36 min AI-assisted, total window separate, Mithul's own time to be added). 553 tests.

## Inspection 4 – full build (by Codex, fresh session, 264 s) – **Score 8/10, 3 findings**
R4-01 "Anschrift"/"house number" uncertainty not recognised as building uncertainty · R4-02 UI could approve a reply/task text it had not displayed · R4-03 an order for an earlier assignment showed as done after reassignment.
- Claude fixed all three (+5 regression tests); end-to-end browser run (Playwright, real Chrome) of S1 approve+order, S2 manual approval with reason, S4c registered-address variant, S5b building action: no errors. 558 tests.

## Inspection 5 – first attempt failed (Codex usage limit, 18 Nov 21:50); Mithul chose to wait for the reset.

## Inspection 5 – full build (by Codex, fresh session, 19 Nov 00:17, 261 s) – **Score 7/10, 3 findings**
R5-01 "Vielleicht Musterstr. 12" kept only "Vielleicht" → building not marked uncertain · R5-02 gas recognised only by the reader did not activate gas safety advice · R5-03 a slow, older run could overwrite a newer result; approval did not check the rules version.
- Claude fixed R5-02 (config `category_hazards`), R5-03 (generation stamped at processing start; 409 when rules changed). Codex fixed R5-01 (WO6) and flagged a follow-up in matching.py ("Musterstraße12"), fixed by Claude. 588 tests.

## Inspection 6 – full build (by Codex, fresh session, 239 s) – **Score 7/10, 5 findings**
R6-01 "Musterstr. 12; ich bin unsicher" still allowed a building action · R6-02 after a human action + rule change the case could not be re-processed · R6-03 an identical newer run did not advance the generation watermark · R6-04 staff options kept the original contract's phone after manual reassignment · R6-05 effort report ended before the night session.
- Claude fixed all five: building doubt is now **fail-safe** (any location doubt blocks building actions unless it clearly concerns only floor/side – no longer dependent on recognising each phrasing); audited re-processing supersedes the proposal and voids earlier approvals; generation watermark; staff options regenerated for the approved contract; effort report split into calendar span, waiting time, active time and core. 593 tests, browser flows re-checked.

## Inspection 7 – full build (by Codex, fresh session, 249 s) – **Score 8/10, 2 findings**
R7-01 "Alte Musterstraße 12" was read as "Musterstraße 12" → could become a wrong READY_FOR_APPROVAL · R7-02 after reassignment the unknown-sender flag and staff options could disagree.
- Codex fixed R7-01 (WO7: multi-word street names; Claude added opener words like "Hilfe"/"Notfall" to the stoplist with tests). Claude fixed R7-02 (one consistent contact state for the approved contract, both directions tested). 637 tests.

## Inspection 8 – full build (by Codex, fresh session) – **Score 8/10, 2 findings**
R8-01 lowercase street prefix ("alte Musterstraße") dropped → Codex WO8 · R8-02 incomplete address earned half points (plan says 0) → Claude. (This run was marked "failed" by the runner only because docs/PLAN.md was changed by another session during the review; findings were valid.)

## Takeover and §19 (19 Nov, ~00:55)
A forked session had added plan §19 (Render hosting, full German/English) and a Codex review of it (R19-01..04). It handed over; this session built §19: translation layer + language switch, bilingual n8n, English deliverables, Render blueprint, n8n start script (rehearsed locally).

## Inspection 9 – full build incl. §19 (by Codex, fresh session, 347 s) – **Score 7/10, 3 findings**
R9-01 the n8n webhook was open and returned the full case → token-protected webhook + minimal receipt (Claude, rehearsed: 403 without token) · R9-02 "Musterstraße 12-14" and a prefix on the previous line were truncated → Codex WO9 · R9-03 superseded approvals still froze newer results → Claude. 785 tests.

## Inspection 10 – full build (by Codex, fresh session, 346 s) – **Score 7/10, 3 findings**
R10-01 the bootstrap n8n listened on all interfaces → loopback only, killed on failure (Claude; verified with lsof) · R10-02 "2. bzw. 3. OG" collapsed to one floor → Codex WO10 (run cut off by Codex's usage limit after writing the change; Claude inspected and proved it) · R10-03 translation re-render could reset a manual approval form → state kept per case (Claude; browser-checked). 837 tests.
Codex usage limit reached again (resets 05:17).

## Hosting (19 Nov, ~03:00–05:00)
Repo made public (Mithul's OK) so Render could read it; Render blueprint deployed both services in Frankfurt (free plan). Verified without credentials: intake /api/health 200, every other path 401; n8n ready after cold start, webhook 403 without token, owner pre-created (no public setup page).

## Inspection 11 – full build incl. hosting (by Codex, fresh session) – **Score 8/10, 3 findings**
R11-01 approvals were not tied to the ERP data the reviewer saw · R11-02 an LLM could return one field with alternatives ("2. bzw. 3. OG", "links bzw. rechts", "12-14") and get a definite match · R11-03 step requests of one chain could run on different rule versions.
- Claude fixed all three: ERP fingerprint per case (409 at approval, supersede on change, audit label "neu verarbeitet (ERP-Daten geändert)"); one shared check for compound location values in every provider (floor/side → review, street/house → building uncertain); steps and stores reject a case built on other rules/ERP data (409). +13 regression tests, 851 tests, 14/14 scenarios. Commit 6e0aecd, redeployed on Render.

## Inspection 12 – full build (by Codex, fresh session, 247 s) – **Score 8/10, 1 finding**
R11-01 and R11-03 confirmed fixed. R12-01: a floor range in words ("zweite bis dritte Etage", "EG, 2. OG") still became one floor. (The runner marked the run "code changed" only because this log was committed during the review; the finding was valid.)
- Claude fixed it: the floor check now counts every floor the value names (digits, German ordinal words, English ordinals, ground-floor terms) and treats ranges ("bis", "zwischen") as alternatives; more than one → floor unclear + review. +12 regression tests, 863 tests, 14/14 scenarios.
