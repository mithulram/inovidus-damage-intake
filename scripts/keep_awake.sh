#!/bin/sh
# Keeps the hosted demo awake (Render free plan sleeps after 15 min without visits).
# Run it 30 minutes before the demo; stop with Ctrl+C after the interview.
APP=https://inovidus-intake.onrender.com/api/health
N8N=https://inovidus-n8n.onrender.com/healthz
while true; do
  a=$(curl -s -o /dev/null -m 120 -w "%{http_code}" "$APP")
  n=$(curl -s -o /dev/null -m 120 -w "%{http_code}" "$N8N")
  echo "$(date +%H:%M)  app=$a  n8n=$n   (200 = awake)"
  sleep 300
done
