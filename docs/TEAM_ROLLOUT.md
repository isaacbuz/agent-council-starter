# Team Rollout Guide

## Pitch

Agent Council is a lightweight coordination layer for teams using multiple AI
agents across multiple IDEs.

It answers:

- Who is working right now?
- **Can I safely edit this worktree, or is another agent already in it?**
- What did the last agent change?
- Which branch/head was the repo on?
- What issues or PRs were touched?
- What is blocked?
- What should the next agent do first?
- Which sub-agents were spawned, what they owned, and whether they closed out?

The hardest of these in practice is the second one: two agents editing the same
working directory clobber each other. **Traffic control** solves it — `traffic.sh
acquire` gives each agent a red/yellow/green light on a worktree before it
writes, leases auto-expire so a crashed agent never blocks a lane, and
`doctor.sh` flags collisions. See the README "Traffic Control" section.

## Pilot Plan

1. Choose one low-risk internal repository.
2. Add `.council/projects/<project>.yaml`.
3. Add `docs/AGENT_INSTRUCTIONS_SNIPPET.md` to the repo's agent instructions.
4. Ask every agent session to use `session.sh start/end` and `traffic.sh
   acquire/release` around its work.
5. Run `doctor.sh` at the start of standup or handoff.
6. Run `steward.sh --no-model` once per day for stale-session summaries.
7. After one week, review whether skipped closeouts, stale cards, or
   same-worktree collisions decreased.

## What To Avoid

- Do not store secrets.
- Do not store customer data.
- Do not paste incident payloads or private logs into the ledger.
- Do not make the heartbeat mutate GitHub, Jira, Linear, or production systems.
- Do not use this as a task tracker replacement; link out to the tracker.

## Suggested Demo

Open two IDEs:

1. Start a session from IDE A:

```bash
./bin/session.sh start --agent codex --harness ide-a --project example-app --summary "Refactor parser"
```

2. Start a session from IDE B:

```bash
./bin/session.sh start --agent claude --harness ide-b --project example-app --summary "Review parser tests"
```

3. Run:

```bash
./bin/doctor.sh example-app
./bin/query.sh tail 10
./bin/query.sh tree example-app
cat .council/current-state/example-app.yaml
```

The team should see both sessions, stale-session warnings if someone forgets to
close out, and the latest generated project state.
