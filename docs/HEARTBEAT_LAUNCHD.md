# Optional macOS Heartbeat

Agent Council does not need a long-running daemon. A lightweight heartbeat is
usually better.

The heartbeat should:

- run on login and every 10-15 minutes while the Mac is awake
- run `doctor.sh`
- regenerate current-state files
- optionally render a session tree for diagnostics
- optionally run `steward.sh --no-model` or a local-model Steward report
- avoid mutating repos, issues, PRs, or external systems

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

./bin/doctor.sh || true
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
