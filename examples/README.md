# Beispielausgaben

Erzeugt mit `uv run intake process …` bzw. der Testfall-Suite. Jede Datei gibt es als lesbare Zusammenfassung (`.md`) und als vollständigen Datensatz (`.json`, Schritt 7 der Aufgabe).

| Datei | Fall | Leser |
|---|---|---|
| [S1_regelmodus.md](S1_regelmodus.md) | Original-E-Mail → MV-10245, bitte freigeben | Regeln, ohne KI |
| [S1_groq_aufzeichnung.md](S1_groq_aufzeichnung.md) | dieselbe E-Mail, gelesen von Groq (echte Antwort, aufgezeichnet) | Groq `openai/gpt-oss-120b` |
| [S2_regelmodus.md](S2_regelmodus.md) | ohne Etage/Seite → Prüfung nötig, Rückfrage | Regeln |
| [S3_regelmodus.md](S3_regelmodus.md) | Vertrag inaktiv → Prüfung, kein Ausweichen | Regeln |
| [S5b_regelmodus.md](S5b_regelmodus.md) | Gasgeruch, Wohnung unklar → NOTFALL, Gebäude-Maßnahme | Regeln |
| [S7_groq_aufzeichnung.md](S7_groq_aufzeichnung.md) | englische E-Mail → englische Antwort, Etage nachfragen | Groq (Aufzeichnung) |

`llm_recorded/` enthält die echten Groq-Antworten (ohne Schlüssel) samt Schema und Systemprompt.
