# Sub-Agent Lineage

Agent Council supports sub-agents to arbitrary depth by storing lineage pointers
in the append-only ledger.

## Core Fields

Every session event may include:

- `session_id` - unique id for this agent session
- `parent_session_id` - the session that spawned this one
- `root_session_id` - the top-level session for the workstream
- `depth` - root is `0`, child is `1`, grandchild is `2`
- `role` - optional short label such as `worker`, `verifier`, `reviewer`
- `scope` - optional ownership boundary, such as `tests only`

This keeps the model flat on disk while still allowing a full tree view.

## Why Parent Pointers Instead Of Nested Files?

Parent pointers are easier to append safely from many IDEs and agents. They also
work when child agents finish out of order, fail early, or run in separate
terminals.

## Parent-Owned Logging

If a child agent can run shell commands, it should call `session.sh start/end`
itself.

If it cannot, the parent agent logs on its behalf:

```bash
./bin/session.sh start \
  --agent verifier-1 \
  --harness delegated-agent \
  --project example-app \
  --parent-session-id ROOT_SESSION_ID \
  --role verifier \
  --scope "no file edits" \
  --summary "Review the API contract"
```

Close it with the same `session_id`:

```bash
./bin/session.sh end \
  --agent verifier-1 \
  --harness delegated-agent \
  --project example-app \
  --session-id CHILD_SESSION_ID \
  --summary "Found one schema drift risk" \
  --files "" \
  --blockers "" \
  --next "Parent should patch the schema test"
```

## Tree Inspection

```bash
./bin/query.sh tree example-app
```

The tree command shows open and closed children under the root session. Rendering
is capped by `COUNCIL_TREE_RENDER_DEPTH`, but the ledger can store deeper
lineage.

## Guardrails

- Give every child a narrow `scope`.
- Prefer disjoint file ownership for editing workers.
- The parent remains accountable for child results.
- The Council stores summaries and artifacts, not private chain-of-thought.
- A local Steward may summarize the tree and flag abandoned children, but should
  not mutate project state without confirmation.
