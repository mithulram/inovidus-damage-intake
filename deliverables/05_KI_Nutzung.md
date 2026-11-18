# KI-Nutzung – wofür, und was ich selbst geprüft oder angepasst habe

Die Aufgabe erlaubt KI-Werkzeuge ausdrücklich. Ich habe sie bewusst intensiv eingesetzt – und so organisiert, dass zwei verschiedene KI-Systeme sich **gegenseitig prüfen**. Das vollständige Protokoll steht in `docs/AI_USAGE.md`, `docs/PLAN-REVIEW-LOG.md` und `docs/BUILD-REVIEW-LOG.md`.

## Werkzeuge

| Werkzeug | Rolle |
|---|---|
| **Claude Code** (Anthropic, Modell Opus 5.5) | Planung, Datenmodell, Regeln, Zuordnungslogik, Oberfläche, n8n-Workflow, Dokumentation, Koordination |
| **Codex CLI** (OpenAI, Modell gpt-6.1-sol) | Prüfer des Plans; Entwickler von Leser (Regelmodus), Schritten 5/6/8/9, Freigabe-Prüfung, API, Groq-Anbindung und vielen Tests; Prüfer des Claude-Codes |
| **Groq** (`openai/gpt-oss-120b`) | die KI **im Produkt**: liest E-Mails (nur Demo-Daten) |
| Design-Skills (Impeccable, UI/UX Pro Max, Taste) | Gestaltungsregeln für die Oberfläche |

## Arbeitsweise: zwei KIs, gegenseitige Prüfung

1. **Plan:** Claude schreibt den Plan, Codex bewertet ihn mit Punkten (0–10) und konkreten Fehlern. 9 Runden bis 10/10. Codex fand u. a.: ein inaktiver Vertrag hätte eine Unklarheit verstecken können; eine gesenkte Schwelle hätte ein anderes Gebäude „eindeutig“ machen können.
2. **Bau:** Jedes Modul wird von der jeweils anderen KI geprüft. Codex fand im Claude-Code echte Fehler (z. B. eine gefälschte Freigabe konnte eingeschleust werden; eine Notfall-Formulierung konnte als „keine Schadenmeldung“ enden). Claude fand im Codex-Code z. B. falsche Treffer bei „oder“.
3. **Regeln für die KIs:** nie automatisch senden, Unsicherheit sichtbar machen, nur kostenlose Werkzeuge, Schlüssel nur in `.env`, Arbeitsschritte ehrlich protokollieren.

## Was ich selbst entschieden, geprüft oder angepasst habe

**Entscheidungen (im Verlauf, belegt im Protokoll):**
- Groq als KI-Anbieter; keine lokale KI.
- Deutsche Etagen-Zählweise (EG = Erdgeschoss) und eine strenge Regel: fehlende oder unklare Etage → immer nachfragen.
- Unbekannte Absenderadresse: nicht blockieren, sondern deutliche Warnung und drei Optionen für die Sachbearbeitung (antworten / von registrierter Adresse schreiben lassen / anrufen, nur wenn eine Nummer bekannt ist).
- Eigene Oberfläche statt Streamlit, Fokus auf einen nachvollziehbaren Ablauf; n8n als sichtbarer Prozess.

**Selbst geprüft:** *[Mithul: bitte vor dem Versand ehrlich ergänzen – z. B. „Plan gelesen und freigegeben“, „Testfälle S1–S10 in der Oberfläche durchgeklickt“, „Zuordnung der Beispiel-E-Mail nachgerechnet“, „Antworttexte sprachlich geprüft“, „n8n-Workflow ausgeführt“. Nur eintragen, was wirklich gemacht wurde.]*

**Selbst angepasst:** *[Mithul: ergänzen, falls Texte/Regeln von Hand geändert wurden.]*
