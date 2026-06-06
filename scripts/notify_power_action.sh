#!/usr/bin/env bash
# Notify configured email recipients before a host reboot or shutdown (SSH / sudo).
#
# Usage:
#   ./scripts/notify_power_action.sh reboot
#   ./scripts/notify_power_action.sh shutdown "ssh:admin"
#
# Requires CRON_NOTIFY_SECRET and EMAIL_ALERTS_ENABLED=true in the bot .env.
# From the NAS host (published port):
#   CRON_NOTIFY_SECRET=... ./scripts/notify_power_action.sh reboot "$(whoami)"
#
# Or without a published port:
#   CRON_NOTIFY_MODE=docker ./scripts/notify_power_action.sh shutdown "$(whoami)"

set -euo pipefail

ACTION="${1:?Usage: $0 reboot|shutdown [initiated_by]}"
INITIATED_BY="${2:-ssh:$(whoami)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${REPO_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source "${REPO_ROOT}/.env"
  set +a
fi

SECRET="${CRON_NOTIFY_SECRET:?Set CRON_NOTIFY_SECRET in .env or environment}"
HOST="${CRON_NOTIFY_HOST:-127.0.0.1}"
PORT="${CRON_NOTIFY_PORT:-18765}"
CONTAINER="${CRON_NOTIFY_CONTAINER:-nas-telegram-bot}"
MODE="${CRON_NOTIFY_MODE:-auto}"

ACTION="$(echo "${ACTION}" | tr '[:upper:]' '[:lower:]')"
if [[ "${ACTION}" != "reboot" && "${ACTION}" != "shutdown" ]]; then
  echo "action must be reboot or shutdown" >&2
  exit 2
fi

_json_body() {
  python3 -c 'import json,sys; print(json.dumps({"secret":sys.argv[1],"action":sys.argv[2],"initiated_by":sys.argv[3]}))' \
    "${SECRET}" "${ACTION}" "${INITIATED_BY}"
}

post_host() {
  curl -fsS -X POST \
    -H "Content-Type: application/json" \
    -d "$(_json_body)" \
    "http://${HOST}:${PORT}/power-notify"
}

post_docker() {
  docker exec "${CONTAINER}" curl -fsS -X POST \
    -H "Content-Type: application/json" \
    -d "$(_json_body)" \
    "http://127.0.0.1:${PORT}/power-notify"
}

case "${MODE}" in
  host)
    post_host
    ;;
  docker)
    post_docker
    ;;
  auto)
    if curl -fsS "http://${HOST}:${PORT}/health" >/dev/null 2>&1; then
      post_host
    else
      post_docker
    fi
    ;;
  *)
    echo "Unknown CRON_NOTIFY_MODE=${MODE} (use host, docker, or auto)" >&2
    exit 2
    ;;
esac

echo "Power-action email notification queued (${ACTION})."
