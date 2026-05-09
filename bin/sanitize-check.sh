#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FORBIDDEN=(
  "Disney"
  "AdOps"
  "Sentinel"
  "github.twdcgrid.net"
  ".AdOpsEngineering"
  "isaac.buziba"
  "dpo_adops"
  "BOAT-P-"
  "Airtable"
)

FAILED=0
for token in "${FORBIDDEN[@]}"; do
  if grep -RIn \
      --exclude-dir=.git \
      --exclude-dir=.council/current-state \
      --exclude-dir=.council/steward/reports \
      --exclude='sanitize-check.sh' \
      --exclude='ledger.jsonl' \
      "$token" "$ROOT" >/tmp/agent-council-sanitize-hit.txt 2>/dev/null; then
    echo "Forbidden token found: $token"
    cat /tmp/agent-council-sanitize-hit.txt
    FAILED=1
  fi
done

if grep -RIn \
    --exclude-dir=.git \
    --exclude-dir=.council/current-state \
    --exclude-dir=.council/steward/reports \
    --exclude='sanitize-check.sh' \
    --exclude='ledger.jsonl' \
    "/Users/" "$ROOT" >/tmp/agent-council-sanitize-path.txt 2>/dev/null; then
  echo "Absolute local path found:"
  cat /tmp/agent-council-sanitize-path.txt
  FAILED=1
fi

if [ "$FAILED" -eq 0 ]; then
  echo "Sanitize check passed."
fi

exit "$FAILED"
