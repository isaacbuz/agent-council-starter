# Optional macOS Heartbeat

Agent Council does not need a long-running daemon. A lightweight heartbeat is
usually better.

The heartbeat should:

- run on login and every 15-30 minutes while the Mac is awake
- run `warden.sh` — the dumb janitor: sweep expired leases, prune long-ended
  agents from project cards, refresh manifest `active` flags, run `doctor.sh`
- regenerate current-state files
- run `rotate-ledger.sh` (a cheap no-op until the month rolls over)
- optionally render a session tree for diagnostics
- optionally run `steward.sh --no-model` or a local-model Steward report

### Warden vs Steward — both are safe to schedule

- **`warden.sh`** makes *deterministic* edits to council state only (sweeps
  leases, prunes ended agents, flips `active` flags). It never touches repos,
  issues, PRs, or external systems, and uses no model — pure mechanical chores.
  This is what keeps the council from rotting between sessions.
- **`steward.sh`** is read-mostly: it summarizes, it does not mutate.

Neither mutates anything outside `.council/`.

## Example Heartbeat Script

Create `bin/heartbeat.sh`:

```bash
#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

for project in .council/projects/*.yaml; do
  slug="$(basename "$project" .yaml)"
  ./bin/current-state.sh "$slug" >/dev/null || true
done

./bin/warden.sh || true          # sweep leases, prune stale cards, refresh flags, doctor
./bin/rotate-ledger.sh || true   # no-op until the month rolls over
./bin/steward.sh --no-model || true
```

## Example LaunchAgent

Create `~/Library/LaunchAgents/com.example.agent-council-heartbeat.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.example.agent-council-heartbeat</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/absolute/path/to/agent-council-starter/bin/heartbeat.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>900</integer>
  <key>StandardOutPath</key>
  <string>/tmp/agent-council-heartbeat.out</string>
  <key>StandardErrorPath</key>
  <string>/tmp/agent-council-heartbeat.err</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.example.agent-council-heartbeat.plist
```
