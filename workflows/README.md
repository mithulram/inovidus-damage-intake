# n8n-Workflow „Schadenmeldung – KI-gestützte Erfassung“

Getestet mit **n8n 2.48.5** (selbst gehostet, lokal). Datei: `n8n_schadenmeldung.json`.

## Was der Workflow macht

`E-Mail eingegangen` (Webhook) → `E-Mail vorbereiten` → `1 Verstehen` → `2 Zuordnung im ERP` → `3 Frühere Vorgänge` → `4 Dringlichkeit` → `5 Antwortentwurf (nie senden)` → `6 Interne Aufgabe` → `Notfall?` → `Status?` → `In Prüfliste ablegen`

- Jeder Schritt ist ein HTTP-Knoten, der genau einen Schritt im Python-Dienst aufruft (`POST /api/steps/{name}`). Ein Test stellt sicher, dass diese Kette dasselbe Ergebnis liefert wie `POST /api/process`.
- **n8n entscheidet nichts.** Die Verzweigungen lesen nur `status` und `urgency.level`. Die Regeln stehen in `config/rules.yaml`.
- n8n ruft **nie** `/api/approve` auf. Freigaben gibt es nur im Prüfplatz.
- Der API-Schlüssel für Groq bleibt im Python-Dienst (`.env`), nicht in n8n.
- Produktion: Der deaktivierte Knoten „Postfach (Produktion, aus)“ ersetzt den Webhook; „Bereitschaft alarmieren“ zeigt, wo SMS/Anruf hingehört.

## Ausprobieren

```bash
uv run intake-ui                                  # 1. Dienst starten (Port 8000)
npx n8n@2.48.5                                    # 2. n8n starten (Port 5678), Konto anlegen
# 3. In n8n: Workflows → Import from File → n8n_schadenmeldung.json → Publish
```

```bash
curl -s -X POST http://localhost:5678/webhook/schadenmeldung \
  -H 'Content-Type: application/json' \
  -d '{"subject":"Wasserschaden Küche, Musterstraße 12","body":"Hallo, seit gestern läuft Wasser unter unserer Spüle aus. Der Küchenunterschrank ist bereits aufgequollen. Wir wohnen in der Musterstr. 12, zweite Etage links. Bitte dringend jemanden schicken. Fotos sind vorhanden. Viele Grüße, Max Mustermann","provider":"offline"}'
```

Der Vorgang erscheint danach im Prüfplatz unter **Posteingang → Prüfliste**. Optional im JSON: `"provider": "recorded"` oder `"groq"`, `"scenario_id": "S3"` (wendet die Daten-/Regeländerungen eines Testfalls an).

Die Dienst-Adresse steht im Knoten „E-Mail vorbereiten“ (`api_url`, Standard `http://127.0.0.1:8000`).

## Bildschirmfotos

- Überblick: `../docs/screenshots/n8n_workflow_overview.webp`
- Ausführungen: `../docs/screenshots/n8n_executions.webp`
- Was „1 Verstehen“ liest und zurückgibt: `../docs/screenshots/n8n_node_verstehen.webp`
- Zuordnung im Detail: `../docs/screenshots/n8n_node_zuordnung.webp`
