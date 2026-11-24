# Wiederverwendung für einen internen KI-Assistenten (Dokumente und Wissen)

Ein interner Assistent soll Fragen zu Unternehmensdokumenten beantworten (z. B. „Welche Kündigungsfrist gilt für Gewerbemieter im Objekt X?“). Viele Bausteine dieser Lösung passen direkt:

| Baustein aus dem Prototyp | Wiederverwendung im Wissensassistenten |
|---|---|
| **Eingang und Normalisierung** (E-Mail lesen, Text bereinigen) | Dokumente einlesen (PDF, DMS, E-Mail, Wiki), Text bereinigen und in Abschnitte teilen |
| **Anbieter-Schnittstelle** (`LLMProvider`: Groq, Regeln, Aufzeichnung) | dieselbe Schnittstelle für Antworten; Modell austauschbar (EU-Modell, lokal) |
| **Strenges JSON-Schema + Prüfung** (Pydantic) | Antworten immer mit Quellenangaben im festen Format; ungültige Antworten abfangen |
| **ERP-Anbindung und Vorgangshistorie** | zusätzliche Wissensquelle neben Dokumenten (z. B. Vertragsdaten, offene Vorgänge) – Suche/RAG |
| **Punkte, Schwelle, Abstand, „Prüfung nötig“** | „Nur mit Quelle antworten. Ist die Fundstelle schwach oder widersprüchlich: ‚Ich bin unsicher‘ sagen und an Fachexperten weiterleiten.“ |
| **Regeldatei** (`rules.yaml`) | Einstellungen ohne Programmieren: Schwellen, erlaubte Quellen, Sperrthemen |
| **Prüfplatz + Freigabe + Protokoll** | Rückmeldung „Antwort hilfreich / falsch“, Freigabe sensibler Antworten, Nachvollziehbarkeit |
| **Testfälle mit erwartetem Ergebnis** | Test-Set aus Fragen und richtigen Antworten; bei jeder Änderung automatisch prüfen |
| **n8n als sichtbarer Ablauf** | Dokument-Import, regelmäßige Aktualisierung, Benachrichtigungen |

**Was neu dazukommt:** eine Vektor-Suche (z. B. pgvector), Berechtigungen pro Dokument (nicht jede:r darf alles sehen), und Zitate in jeder Antwort.

**Wichtigste Übernahme:** die Haltung *„Unsicherheit ist ein Ergebnis, kein Fehler“*. Der Assistent darf – wie die Zuordnung hier – nie raten, sondern zeigt, worauf er sich stützt, und sagt klar, wenn er sich nicht sicher ist.
