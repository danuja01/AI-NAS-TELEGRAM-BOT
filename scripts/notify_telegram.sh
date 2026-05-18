#!/usr/bin/env bash
# Send a Telegram message (for cron / OMV UserScript jobs on the NAS host).
# Usage:
#   export TELEGRAM_BOT_TOKEN="..."
#   export TELEGRAM_CHAT_ID="123456789"
#   ./notify_telegram.sh "Job name" "ok" "Optional details"
#
# Or source values from BOT/.env next to this script.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/../.env"
  set +a
fi

TOKEN="${TELEGRAM_BOT_TOKEN:-${TELEGRAM_TOKEN:-}}"
CHAT="${TELEGRAM_CHAT_ID:-}"
JOB="${1:-cron}"
STATUS="${2:-unknown}"
MSG="${3:-}"

# First ALLOWED_USER_ID from comma list if TELEGRAM_CHAT_ID unset
if [[ -z "${CHAT}" && -n "${ALLOWED_USER_IDS:-}" ]]; then
  CHAT="${ALLOWED_USER_IDS%%,*}"
  CHAT="${CHAT// /}"
fi

if [[ -z "$TOKEN" || -z "$CHAT" ]]; then
  echo "Set TELEGRAM_BOT_TOKEN (or TELEGRAM_TOKEN) and TELEGRAM_CHAT_ID (or ALLOWED_USER_IDS)" >&2
  exit 1
fi

TEXT="🗓 *${JOB}*
Status: \`${STATUS}\`"
if [[ -n "$MSG" ]]; then
  TEXT+=$'\n'"${MSG}"
fi

curl -sS -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${CHAT}" \
  --data-urlencode "text=${TEXT}" \
  --data-urlencode "parse_mode=Markdown" \
  | grep -q '"ok":true' || { echo "Telegram API error" >&2; exit 2; }
