#!/bin/bash
# Agent Council — install git hooks into a target repo.
#
# Copies hooks/pre-push into <target-repo>/.git/hooks/pre-push so a push from an
# unclaimed worktree prints an advisory warning (non-blocking by default).
#
#   ./bin/install-hooks.sh [TARGET_REPO]   # default: current git repo
#
# The hook is advisory. To make an unclaimed push fail, the developer sets
# COUNCIL_PREPUSH_BLOCK=1 in their environment.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOK_SRC="$ROOT/hooks/pre-push"

TARGET="${1:-$(git rev-parse --show-toplevel 2>/dev/null || true)}"
if [ -z "$TARGET" ] || [ ! -d "$TARGET/.git" ]; then
  echo "install-hooks: '$TARGET' is not a git repo. Pass a target repo path." >&2
  exit 1
fi

HOOK_DST="$TARGET/.git/hooks/pre-push"
if [ -e "$HOOK_DST" ] && ! grep -q "Agent Council" "$HOOK_DST" 2>/dev/null; then
  cp "$HOOK_DST" "$HOOK_DST.pre-council.bak"
  echo "install-hooks: existing pre-push backed up to $HOOK_DST.pre-council.bak"
fi
cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"
echo "install-hooks: installed pre-push into $TARGET/.git/hooks/"
