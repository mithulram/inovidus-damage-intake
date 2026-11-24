#!/bin/sh
# Send one test e-mail into n8n:  ./scripts/send_test_email.sh local   (n8n on this Mac)
# Optional second argument: your own text, e.g. ./scripts/send_test_email.sh local "Hallo, im Bad tropft es ..."
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BODY="${2:-Hallo, seit gestern läuft unter meiner Spüle Wasser aus. Musterstraße 12, zweite Etage links. Viele Grüße, Max Mustermann}"
case "$1" in
  local) URL=http://localhost:5678/webhook/schadenmeldung; KEY="$(cat "$ROOT/private/.local_webhook_token")" ;;
  *) echo "usage: $0 local [text]"; exit 1 ;;
esac
BODY_JSON=$(printf '%s' "$BODY" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')
curl -s -X POST "$URL" -H "Content-Type: application/json" -H "X-Webhook-Token: $KEY" \
  -d "{\"subject\":\"Schadenmeldung\",\"body\":$BODY_JSON,\"sender_email\":\"max.mustermann@example.org\"}"
echo
