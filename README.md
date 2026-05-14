# Agent Council Starter

A tiny, file-based coordination layer for teams running multiple AI coding agents
across IDEs, desktops, terminals, and repositories.

It gives every agent a shared ritual:

1. See what other agents are doing.
2. Log session start.
3. Claim the worktree you are about to edit (a red/yellow/green traffic light).
4. Work normally; heartbeat the claim while you work.
5. Log session end and release the claim.
6. Let a doctor command flag stale state, skipped closeouts, drift, and lease collisions.

This starter is deliberately local-first. It uses plain YAML and JSONL files,
so it works with any agent that can read files and run shell commands.

## What This Is

Agent Council is not a chat app, queue, database, or orchestration framework. It
is a lightweight coordination substrate:

- `ledger.jsonl` is the local append-only event stream.
- `projects/*.yaml` are human-readable project cards.
- `agents/*.yaml` are agent identity cards.
- `current-state/*.yaml` is generated from the ledger, project cards, and git.
- `claims/*.yaml` are short-lived resource leases — the traffic-control layer
  that stops two agents editing the same worktree at once. Auto-expire 30 min
  after the last heartbeat, so a crashed agent never blocks a lane forever.
- `doctor` reports stale sessions, missing references, branch/head drift, stale
  leases, and lease collisions.
- `session_id` plus `parent_session_id` tracks root agents and sub-agents to
  any depth.
- `steward` optionally runs a local read-mostly summary loop with deterministic
  checks or a local Ollama/Gemma-style model.

## Quick Start

```bash
git clone <your-repo-url> agent-council-starter
cd agent-council-starter

./bin/council.py doctor

./bin/session.sh start \
  --agent codex \
  --harness openai-desktop \
  --project example-app \
  --summary "Implement the next small feature"

# Claim the worktree before writing in it. GREEN = go, RED = another agent
# holds it (use your own `git worktree` instead). Heartbeat while you work.
./bin/traffic.sh acquire \
  --agent codex --harness openai-desktop \
  --resource "$(pwd)" --intent "Implement the next small feature"

./bin/session.sh end \
  --agent codex \
  --harness openai-desktop \
  --project example-app \
  --summary "Implemented the feature and ran tests" \
  --files "src/app.ts,tests/app.test.ts" \
  --issues "42" \
  --prs "" \
  --blockers "" \
  --next "Open a PR after one more review pass"

./bin/traffic.sh release --agent codex --resource "$(pwd)"
```

## Traffic Control

`session` records *that* an agent is working; it does not stop two agents from
editing the same working directory. Claims do.

```bash
./bin/traffic.sh acquire --agent codex --harness openai-desktop \
  --resource "$(pwd)" --intent "what you will change here"
./bin/traffic.sh heartbeat --agent codex --resource "$(pwd)"   # extend while working
./bin/traffic.sh check --agent codex --resource "$(pwd)"        # GREEN/YELLOW/RED, no mutation
./bin/traffic.sh board                                         # all leases + collisions
./bin/traffic.sh release --agent codex --resource "$(pwd)"
```

A claim is a lease on a resource — almost always a worktree path. It is atomic
(`O_EXCL` create), auto-expires 30 minutes after the last heartbeat, and is
keyed to the worktree path: two agents in the same repo via separate
`git worktree` directories never collide. `board` and `doctor` flag overlapping
live leases.

## Sub-Agent Trees

When an agent spawns another agent, pass the parent's session id:

```bash
./bin/session.sh start \
  --agent verifier-1 \
  --harness local-runner \
  --project example-app \
  --parent-session-id example-app-codex-20260101T000000Z-abcd1234 \
  --role verifier \
  --scope "tests only" \
  --summary "Verify the parser tests"
```

Every nested worker gets its own `session_id`. The Council stores the lineage as
plain parent pointers, so depth can be root -> worker -> verifier -> fixer -> ...
without a special database.

```bash
./bin/query.sh tree example-app
```

## Optional Local Steward

Run a one-shot Steward report:

```bash
./bin/steward.sh --project example-app --no-model
```

Use a local model through Ollama:

```bash
COUNCIL_STEWARD_MODEL=gemma3:4b ./bin/steward.sh --project example-app
```

Run it continuously while the machine is awake:

```bash
./bin/steward.sh --project example-app --watch --interval 900
```

Reports are written to `.council/steward/reports/` and are ignored by git.
The Steward is intentionally read-mostly: it reports stale sessions, active
alerts, and sub-agent lineage issues, but it does not mutate projects or issue
trackers.

## Repository Layout

```text
agent-council-starter/
├── bin/
│   ├── council.py
│   ├── session.sh
│   ├── traffic.sh
│   ├── doctor.sh
│   ├── current-state.sh
│   ├── query.sh
│   ├── steward.sh
│   └── dogfood-smoke.sh
├── .council/
│   ├── manifest.yaml
│   ├── ledger.example.jsonl
│   ├── agents/
│   ├── projects/
│   ├── claims/
│   └── current-state/
├── docs/
│   ├── AGENT_INSTRUCTIONS_SNIPPET.md
│   ├── AGENTIC_FRAMEWORK.md
│   ├── HEARTBEAT_LAUNCHD.md
│   ├── LOCAL_STEWARD.md
│   ├── SUB_AGENT_LINEAGE.md
│   ├── VAULT_AND_STORAGE.md
│   └── TEAM_ROLLOUT.md
└── examples/
    └── AGENTS.md
```

## Cross-IDE And Cross-Project Use

This is designed for multiple IDEs and agent harnesses at the same time:

- Codex Desktop
- Claude Code or Claude Desktop
- Gemini or Antigravity
- Cursor
- terminal-based agents
- CI-style local runners

Each IDE writes to the same local Council files, so a session started in Cursor
is visible to a later Codex or Claude session.

## Cross-Project Use

By default, this repo stores state in its own `.council/` directory. For a real
team, set `COUNCIL_HOME` to one shared local path:

```bash
export COUNCIL_HOME="$HOME/.agent-council"
```

Then copy `.council/` there:

```bash
mkdir -p "$COUNCIL_HOME"
cp -R .council/* "$COUNCIL_HOME"/
cp "$COUNCIL_HOME/ledger.example.jsonl" "$COUNCIL_HOME/ledger.jsonl"
```

Any project can then point its `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md` at:

```bash
$COUNCIL_HOME/session.sh start ...
$COUNCIL_HOME/session.sh end ...
```

## Safety

This repo contains only generic sample data. Before publishing:

```bash
./bin/sanitize-check.sh
```

The checker scans for common private/company markers and absolute local paths.
Add your own organization-specific forbidden strings before sharing.

## License

MIT, or replace with your team's preferred license.
