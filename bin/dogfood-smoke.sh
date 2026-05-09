#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

cp -R "$ROOT/.council/." "$TMP_HOME/"

run_council() {
  COUNCIL_HOME="$TMP_HOME" "$@"
}

root_output="$(mktemp)"
child_output="$(mktemp)"
grandchild_output="$(mktemp)"
trap 'rm -rf "$TMP_HOME" "$root_output" "$child_output" "$grandchild_output"' EXIT

run_council "$ROOT/bin/session.sh" start \
  --agent codex \
  --harness openai-desktop \
  --project example-app \
  --summary "Root cross-IDE smoke session" \
  --role lead \
  --scope "lineage smoke" >"$root_output"

root_id="$(python3 - "$root_output" <<'PY'
import pathlib
import re
import sys
text = pathlib.Path(sys.argv[1]).read_text()
print(re.search(r"Session id: (\S+)", text).group(1))
PY
)"

run_council "$ROOT/bin/session.sh" start \
  --agent claude \
  --harness claude-code \
  --project example-app \
  --parent-session-id "$root_id" \
  --summary "Child worker smoke session" \
  --role worker \
  --scope "docs only" >"$child_output"

child_id="$(python3 - "$child_output" <<'PY'
import pathlib
import re
import sys
text = pathlib.Path(sys.argv[1]).read_text()
print(re.search(r"Session id: (\S+)", text).group(1))
PY
)"

run_council "$ROOT/bin/session.sh" start \
  --agent gemini \
  --harness gemini-cli \
  --project example-app \
  --parent-session-id "$child_id" \
  --summary "Grandchild verifier smoke session" \
  --role verifier \
  --scope "tree inspection" >"$grandchild_output"

grandchild_id="$(python3 - "$grandchild_output" <<'PY'
import pathlib
import re
import sys
text = pathlib.Path(sys.argv[1]).read_text()
print(re.search(r"Session id: (\S+)", text).group(1))
PY
)"

run_council "$ROOT/bin/session.sh" end \
  --agent gemini \
  --harness gemini-cli \
  --project example-app \
  --session-id "$grandchild_id" \
  --summary "Grandchild verifier closed cleanly" \
  --files "" \
  --blockers "" \
  --next "Child worker can close" >/dev/null

run_council "$ROOT/bin/query.sh" tree example-app | tee "$TMP_HOME/tree.out"
grep -q "depth=2" "$TMP_HOME/tree.out"

run_council "$ROOT/bin/steward.sh" --project example-app --no-model >/dev/null
test -f "$TMP_HOME/steward/reports/latest.md"

echo "Dogfood smoke passed."
