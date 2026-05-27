#!/bin/sh
# Send a Watchtower-style notification to the NAS bot HTTP hook.
# Usage: ./scripts/notify_watchtower.sh "New update available for jellyfin"
#
# Requires CRON_NOTIFY_SECRET in environment or .env on the host.

set -e
MSG="${1:-Watchtower: update detected}"
SECRET="${CRON_NOTIFY_SECRET:?Set CRON_NOTIFY_SECRET}"
HOST="${CRON_NOTIFY_HOST:-127.0.0.1}"
PORT="${CRON_NOTIFY_PORT:-18765}"

curl -fsS -X POST "http://${HOST}:${PORT}/watchtower" \
  -H "Content-Type: application/json" \
  -d "{\"secret\":\"${SECRET}\",\"message\":\"${MSG}\"}"

echo "OK"
