#!/bin/bash
# Agent Council — Traffic Control (resource leases / "traffic lights").
#
# `session` records THAT an agent is working; traffic claims stop two agents
# from editing the SAME working directory at once. Acquire a lease before you
# write, heartbeat while you work, release when done. Leases auto-expire 30 min
# after their last heartbeat so a crashed agent never blocks a lane forever.
#
#   traffic.sh acquire   --agent X --harness Y --resource <path> [--intent "..."] [--ttl 1800]
#   traffic.sh heartbeat --agent X --resource <path>     # extend your lease while working
#   traffic.sh release   --agent X --resource <path>     # release when done
#   traffic.sh check     [--agent X] --resource <path>   # GREEN/YELLOW/RED, no mutation
#   traffic.sh board                                     # all leases + collisions
#   traffic.sh sweep                                     # drop expired leases
#
# Exit codes: 0 = green/ok, 1 = red (denied / held by another), 2 = collision (board).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$SCRIPT_DIR/council.py" claim "$@"
