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

## Inspection 13 – full build (by Codex, fresh session, 265 s) – **Score 7/10, 3 findings**
R13-01 the rules reader dropped a floor in "Zwischen 2. und 3. OG" / "erste, zweite Etage" (the R12 fix only covered values handed to matching) · R13-02 a record with an empty rules/ERP stamp skipped the version check · R13-03 "Mein Mietvertrag läuft aus … Kaution" became water damage.
- Claude fixed all three: floor lists joined by "und"/comma are kept when the operand is clearly a floor ("Musterstr. 12, zweite Etage" stays one floor); records without both stamps are refused (409, re-process); "läuft"/"läuft aus" alone no longer count as damage ("läuft aus der/dem …" does). +10 regression tests, 873 tests, 14/14 scenarios.

## Inspection 14 – full build (by Codex, fresh session, 239 s) – **Score 8/10, 2 findings**
R14-01 a caller with the password could edit a proposal (status, contract, building) and store it – version stamps do not prove who made the decision · R14-02 a negated place ("2. OG, aber nicht links", side_raw "nicht links") still became a definite match.
- Claude fixed both: every case the server hands out carries a server seal (HMAC over the whole record); steps and the review list accept only unchanged sealed cases (409 otherwise); generation stamp switched to microseconds so the seal survives JavaScript (n8n, browser). Negated places count as doubt in the shared normalizer and in the rules reader. Verified end to end through the local n8n (S1 → READY_FOR_APPROVAL, sealed) and the browser (approve → order offered). +12 tests, 884 tests, 14/14 scenarios.

## Inspection 15 – full build (by Codex, fresh session, 346 s) – **Score 7/10, 3 findings**
R14 fixes confirmed (direct proposal tampering blocked). R15-01 "Wir wohnen nicht mehr im 2. OG links" – negation across "mehr" was lost · R15-02 "Adresse: Am Beispielweg 7" was shortened to "Beispielweg 7" → wrong building · R15-03 the e-mail header name was dropped (rules reader, Groq message, n8n), so a partner report without signature skipped the identity check.
- Claude fixed all three: any negation earlier in the same clause makes the place doubtful; a street preposition is kept when it is clearly part of the name (capitalised mid-sentence), otherwise the address is doubtful (review); the header name is carried through n8n and the Groq message and checked against the contract holder for every provider. Verified through the local n8n (partner report → NEEDS_REVIEW). +10 tests, 892 tests, 14/14 scenarios.

## Inspection 16 – full build (by Codex, fresh session, 240 s) – **Score 8/10, 2 findings**
R16-01 negation AFTER the place ("… 2. OG links wohnen wir nicht mehr") was missed · R16-02 a sealed but unfinished record (stopped after "match") could enter the inbox and allow a building action without urgency or safety advice.
- Claude fixed both: negation later in the same clause also makes the place doubtful; steps run once and in order (re-running an earlier step is refused), only completely processed records enter the inbox (422) and only those can be acted on. Checked through the local n8n (S1 READY, gas NOTFALL review). +6 tests, 897 tests, 14/14 scenarios.

## Own probing while Codex was at its usage limit (19 Nov, ~06:30) – by Claude, NOT an independent review
Claude sent 13 unusual tenant e-mails through the rules reader. Three became a wrong READY_FOR_APPROVAL: a hedging bracket after the floor ("2. OG links (oder doch 3.?)"), writing for someone else ("schreibe aber für meine Mutter") and an agent signature ("i. A. Hausverwaltung"). Fixed: a hedging bracket right after a place is doubt; a proxy phrase makes the tenant "unbekannt (…)" so the name no longer matches. A broader "doubt after the place" rule was tried and reverted because it broke 71 deliberate tests (unrelated doubt such as "bitte heute oder morgen kommen" must not force review). +5 tests. Codex inspects these changes in round 17.

## Claude plan review while Codex was at its limit (/claude-wr, ~06:40–07:30)
A generic "unexplained words near the address" guard was planned and reviewed by fresh Opus reviewers (same model as the builder – Claude self-review, not independent): 5 → 6 → 7 → 6 → 6, stopped by the no-improvement rule. Each round found a way the guard itself would break normal e-mails, so the plan was trimmed after testing the reviewers' examples against the code: three real gaps remain (another town/PLZ next to the address, building parts such as "Hinterhaus"/"Haus B", flat numbers such as "Wohnung 5"). Plan in `docs/work_orders/claude_wr1.md`; not built yet.

## Inspection 17 – commit 79d202e (by Codex, fresh session in a separate worktree, 258 s) – **Score 8/10, 2 findings**
The three known gaps above were declared to Codex in advance. R17-01 a line break inside a sentence hid a negation ("… links wohnen wir↵nicht mehr") · R17-02 writing for someone else was not a reliable review gate ("für meinen Partner" without a name was not recognised; with a lowered threshold a recognised proxy report could still become ready).
- Claude fixed both: a wrapped line is whitespace (only punctuation, a blank line or the body/subject seam end a clause); the reader records `on_behalf_of` ("für meinen Partner", "für meine Mutter", "i. A.", …) and matching always raises the identity gate for it, independent of the threshold. +7 tests, 909 tests, 14/14 scenarios.

## Build of the trimmed plan + Claude build review (/claude-wr, ~10:35–11:10)
Fixes A (postcode/town next to the address compared with the ERP; correct "12345 Musterstadt" no longer read as a 2nd house number), B (building parts "Hinterhaus", "Haus B", "Aufgang 2" → building uncertain), C ("Wohnung 5" → unit unclear). Detectors for "writes for someone else" and postcode/town run for every reader (also Groq). Build review by fresh Opus reviewers (same model as the builder – self-review, not independent): 5 → 7 → 8 → 7 → 9 → 9; each finding fixed with a test (line-style address blocks, CRLF/trailing spaces, "nicht mehr" at line end, towns such as "Bad Homburg", "in Lebensgefahr" is not a town, flat sizes "3 Zimmer", counts "3 Wohnungen"). Known limitation: a real town ending like a room/state word (e.g. "Karlsbad") is not read as a town, so no postcode/town check runs for it (same behaviour as before this change). 977 tests, 14/14 scenarios.
