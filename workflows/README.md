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
  -H "X-Webhook-Token: $N8N_WEBHOOK_TOKEN" \
  -d '{"subject":"Wasserschaden Küche, Musterstraße 12","body":"Hallo, seit gestern läuft Wasser unter unserer Spüle aus. Der Küchenunterschrank ist bereits aufgequollen. Wir wohnen in der Musterstr. 12, zweite Etage links. Bitte dringend jemanden schicken. Fotos sind vorhanden. Viele Grüße, Max Mustermann","provider":"offline"}'
```

Ohne gültigen Token antwortet n8n mit **403**. Mit Token kommt nur eine kurze Quittung zurück (`case_id`, `status`, `urgency`) – den vollständigen Vorgang sieht man nur im (passwortgeschützten) Prüfplatz. Lokal: Zugangsdaten-Eintrag „Intake Webhook Token“ (Header `X-Webhook-Token`) in n8n anlegen.

Der Vorgang erscheint danach im Prüfplatz unter **Posteingang → Prüfliste**. Optional im JSON: `"provider": "recorded"` oder `"groq"`, `"scenario_id": "S3"` (wendet die Daten-/Regeländerungen eines Testfalls an).

Die Dienst-Adresse steht im Knoten „E-Mail vorbereiten“ (`api_url`, Standard `http://127.0.0.1:8000`).

## Bildschirmfotos

- Überblick: `../docs/screenshots/n8n_workflow_overview.webp`
- Ausführungen: `../docs/screenshots/n8n_executions.webp`
- Was „1 Verstehen“ liest und zurückgibt: `../docs/screenshots/n8n_node_verstehen.webp`
- Zuordnung im Detail: `../docs/screenshots/n8n_node_zuordnung.webp`

## English

The workflow is the visible process: one node per step, each calling one step of the Python service; n8n only routes (`status`, `urgency.level`) and never approves. The webhook requires the header `X-Webhook-Token` (403 without it) and answers with a short receipt only. Hosted version: see `render.yaml` and `deploy/n8n/` – the owner account and the webhook credential are created from Render-generated secrets on every start.
