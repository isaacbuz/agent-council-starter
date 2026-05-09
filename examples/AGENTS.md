# Example Agent Instructions

This is a sanitized example. Copy the Agent Council section into your real
project's agent instructions.

## Agent Council

Before non-trivial work:

```bash
./bin/session.sh start \
  --agent codex \
  --harness openai-desktop \
  --project example-app \
  --summary "Describe the plan"
```

Before closeout:

```bash
./bin/session.sh end \
  --agent codex \
  --harness openai-desktop \
  --project example-app \
  --summary "Describe the completed work" \
  --files "path/to/file" \
  --issues "" \
  --prs "" \
  --blockers "" \
  --next "Describe the next action"
```

Run `./bin/doctor.sh example-app` if project state looks stale.
