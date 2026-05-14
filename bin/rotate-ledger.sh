#!/bin/bash
# Agent Council — Ledger rotation.
#
# ledger.jsonl is append-only and grows forever. This archives every event from
# before the current month into .council/ledger-archive/ledger-YYYY-MM.jsonl and
# leaves the live ledger holding only the current month. Safe to run any time;
# a no-op when there is nothing older than this month. Cron it monthly, or let
# the warden's schedule call it.
#
#   ./bin/rotate-ledger.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$SCRIPT_DIR/council.py" rotate-ledger "$@"
