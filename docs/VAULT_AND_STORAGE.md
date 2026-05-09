# Vault And Storage Model

Agent Council uses a file vault by default, not a database.

## Default Vault

The vault is `.council/`:

```text
.council/
├── manifest.yaml
├── ledger.jsonl              # local runtime event log, gitignored
├── ledger.example.jsonl      # sanitized seed example
├── agents/                   # agent identity cards
├── projects/                 # project cards
└── current-state/            # generated snapshots, gitignored
```

## Why Files First

Files are enough for the core use case:

- every IDE can read/write them
- humans can inspect them without a UI
- git can diff project-card changes
- the ledger is append-only and easy to recover
- there is no service to deploy or keep alive
- it works offline

## What Gets Committed

Commit:

- `manifest.yaml`
- `agents/*.yaml`
- `projects/*.yaml`
- docs and scripts
- sanitized examples

Do not commit:

- `.council/ledger.jsonl`
- `.council/current-state/*.yaml`
- secrets
- private logs
- customer or company data

## Optional Database Later

A database can be useful when the team needs:

- web dashboards
- multi-machine sync
- query-heavy analytics
- audit retention policies
- role-based access

Good phase-two options:

- SQLite for a local single-machine dashboard
- DuckDB for analytics over `ledger.jsonl`
- Postgres for a hosted team service
- object storage for durable ledger archival

The key rule: keep the file vault as the source-of-recovery even if a database
is added as a read model.
