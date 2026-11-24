# n8n-Workflow „Damage report – AI-assisted intake (Schadenmeldung – KI-gestützte Erfassung)“

Getestet mit **n8n 2.48.5** (selbst gehostet, lokal). Datei: `n8n_schadenmeldung.json`.

## Was der Workflow macht

`E-mail received` (Webhook) → `Prepare e-mail` → `1 Understand` → `2 Match to contract` → `3 Earlier cases` → `4 Urgency` → `5 Reply draft – never sent` → `6 Internal task` → `Emergency?` → `Which status?` → `Store in review list`

Jeder Knoten heißt zuerst englisch, dahinter in Klammern deutsch (z. B. „2 Match to contract (Zuordnung zum Vertrag)“); jede Notiz steht auf Englisch und Deutsch.

- Jeder Schritt ist ein HTTP-Knoten, der genau einen Schritt im Python-Dienst aufruft (`POST /api/steps/{name}`). Ein Test stellt sicher, dass diese Kette dasselbe Ergebnis liefert wie `POST /api/process`.
- **n8n entscheidet nichts.** Die Verzweigungen lesen nur `status` und `urgency.level`. Die Regeln stehen in `config/rules.yaml`.
- n8n ruft **nie** `/api/approve` auf. Freigaben gibt es nur im Prüfplatz.
- Der API-Schlüssel für Groq bleibt im Python-Dienst (`.env`), nicht in n8n.
- Produktion: Der deaktivierte Knoten „Mailbox – production, switched off (Postfach – Produktion, aus)“ ersetzt den Webhook; „Alert on-call team (Bereitschaft alarmieren)“ zeigt, wo SMS/Anruf hingehört.

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

Ohne gültigen Token antwortet n8n mit **403**. Mit Token kommt nur eine kurze Quittung zurück (`case_id`, `status`, `urgency`) – den vollständigen Vorgang sieht man nur im (passwortgeschützten) Prüfplatz. Lokal: in n8n unter *Credentials* einen Eintrag „Header Auth“ mit dem Namen `X-Webhook-Token` und einem eigenen Wert anlegen, im Knoten „E-mail received“ auswählen und denselben Wert im curl-Befehl verwenden. (`scripts/n8n_local.sh` und `scripts/demo_local.sh` erledigen das automatisch.)

Der Vorgang erscheint danach im Prüfplatz unter **Posteingang → Prüfliste**. Optional im JSON: `"provider": "recorded"` oder `"groq"`, `"scenario_id": "S3"` (wendet die Daten-/Regeländerungen eines Testfalls an).

Schneller: `./scripts/demo_local.sh` startet Dienst und n8n zusammen; `./scripts/n8n_local.sh` startet nur n8n und verbindet es mit der Online-Version.

Die Dienst-Adresse steht im Knoten „Prepare e-mail (E-Mail vorbereiten)“ (`api_url`, Standard `http://127.0.0.1:8000`).

## Bildschirmfotos

- Überblick: `../docs/guide/14_n8n_ablauf.jpg`
- Ausführungen: `../docs/guide/15_n8n_ausfuehrungen.jpg`

## English

The workflow is the visible process: one node per step, each calling one step of the Python service; n8n only routes (`status`, `urgency.level`) and never approves. The webhook requires the header `X-Webhook-Token` (403 without it) and answers with a short receipt only. Hosted version: see `render.yaml` and `deploy/n8n/` – the owner account and the webhook credential are created from Render-generated secrets on every start.
