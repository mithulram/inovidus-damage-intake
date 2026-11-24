#!/bin/sh
# Backup for the interview: n8n runs on this Mac, the app stays online on Render.
# E-mails sent to the local n8n are processed by the Render app and appear in its online review list.
#
#   ./scripts/n8n_local.sh            → n8n at http://localhost:5678 (login owner@intake-demo.example / Demo1234)
#
# Needs in .env (gitignored): INTAKE_RENDER_SERVICE_TOKEN = the INTAKE_SERVICE_TOKEN of the Render app.
# Optional: INTAKE_RENDER_URL (default https://inovidus-intake.onrender.com).
# Uses its own n8n data folder (~/.n8n-inovidus/render-data), so the all-local setup stays untouched.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
N8N_APP="$HOME/.n8n-inovidus/app"
DATA="$HOME/.n8n-inovidus/render-data"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

get_env() { grep -E "^$1=" "$ROOT/.env" 2>/dev/null | tail -1 | cut -d= -f2- | sed 's/^"//;s/"$//'; }
TOKEN="$(get_env INTAKE_RENDER_SERVICE_TOKEN)"
URL="$(get_env INTAKE_RENDER_URL)"; URL="${URL:-https://inovidus-intake.onrender.com}"
[ -n "$TOKEN" ] || { echo "INTAKE_RENDER_SERVICE_TOKEN missing in .env – run ./scripts/save_render_token.sh first"; exit 1; }
[ -x "$N8N_APP/node_modules/.bin/n8n" ] || { echo "n8n not installed: (mkdir -p $N8N_APP && cd $N8N_APP && npm i n8n@2.48.5)"; exit 1; }

# local webhook key (created once, kept in private/)
KEYFILE="$ROOT/private/.local_webhook_token"
[ -s "$KEYFILE" ] || { mkdir -p "$ROOT/private"; echo "local-demo-$(openssl rand -hex 6)" > "$KEYFILE"; }
WEBHOOK_TOKEN="$(cat "$KEYFILE")"

export N8N_USER_FOLDER="$DATA" N8N_PORT=5678 N8N_HOST=localhost N8N_DIAGNOSTICS_ENABLED=false \
  N8N_VERSION_NOTIFICATIONS_ENABLED=false N8N_TEMPLATES_ENABLED=false N8N_HIRING_BANNER_ENABLED=false \
  N8N_SECURE_COOKIE=false GENERIC_TIMEZONE=Europe/Berlin N8N_DEFAULT_LOCALE=en
mkdir -p "$DATA"
N8N="$N8N_APP/node_modules/.bin/n8n"

# same workflow as online, pointed at the Render app (the same scripts the hosted n8n uses)
echo "Waking the Render app (can take a minute) ..."
curl -s -o /dev/null -m 180 "$URL/api/health" || true
INTAKE_API_URL="$URL" INTAKE_SERVICE_TOKEN="$TOKEN" node "$ROOT/deploy/n8n/configure.mjs" "$ROOT/workflows/n8n_schadenmeldung.json" "$TMP/workflow.json"
INTAKE_WEBHOOK_TOKEN="$WEBHOOK_TOKEN" node "$ROOT/deploy/n8n/credentials.mjs" "$TMP/credentials.json"
"$N8N" import:credentials --input="$TMP/credentials.json" >/dev/null
"$N8N" import:workflow --input="$TMP/workflow.json" >/dev/null
"$N8N" publish:workflow --id=iM8N72bLtuYUcMK3 >/dev/null
rm -f "$TMP/credentials.json" "$TMP/workflow.json"

"$N8N" start &
PID=$!
trap 'kill $PID 2>/dev/null; rm -rf "$TMP"' INT TERM EXIT
for i in $(seq 1 90); do
  curl -sf http://localhost:5678/healthz/readiness >/dev/null 2>&1 && break
  sleep 2
done
# first start only: create the same owner login as online (ignored when it exists)
curl -s -o /dev/null -X POST http://localhost:5678/rest/owner/setup -H 'Content-Type: application/json' \
  -d '{"email":"owner@intake-demo.example","firstName":"Demo","lastName":"Owner","password":"Demo1234"}' || true
echo ""
echo "Ready: n8n http://localhost:5678  (owner@intake-demo.example / Demo1234)  →  app $URL"
echo "Test e-mail:  ./scripts/send_test_email.sh local"
echo "Stop with Ctrl+C."
wait $PID
