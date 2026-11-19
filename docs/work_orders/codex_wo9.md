# Work order WO9 – Codex (builder) · inspected by Claude

Finding R9-02 from Codex's inspection round 9. Files you own: `src/intake/providers/offline.py`, `tests/test_offline_provider.py`.

**R9-02 (high):** address extraction silently drops meaningful text:
- "Wasser läuft aus. Musterstraße 12-14, 2. OG links. Viele Grüße, Max Mustermann" → house number "12" only, no ambiguity → wrong READY_FOR_APPROVAL for MV-10245 and a certain building.
- "Alte\nMusterstraße 12, 2. OG links …" (prefix on the previous line) → "Alte" lost → same false match.
Fix (fail-safe): keep complete house-number expressions; ranges and lists ("12-14", "12–14", "12/14", "12, 14", "12 und 14", "12a-c") put every extra number into `location_alternatives` as written (e.g. "14") so review is forced and the building counts as uncertain. Street prefixes may be separated from the street word by any whitespace including a single line break. Anything the parser cannot fully account for must not silently become a shorter, valid-looking address.
Regressions (end-to-end, offline): both examples → NEEDS_REVIEW, no object action; S1 unchanged; "Musterstraße 12a" stays a single house number "12a".
Proof: `uv run pytest && uv run intake-scenarios`. Do not commit.
