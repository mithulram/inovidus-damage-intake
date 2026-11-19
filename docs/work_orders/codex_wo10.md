# Work order WO10 – Codex (builder) · inspected by Claude

Finding R10-02 from Codex's inspection round 10. Files you own: `src/intake/providers/offline.py`, `tests/test_offline_provider.py`.

**R10-02 (high):** compound floor expressions collapse to one floor: "Wasser läuft aus. Musterstraße 12. Die Wohnung liegt im 2. bzw. 3. OG rechts. Viele Grüße, Max Mustermann" → only "3. OG" → wrong READY_FOR_APPROVAL for MV-10487.
Fix (fail-safe): recognise every compound/alternative floor or side expression before picking one: "2. bzw. 3. OG", "2. oder 3. OG", "2./3. OG", "2.-3. OG", "2. bis 3. OG", "zweite oder dritte Etage", "2nd or 3rd floor", "links bzw. rechts", "entweder … oder …". Keep the first as `floor_raw`/`side_raw` and put the others, as written, into `location_alternatives` (forces review; floor-only doubts keep the building certain). Also treat "bzw." like "oder" for addresses ("Musterstraße 12 bzw. 14"). Scheduling phrases ("heute bzw. morgen") must still be ignored.
Regressions (end-to-end, offline): the example → NEEDS_REVIEW with `unit_ambiguous`; each listed form; S1 unchanged.
Proof: `uv run pytest && uv run intake-scenarios`. Do not commit.
