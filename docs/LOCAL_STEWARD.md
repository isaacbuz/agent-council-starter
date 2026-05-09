# Local Steward

The Local Steward is an optional read-mostly process for keeping Council state
fresh while your machine is awake.

It should:

- read the ledger, project cards, current-state files, and sub-agent lineage
- flag stale sessions and abandoned child agents
- summarize active alerts
- write reports under `.council/steward/reports/`
- avoid mutating repositories, issue trackers, pull requests, or deployments

## One-Shot Mode

```bash
./bin/steward.sh --project example-app --no-model
```

This uses deterministic checks only.

## Local Model Mode

If you run Ollama locally, the Steward can ask a local Gemma-style model for a
short report:

```bash
COUNCIL_STEWARD_MODEL=gemma3:4b ./bin/steward.sh --project example-app
```

If Ollama is unavailable or the model fails, it falls back to deterministic
checks.

## Running Process Mode

For a local always-available Steward:

```bash
./bin/steward.sh --project example-app --watch --interval 900
```

This writes a fresh report every 15 minutes. Use launchd if you want it to start
on login.

## Suggested Permissions

Keep the Steward read-mostly:

- allowed: read Council files
- allowed: write Steward reports
- allowed: run doctor/current-state/tree commands
- gated: edit project cards
- blocked: push code, merge pull requests, close issues, deploy, or write
  external comments without human confirmation

## Good Report Questions

- Which sessions are still open?
- Which child agents are abandoned?
- Which root workstreams have too many active branches?
- Which alerts are stale or overdue?
- What is the next safest action for a human or lead agent?
