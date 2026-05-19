#!/usr/bin/env bash
# Create severity labels and apply them to security audit issues.
# Run locally as a user with repo write access:
#   gh auth login
#   ./scripts/apply_security_issue_labels.sh
# Optional: REPO=owner/name ./scripts/apply_security_issue_labels.sh

set -euo pipefail
REPO="${REPO:-danuja01/AI-NAS-TELEGRAM-BOT}"

create_label() {
  local name="$1" color="$2" desc="$3"
  if gh label list --repo "$REPO" --json name -q '.[].name' | grep -qx "$name"; then
    echo "Label exists: $name"
  else
    gh label create "$name" --repo "$REPO" --color "$color" --description "$desc"
    echo "Created: $name"
  fi
}

echo "Creating labels on $REPO ..."
create_label "critical" "b60205" "Security audit: critical severity"
create_label "high" "d93f0b" "Security audit: high severity"
create_label "medium" "fbca04" "Security audit: medium severity"
create_label "low" "0e8a16" "Security audit: low severity"
create_label "potential-risk" "5319e7" "Security audit: context-dependent risk"
create_label "security" "1d76db" "Security audit finding"

echo "Labeling issues ..."
gh issue list --repo "$REPO" --state all --limit 200 --json number,title \
  | jq -r '.[] | select(.title | test("^\\[(Critical|High|Medium|Low|Potential risk)\\]")) | "\(.number)\t\(.title)"' \
  | while IFS=$'\t' read -r num title; do
    case "$title" in
      "[Critical]"*) labels="critical,security" ;;
      "[High]"*)     labels="high,security" ;;
      "[Medium]"*)   labels="medium,security" ;;
      "[Low]"*)      labels="low,security" ;;
      "[Potential risk]"*) labels="potential-risk,security" ;;
      *) continue ;;
    esac
    echo "  #$num → $labels"
    gh issue edit "$num" --repo "$REPO" --add-label "$labels"
  done

echo "Finished."
