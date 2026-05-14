#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COUNCIL_HOME="${COUNCIL_HOME:-$ROOT/.council}"
LEDGER="$COUNCIL_HOME/ledger.jsonl"

case "${1:-}" in
  tail)
    N="${2:-20}"
    tail -"$N" "$LEDGER" | python3 -c '
import json, sys
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    e=json.loads(line)
    print(f"{e.get(\"ts\", \"\")[:16]} [{e.get(\"agent\", \"?\")}] {e.get(\"event\", \"?\")}: {e.get(\"summary\", \"\")[:100]}")
'
    ;;
  project)
    PROJECT="${2:?Usage: query.sh project <slug> [N]}"
    N="${3:-20}"
    grep "\"project\":\"$PROJECT\"" "$LEDGER" | tail -"$N" | python3 -c '
import json, sys
for line in sys.stdin:
    line=line.strip()
    if not line: continue
    e=json.loads(line)
    print(f"{e.get(\"ts\", \"\")[:16]} [{e.get(\"agent\", \"?\")}] {e.get(\"event\", \"?\")}: {e.get(\"summary\", \"\")[:100]}")
'
    ;;
  doctor)
    shift
    exec "$SCRIPT_DIR/doctor.sh" "$@"
    ;;
  current)
    shift
    exec "$SCRIPT_DIR/current-state.sh" "$@"
    ;;
  tree)
    shift
    exec "${PYTHON:-python3}" "$SCRIPT_DIR/council.py" tree "$@"
    ;;
  board)
    shift
    exec "${PYTHON:-python3}" "$SCRIPT_DIR/council.py" claim board "$@"
    ;;
  stats)
    shift
    exec "${PYTHON:-python3}" "$SCRIPT_DIR/council.py" stats "$@"
    ;;
  *)
    echo "Usage:"
    echo "  query.sh tail [N]"
    echo "  query.sh project <slug> [N]"
    echo "  query.sh doctor [project]"
    echo "  query.sh current [project]"
    echo "  query.sh tree [project]"
    echo "  query.sh board               # traffic-control leases + collisions"
    echo "  query.sh stats               # coordination + traffic metrics"
    ;;
esac
