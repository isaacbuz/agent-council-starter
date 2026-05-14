#!/bin/bash
# Agent Council — Warden (the dumb janitor; no LLM, safe to cron).
#
# Mechanical hygiene only: sweep expired leases, prune long-ended agents from
# project cards, recompute manifest `active` flags from ledger recency, then run
# doctor. Makes deterministic edits only — no judgement. Schedule it (cron or
# launchd) every 15-30 min so the council never rots between agent sessions.
#
#   ./bin/warden.sh
#
# See docs/HEARTBEAT_LAUNCHD.md for scheduling.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$SCRIPT_DIR/council.py" warden "$@"
