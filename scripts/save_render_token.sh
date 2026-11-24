#!/bin/sh
# Saves the Render app's INTAKE_SERVICE_TOKEN into .env (gitignored) as INTAKE_RENDER_SERVICE_TOKEN.
# 1) start this script  2) copy the token on Render (copy icon)  3) press Enter here.
cd "$(dirname "$0")/.."
printf "Now click the copy icon next to INTAKE_SERVICE_TOKEN on Render, then press Enter here ... "
read _
TOKEN="$(pbpaste | tr -d '\r\n')"
case "$TOKEN" in
  ""|*" "*|*"INTAKE"*) echo "That does not look like the token (clipboard: empty or text). Copy it again and rerun."; exit 1 ;;
esac
grep -v '^INTAKE_RENDER_SERVICE_TOKEN=' .env > .env.tmp 2>/dev/null || true
mv .env.tmp .env
printf 'INTAKE_RENDER_SERVICE_TOKEN=%s\n' "$TOKEN" >> .env
code=$(curl -s -o /dev/null -m 120 -w "%{http_code}" -H "X-Intake-Token: $TOKEN" https://inovidus-intake.onrender.com/api/scenarios)
[ "$code" = 200 ] && echo "saved – the Render app accepts it (200)" || echo "saved, but the Render app answered $code – copy the token again and rerun"
