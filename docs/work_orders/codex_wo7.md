# Work order WO7 – Codex (builder) · inspected by Claude

Finding R7-01 from Codex's inspection round 7. Files you own: `src/intake/providers/offline.py`, `tests/test_offline_provider.py`.

**R7-01 (high):** "Wasser läuft aus. Alte Musterstraße 12, 2. OG links. Viele Grüße, Max Mustermann" is extracted as "Musterstraße 12" – the explicit different street "Alte Musterstraße" is lost, so matching scores the address as a match and returns READY_FOR_APPROVAL for MV-10245.
Fix: capture multi-word street names – up to two capitalised words directly before the street word (e.g. "Alte Musterstraße", "Am Alten Musterweg", "Karl-Marx-Straße"), but not sentence words such as "Wir", "In", "Der", "Die", "Ich", "Hallo", "Bitte" (keep a small stoplist; "in der Musterstr. 12" must still give "Musterstr."). If extraction is unsure whether a preceding capitalised word belongs to the street, prefer the longer name (a wrong longer name causes an address veto → review, which is safe; a truncated name can cause a wrong match).
Regressions (end-to-end, offline): the example above → not READY_FOR_APPROVAL and no object action for OBJ-MS12; S1 ("Wir wohnen in der Musterstr. 12") unchanged; "Karl-Marx-Straße 5" extracted whole.
Proof: `uv run pytest && uv run intake-scenarios`. Do not commit.
