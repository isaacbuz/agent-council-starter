# Does Agent Council Need Its Own Agentic Framework?

Not at first.

Agent Council should be coordination infrastructure that agents use, not another
autonomous agent competing for control.

## Keep The Core Boring

The core should stay:

- file vault
- append-only ledger
- session start/end wrapper
- doctor checks
- current-state generation
- optional heartbeat

That is enough to solve the main problem: agents can see what other agents are
doing across IDEs and projects.

## What To Avoid

Avoid giving the Council authority to:

- mutate project code
- close issues
- merge PRs
- trigger deploys
- decide ownership without a human or project agent
- rewrite agent instructions automatically

Those powers belong to the project-specific agents and human owner.

## Optional Phase Two: Council Steward

If the team wants more automation later, add a small "Council Steward" process
with read-mostly permissions. This starter includes `bin/steward.sh` for that
purpose.

- summarize yesterday's sessions
- detect stale open sessions
- detect stale alerts
- generate a daily handoff
- propose project-card updates
- ask for confirmation before mutating anything important
- summarize sub-agent trees by root session and flag abandoned children

The Steward can run as a one-shot command, a watch loop, or a launchd job. It
does not require a full agent framework. A local model such as a Gemma-style
Ollama model can improve the wording of the report, but the authority stays in
the file protocol and the human/project agent.

## When A Framework Might Be Worth It

Consider a real framework only if the team needs:

- multi-machine hosted service
- role-based access control
- web dashboard with login
- policy approvals
- integration with issue trackers
- scheduled summaries across many teams

Until then, the lightweight file-based model is the advantage.
