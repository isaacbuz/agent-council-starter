# Agent Instructions Snippet

Paste this into each project-level agent instruction file, such as `AGENTS.md`,
`CLAUDE.md`, `GEMINI.md`, Cursor rules, or other IDE agent instructions.

Replace:

- `PROJECT_SLUG` with the matching `.council/projects/<slug>.yaml` filename.
- `AGENT_ID` with `codex`, `claude`, `gemini`, `cursor`, or your own id.
- `HARNESS` with the runtime or IDE, such as `openai-desktop`, `claude-code`,
  `gemini-ide`, `cursor`, or `terminal`.

```markdown
## Agent Council - Required Coordination

Before non-trivial work, run:

```bash
./bin/session.sh start \
  --agent AGENT_ID \
  --harness HARNESS \
  --project PROJECT_SLUG \
  --summary "BRIEF PLAN"
```

At closeout, run:

```bash
./bin/session.sh end \
  --agent AGENT_ID \
  --harness HARNESS \
  --project PROJECT_SLUG \
  --summary "WHAT CHANGED" \
  --files "file1,file2" \
  --issues "123,456" \
  --prs "789" \
  --blockers "ANYTHING STILL BLOCKED" \
  --next "NEXT BEST ACTION"
```

Use `./bin/doctor.sh PROJECT_SLUG` when the project card may be stale.
Trust `./.council/current-state/PROJECT_SLUG.yaml` before older handoffs.
```

## Sub-Agent Pattern

If you spawn a sub-agent, pass your `session_id` as its parent:

```bash
./bin/session.sh start \
  --agent CHILD_AGENT_ID \
  --harness HARNESS \
  --project PROJECT_SLUG \
  --parent-session-id PARENT_SESSION_ID \
  --role verifier \
  --scope "tests and review only" \
  --summary "WHAT THE CHILD OWNS"
```

If the child cannot run shell commands, the parent logs a `session_start` and
`session_end` on the child's behalf. Keep child scopes narrow, especially when
multiple workers are editing files.

To inspect nested work:

```bash
./bin/query.sh tree PROJECT_SLUG
```

## Cross-IDE Pattern

The same snippet works in:

- Cursor project rules
- Claude Code `CLAUDE.md`
- Gemini `GEMINI.md`
- Codex `AGENTS.md`
- local terminal agents
- team runbooks

The key is that each IDE writes to the same `ledger.jsonl`, so agents can see
each other's sessions without sharing a chat thread.
