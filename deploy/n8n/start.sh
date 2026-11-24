#!/bin/sh
# Start script for the hosted n8n (see deploy/n8n/Dockerfile). Required env: INTAKE_API_URL, INTAKE_SERVICE_TOKEN,
# INTAKE_WEBHOOK_TOKEN, N8N_OWNER_EMAIL, N8N_OWNER_PASSWORD; PORT is provided by Render.
set -e
# Free plan = 512 MB for EVERYTHING. n8n starts a JS task-runner child next to the main process; together
# they exceeded the limit (Render "exceeded its memory limit", 23 Nov). Fixed caps keep both well below 512 MB:
# main ≤ 288 MB heap, runner ≤ 96 MB heap. Set here (not only in the dashboard) so an old value cannot win.
# Hosts with more memory can raise both caps with N8N_HEAP_MB / N8N_RUNNER_HEAP_MB.
export NODE_OPTIONS="--max-old-space-size=${N8N_HEAP_MB:-288}"
export N8N_RUNNERS_MAX_OLD_SPACE_SIZE="${N8N_RUNNER_HEAP_MB:-96}"
export N8N_RUNNERS_MAX_CONCURRENCY=2
export N8N_RUNNERS_GRANT_TOKEN_TTL=120   # slow CPU: the task runner needs longer than 30 s to connect
export EXECUTIONS_DATA_PRUNE=true EXECUTIONS_DATA_MAX_AGE=72 EXECUTIONS_DATA_PRUNE_MAX_COUNT=200
export N8N_DEFAULT_LOCALE=en       # n8n's own interface in English (workflow texts are German + English)
: "${INTAKE_API_URL:?INTAKE_API_URL missing}" "${N8N_OWNER_EMAIL:?missing}" "${N8N_OWNER_PASSWORD:?missing}"
node /opt/intake/configure.mjs /opt/intake/workflow.json /tmp/workflow.json
node /opt/intake/credentials.mjs /tmp/credentials.json
n8n import:credentials --input=/tmp/credentials.json
rm -f /tmp/credentials.json
n8n import:workflow --input=/tmp/workflow.json
n8n publish:workflow --id=iM8N72bLtuYUcMK3

# 1) private port: create the owner from secrets, then stop
#    (own ports: 5679 is n8n's internal task-broker port)
N8N_LISTEN_ADDRESS=127.0.0.1 N8N_PORT=5682 N8N_RUNNERS_BROKER_PORT=5683 n8n start &
PID=$!
trap 'kill "$PID" 2>/dev/null' EXIT   # never leave the bootstrap instance running
node -e '
const until = Date.now() + 600000;   // free plan = tiny CPU: first start can take 3–6 min
(async () => {
  for (;;) {
    try { if ((await fetch("http://127.0.0.1:5682/healthz/readiness")).ok) break; } catch {}
    if (Date.now() > until) { console.error("bootstrap n8n not ready after 10 min"); process.exit(1); }
    await new Promise((r) => setTimeout(r, 2000));
  }
  const r = await fetch("http://127.0.0.1:5682/rest/owner/setup", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: process.env.N8N_OWNER_EMAIL, firstName: "Demo", lastName: "Owner", password: process.env.N8N_OWNER_PASSWORD }) });
  console.log("owner setup:", r.status);
  // n8n rule: password 8–64 characters with at least one number and one capital letter
  if (!r.ok) { console.error("owner setup failed – check N8N_OWNER_PASSWORD (8+ chars, a number, a capital letter):", await r.text()); process.exit(2); }
})();'
kill "$PID"; wait "$PID" 2>/dev/null || true
trap - EXIT

# 2) public port: the real service
export N8N_PORT="${PORT:-5678}"
export N8N_LISTEN_ADDRESS=0.0.0.0
# public address: Render sets RENDER_EXTERNAL_URL; other hosts can set SPACE_HOST or WEBHOOK_URL
PUBLIC_URL="${RENDER_EXTERNAL_URL:-}"
[ -z "$PUBLIC_URL" ] && [ -n "${SPACE_HOST:-}" ] && PUBLIC_URL="https://$SPACE_HOST"
export WEBHOOK_URL="${WEBHOOK_URL:-${PUBLIC_URL:-http://localhost:$N8N_PORT}}/"
export N8N_EDITOR_BASE_URL="${N8N_EDITOR_BASE_URL:-$WEBHOOK_URL}"
exec n8n start
