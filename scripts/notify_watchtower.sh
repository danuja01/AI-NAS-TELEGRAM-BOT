#!/usr/bin/env bash
# Send a Watchtower-style notification to the NAS bot HTTP hook.
# Usage: ./scripts/notify_watchtower.sh "New update available for jellyfin"
#
# The hook listens inside the bot container (127.0.0.1:CRON_NOTIFY_PORT).
# From the NAS host: set CRON_NOTIFY_SECRET in .env, then either:
#   - publish port 127.0.0.1:18765 in docker-compose (default after update), or
#   - CRON_NOTIFY_MODE=docker (uses docker exec into nas-telegram-bot)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../.env"
  set +a
fi

MSG="${1:-Watchtower: update detected}"
SECRET="${CRON_NOTIFY_SECRET:?Set CRON_NOTIFY_SECRET in .env or environment}"
HOST="${CRON_NOTIFY_HOST:-127.0.0.1}"
PORT="${CRON_NOTIFY_PORT:-18765}"
CONTAINER="${CRON_NOTIFY_CONTAINER:-nas-telegram-bot}"
MODE="${CRON_NOTIFY_MODE:-auto}"

_json_body() {
  python3 -c 'import json,sys; print(json.dumps({"secret":sys.argv[1],"message":sys.argv[2]}))' \
    "$SECRET" "$MSG"
}

_curl_host() {
  curl -fsS --connect-timeout 3 -X POST "http://${HOST}:${PORT}/watchtower" \
    -H "Content-Type: application/json" \
    -d "$(_json_body)"
}

_curl_docker() {
  docker exec "$CONTAINER" curl -fsS --connect-timeout 3 \
    -X POST "http://127.0.0.1:${PORT}/watchtower" \
    -H "Content-Type: application/json" \
    -d "$(_json_body)"
}

_host_hook_up() {
  curl -fsS --connect-timeout 2 "http://${HOST}:${PORT}/health" >/dev/null 2>&1
}

_container_running() {
  docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"
}

_check_hook() {
  if [[ "$MODE" == "docker" ]]; then
    _curl_docker
    return
  fi
  if [[ "$MODE" == "host" ]]; then
    if ! _host_hook_up; then
      echo "curl: host http://${HOST}:${PORT}/health unreachable (CRON_NOTIFY_MODE=host)" >&2
      echo "Run: docker compose up -d --force-recreate  (publishes 127.0.0.1:${PORT})" >&2
      exit 7
    fi
    _curl_host
    return
  fi
  # auto: host port if published, else docker exec (typical NAS: bot in container, no host bind)
  if _host_hook_up; then
    _curl_host
    return
  fi
  if _container_running; then
    echo "Note: using docker exec ${CONTAINER} (host :${PORT} not published yet)" >&2
    _curl_docker
    return
  fi
  echo "curl: could not reach http://${HOST}:${PORT}/watchtower" >&2
  echo "Fix: set CRON_NOTIFY_SECRET in .env, restart bot, or run with CRON_NOTIFY_MODE=docker" >&2
  exit 7
}

_check_hook
echo "OK"
