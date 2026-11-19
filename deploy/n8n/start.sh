#!/bin/sh
# Start script for the hosted n8n (see Dockerfile). Required env: INTAKE_API_URL, INTAKE_SERVICE_TOKEN,
# INTAKE_WEBHOOK_TOKEN, N8N_OWNER_EMAIL, N8N_OWNER_PASSWORD; PORT is provided by Render.
set -e
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
const until = Date.now() + 180000;
(async () => {
  for (;;) {
    try { if ((await fetch("http://127.0.0.1:5682/healthz/readiness")).ok) break; } catch {}
    if (Date.now() > until) process.exit(1);
    await new Promise((r) => setTimeout(r, 2000));
  }
  const r = await fetch("http://127.0.0.1:5682/rest/owner/setup", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: process.env.N8N_OWNER_EMAIL, firstName: "Demo", lastName: "Owner", password: process.env.N8N_OWNER_PASSWORD }) });
  console.log("owner setup:", r.status);
  if (!r.ok) process.exit(2);
})();'
kill "$PID"; wait "$PID" 2>/dev/null || true
trap - EXIT

# 2) public port: the real service
export N8N_PORT="${PORT:-5678}"
export N8N_LISTEN_ADDRESS=0.0.0.0
export WEBHOOK_URL="${WEBHOOK_URL:-${RENDER_EXTERNAL_URL:-http://localhost:$N8N_PORT}}/"
exec n8n start
