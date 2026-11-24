#!/bin/sh
# Everything on this computer: the app (http://127.0.0.1:8000) and n8n (http://localhost:5678).
# Needs: uv, Node.js, and n8n installed once:  mkdir -p ~/.n8n-inovidus/app && cd ~/.n8n-inovidus/app && npm i n8n@2.48.5
# n8n login: owner@intake-demo.example / Demo1234 (created on the first start). Test e-mail: ./scripts/send_test_email.sh local
# Stop with Ctrl+C.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
N8N_APP="$HOME/.n8n-inovidus/app"
DATA="$HOME/.n8n-inovidus/data"
N8N="$N8N_APP/node_modules/.bin/n8n"
[ -x "$N8N" ] || { echo "n8n not installed: mkdir -p $N8N_APP && cd $N8N_APP && npm i n8n@2.48.5"; exit 1; }
TMP="$(mktemp -d)"
mkdir -p "$DATA"

# webhook key for local test e-mails (created once, kept out of git)
KEYFILE="$ROOT/private/.local_webhook_token"
[ -s "$KEYFILE" ] || { mkdir -p "$ROOT/private"; echo "local-demo-$(openssl rand -hex 6)" > "$KEYFILE"; }

export N8N_USER_FOLDER="$DATA" N8N_PORT=5678 N8N_HOST=localhost N8N_DIAGNOSTICS_ENABLED=false \
  N8N_VERSION_NOTIFICATIONS_ENABLED=false N8N_TEMPLATES_ENABLED=false N8N_HIRING_BANNER_ENABLED=false \
  N8N_SECURE_COOKIE=false GENERIC_TIMEZONE=Europe/Berlin N8N_DEFAULT_LOCALE=en

# the same workflow as online, pointed at the local app
INTAKE_API_URL=http://127.0.0.1:8000 INTAKE_SERVICE_TOKEN="" node "$ROOT/deploy/n8n/configure.mjs" \
  "$ROOT/workflows/n8n_schadenmeldung.json" "$TMP/workflow.json"
INTAKE_WEBHOOK_TOKEN="$(cat "$KEYFILE")" node "$ROOT/deploy/n8n/credentials.mjs" "$TMP/credentials.json"
"$N8N" import:credentials --input="$TMP/credentials.json" >/dev/null
"$N8N" import:workflow --input="$TMP/workflow.json" >/dev/null
"$N8N" publish:workflow --id=iM8N72bLtuYUcMK3 >/dev/null
rm -rf "$TMP"

(cd "$ROOT" && uv run intake-ui) &
APP=$!
"$N8N" start &
PID=$!
trap 'kill $APP $PID 2>/dev/null' INT TERM EXIT

for i in $(seq 1 90); do
  curl -sf http://localhost:5678/healthz/readiness >/dev/null 2>&1 && break
  sleep 2
done
# first start only: create the owner login (ignored when it exists)
curl -s -o /dev/null -X POST http://localhost:5678/rest/owner/setup -H 'Content-Type: application/json' \
  -d '{"email":"owner@intake-demo.example","firstName":"Demo","lastName":"Owner","password":"Demo1234"}' || true
echo ""
echo "Ready:  App  http://127.0.0.1:8000   (no password locally)"
echo "        n8n  http://localhost:5678   owner@intake-demo.example / Demo1234"
echo "Test e-mail:  ./scripts/send_test_email.sh local      Stop with Ctrl+C."
wait
