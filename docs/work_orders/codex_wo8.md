# Work order WO8 – Codex (builder) · inspected by Claude

Finding R8-01 from Codex's inspection round 8. Files you own: `src/intake/providers/offline.py`, `tests/test_offline_provider.py`.

**R8-01 (high):** lowercase street prefixes are dropped: "Wasser läuft aus. alte Musterstraße 12, 2. OG links. Viele Grüße, Max Mustermann" → "Musterstraße 12" → wrong READY_FOR_APPROVAL for MV-10245. `tests/test_offline_provider.py:77` currently *expects* this truncation – replace that expectation.
Fix (fail-safe): a word directly before the street word that is not a known function word (der, die, das, dem, den, in, im, am, an, auf, zur, zum, bei, von, wohnen, wohne, leben, adresse, anschrift, hallo, bitte, hilfe, notfall, we, at, live, in English "the"; case-insensitive) belongs to the street name, regardless of capitalisation – keep up to two such words ("alte Musterstraße", "Am alten Musterweg"). A too-long street name only causes an address veto (review, safe); a truncated one can cause a wrong match.
Regressions: the example → end-to-end NEEDS_REVIEW and no object action for OBJ-MS12; S1 ("wohnen in der Musterstr. 12") unchanged; "Am alten Musterweg 3" and "Karl-Marx-Straße 5" kept whole; "Hilfe Musterstraße 12" → "Musterstraße".
Proof: `uv run pytest && uv run intake-scenarios`. Do not commit.
