#!/usr/bin/env python3
"""Portable Agent Council CLI.

State directory resolution:
1. COUNCIL_HOME, if set.
2. <repo>/.council, where <repo> is the parent of this script's directory.

The tool intentionally uses plain files so it works across IDEs, desktops,
terminal agents, and CI-style runners without a service dependency.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import uuid
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise SystemExit("Missing dependency: PyYAML. Install with `python3 -m pip install pyyaml`.") from exc


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
COUNCIL_HOME = pathlib.Path(os.environ.get("COUNCIL_HOME", REPO_ROOT / ".council")).expanduser().resolve()
LEDGER = COUNCIL_HOME / "ledger.jsonl"
PROJECT_DIR = COUNCIL_HOME / "projects"
AGENT_DIR = COUNCIL_HOME / "agents"
CURRENT_DIR = COUNCIL_HOME / "current-state"
CLAIMS_DIR = COUNCIL_HOME / "claims"
MANIFEST = COUNCIL_HOME / "manifest.yaml"

STALE_VERIFY_HOURS = int(os.environ.get("COUNCIL_STALE_VERIFY_HOURS", "24"))
STALE_SESSION_HOURS = int(os.environ.get("COUNCIL_STALE_SESSION_HOURS", "12"))
TREE_RENDER_DEPTH = int(os.environ.get("COUNCIL_TREE_RENDER_DEPTH", "8"))
DEFAULT_CLAIM_TTL = int(os.environ.get("COUNCIL_CLAIM_TTL", "1800"))  # lease goes stale 30 min after last heartbeat


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def iso_now() -> str:
    return now_utc().replace(microsecond=0).isoformat()


def parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def expand_path(value: str | None, base: pathlib.Path | None = None) -> pathlib.Path | None:
    if not value:
        return None
    path = pathlib.Path(os.path.expandvars(os.path.expanduser(value)))
    if not path.is_absolute() and base:
        path = base / path
    return path.resolve()


def load_yaml(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def write_yaml(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        yaml.safe_dump(data, fh, sort_keys=False, width=100)


def run(cmd: list[str], cwd: pathlib.Path | None = None) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic command wrapper
        return 1, str(exc)
    return proc.returncode, proc.stdout.strip()


def project_path(slug: str) -> pathlib.Path:
    return PROJECT_DIR / f"{slug}.yaml"


def load_project(slug: str) -> dict[str, Any]:
    return load_yaml(project_path(slug))


def normalize_agent(agent: str) -> str:
    return agent.strip().replace("_", "-")


def canonical_project(slug: str) -> str:
    seen: set[str] = set()
    current = slug
    while current and current not in seen:
        seen.add(current)
        doc = load_project(current)
        alias_for = doc.get("alias_for") or doc.get("canonical_slug")
        if not alias_for:
            return current
        current = str(alias_for)
    return slug


def infer_project(cwd: pathlib.Path) -> str | None:
    cwd = cwd.resolve()
    best: tuple[int, str] | None = None
    for path in PROJECT_DIR.glob("*.yaml"):
        doc = load_yaml(path)
        if doc.get("alias_for"):
            continue
        repo = expand_path(doc.get("repo"), REPO_ROOT)
        if not repo or not repo.exists():
            continue
        try:
            cwd.relative_to(repo)
        except ValueError:
            continue
        depth = len(repo.parts)
        if best is None or depth > best[0]:
            best = (depth, path.stem)
    return best[1] if best else None


def git_state(repo: pathlib.Path | None) -> dict[str, Any]:
    if not repo or not repo.exists() or not (repo / ".git").exists():
        return {"available": False}
    branch_code, branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)
    head_code, head = run(["git", "rev-parse", "--short", "HEAD"], repo)
    full_code, full_head = run(["git", "rev-parse", "HEAD"], repo)
    status_code, status = run(["git", "status", "--short", "--branch"], repo)
    dirty_lines = [line for line in status.splitlines() if line and not line.startswith("## ")]
    first = status.splitlines()[0] if status else ""
    return {
        "available": branch_code == 0 and head_code == 0,
        "branch": branch if branch_code == 0 else None,
        "head": head if head_code == 0 else None,
        "head_full": full_head if full_code == 0 else None,
        "dirty": bool(dirty_lines),
        "dirty_count": len(dirty_lines),
        "status_header": first,
        "status_error": None if status_code == 0 else status,
    }


def ledger_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not LEDGER.exists():
        return events
    with LEDGER.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"ts": iso_now(), "agent": "unknown", "project": "unknown", "event": "parse_error", "summary": line[:120]})
    return events


def make_session_id(project: str, agent: str) -> str:
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    return f"{project}-{agent}-{stamp}-{uuid.uuid4().hex[:8]}"


def event_session_id(event: dict[str, Any]) -> str:
    if event.get("session_id"):
        return str(event["session_id"])
    project = canonical_project(str(event.get("project", "")))
    agent = normalize_agent(str(event.get("agent", "")))
    return f"legacy:{project}:{agent}"


def open_sessions(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    active: dict[str, dict[str, Any]] = {}
    for event in events:
        project = canonical_project(str(event.get("project", "")))
        agent = normalize_agent(str(event.get("agent", "")))
        if not project or not agent:
            continue
        key = event_session_id(event)
        if event.get("event") == "session_start":
            active[key] = event
        elif event.get("event") == "session_end":
            active.pop(key, None)
    return active


def latest_open_session(project: str, agent: str, events: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [
        event
        for event in open_sessions(events).values()
        if canonical_project(str(event.get("project", ""))) == project
        and normalize_agent(str(event.get("agent", ""))) == agent
    ]
    if not matches:
        return None
    matches.sort(key=lambda event: str(event.get("ts", "")))
    return matches[-1]


def find_session_start(session_id: str | None, events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not session_id:
        return None
    for event in reversed(events):
        if event.get("event") == "session_start" and event_session_id(event) == session_id:
            return event
    return None


def append_ledger(event: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(event, separators=(",", ":"), sort_keys=False) + "\n")


def update_agent_card(agent: str, project: str, summary: str, event_name: str) -> None:
    path = AGENT_DIR / f"{agent}.yaml"
    doc = load_yaml(path) or {"id": agent, "name": agent}
    doc["last_active"] = iso_now()
    doc["last_project"] = project
    doc["last_session_summary"] = summary
    if event_name == "session_start":
        doc["current_session"] = {"project": project, "started_at": iso_now(), "summary": summary}
    elif event_name == "session_end":
        doc.pop("current_session", None)
        doc["last_session_ended"] = iso_now()
    write_yaml(path, doc)


def update_project_card(project: str, agent: str, harness: str, summary: str, event: dict[str, Any], cwd: pathlib.Path) -> None:
    path = project_path(project)
    doc = load_yaml(path)
    if not doc:
        return
    event_name = str(event.get("event", ""))
    session_id = str(event.get("session_id", ""))
    active = doc.get("active_agents") or []
    normalized: list[dict[str, Any]] = []
    for item in active:
        if isinstance(item, dict):
            normalized.append(dict(item))
        elif isinstance(item, str):
            normalized.append({"agent": item})
    if event_name == "session_start":
        normalized = [
            item
            for item in normalized
            if not (
                (session_id and item.get("session_id") == session_id)
                or (not session_id and item.get("agent") == agent)
            )
        ]
        active_item = {
            "agent": agent,
            "harness": harness,
            "focus": summary,
            "since": event.get("ts") or iso_now(),
            "session_id": session_id or None,
            "parent_session_id": event.get("parent_session_id") or None,
            "root_session_id": event.get("root_session_id") or session_id or None,
            "depth": event.get("depth", 0),
        }
        if event.get("role"):
            active_item["role"] = event.get("role")
        if event.get("scope"):
            active_item["scope"] = event.get("scope")
        normalized.append(active_item)
    elif event_name == "session_end":
        for item in normalized:
            same_session = session_id and item.get("session_id") == session_id
            same_legacy_agent = not session_id and item.get("agent") == agent
            if (same_session or same_legacy_agent) and not item.get("ended"):
                item["ended"] = event.get("ts") or iso_now()
                item["last_summary"] = summary
    doc["active_agents"] = normalized
    repo = expand_path(doc.get("repo"), REPO_ROOT) or cwd
    state = doc.setdefault("state", {})
    gs = git_state(repo)
    if gs.get("available"):
        state["git_branch"] = gs.get("branch")
        state["git_head"] = gs.get("head")
        state["git_dirty"] = gs.get("dirty")
    verification = doc.setdefault("verification", {})
    verification["last_verified_at"] = iso_now()
    verification["verified_by"] = agent
    verification["confidence"] = "fresh"
    doc["last_updated"] = iso_now()
    doc["last_updated_by"] = agent
    write_yaml(path, doc)


def project_references(doc: dict[str, Any]) -> list[tuple[str, pathlib.Path, bool]]:
    refs: list[tuple[str, pathlib.Path, bool]] = []
    repo = expand_path(doc.get("repo"), REPO_ROOT)
    state = doc.get("state") or {}
    if not isinstance(state, dict):
        return refs
    reference_keys = {"handoff", "current_state", "agent_handoff", "runbook", "docs"}
    for key, value in state.items():
        if key not in reference_keys:
            continue
        values = value if isinstance(value, list) else [value]
        for raw in values:
            if not isinstance(raw, str) or not raw:
                continue
            refs.append((key, expand_path(raw, repo or REPO_ROOT) or pathlib.Path(raw), (expand_path(raw, repo or REPO_ROOT) or pathlib.Path(raw)).exists()))
    return refs


def alert_status(alert: dict[str, Any]) -> str:
    status = str(alert.get("status", "active"))
    return status if status in {"active", "mitigated", "resolved", "stale"} else "active"


def doctor(project: str | None = None) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    infos: list[str] = []
    events = ledger_events()
    active = open_sessions(events)
    manifest = load_yaml(MANIFEST)
    manifest_slugs = [p.get("slug") for p in manifest.get("projects", []) if isinstance(p, dict)]
    for slug in manifest_slugs:
        if slug and not project_path(str(slug)).exists():
            errors.append(f"manifest references missing project card: {slug}")
    projects = [canonical_project(project)] if project else [
        path.stem for path in PROJECT_DIR.glob("*.yaml") if not load_yaml(path).get("alias_for")
    ]
    for slug in sorted(set(projects)):
        doc = load_project(slug)
        if not doc:
            errors.append(f"{slug}: missing project card")
            continue
        repo = expand_path(doc.get("repo"), REPO_ROOT)
        if not repo or not repo.exists():
            warnings.append(f"{slug}: repo missing: {doc.get('repo')}")
        state = doc.get("state") or {}
        gs = git_state(repo)
        if gs.get("available"):
            if state.get("git_branch") and state.get("git_branch") != gs.get("branch"):
                warnings.append(f"{slug}: card branch {state.get('git_branch')} != repo {gs.get('branch')}")
            if gs.get("dirty"):
                infos.append(f"{slug}: repo dirty with {gs.get('dirty_count')} changed paths")
        verification = doc.get("verification") or {}
        verified_at = parse_time(verification.get("last_verified_at"))
        if verification.get("confidence") == "example":
            pass
        elif not verified_at:
            warnings.append(f"{slug}: no verification.last_verified_at")
        elif now_utc() - verified_at > dt.timedelta(hours=STALE_VERIFY_HOURS):
            warnings.append(f"{slug}: verification stale")
        for key, path, exists in project_references(doc):
            if not exists:
                warnings.append(f"{slug}: state.{key} reference not found: {path}")
        for alert in doc.get("alerts") or []:
            if not isinstance(alert, dict) or alert_status(alert) in {"resolved", "stale"}:
                continue
            ident = alert.get("id") or alert.get("message", "")[:40]
            for field in ("owner", "last_checked_at", "next_check"):
                if not alert.get(field):
                    warnings.append(f"{slug}: alert missing {field}: {ident}")
            next_check = parse_time(alert.get("next_check"))
            if next_check and next_check < now_utc():
                warnings.append(f"{slug}: alert next_check overdue: {ident}")
        for session_id, event in active.items():
            session_project = canonical_project(str(event.get("project", "")))
            agent = normalize_agent(str(event.get("agent", "")))
            if session_project != slug:
                continue
            started = parse_time(event.get("ts"))
            if started and now_utc() - started > dt.timedelta(hours=STALE_SESSION_HOURS):
                warnings.append(f"{slug}: open session stale >{STALE_SESSION_HOURS}h: {agent} ({session_id})")
    # Traffic control: stale leases, collisions, sessions with no claim.
    live_leases: list[dict[str, Any]] = []
    for lease in all_claims():
        if claim_is_live(lease):
            live_leases.append(lease)
        else:
            infos.append(
                f"claims: stale lease on {lease.get('resource')} "
                f"(held by {lease.get('agent')}) — run `traffic.sh sweep`"
            )
    for i, lease_a in enumerate(live_leases):
        for lease_b in live_leases[i + 1:]:
            ra, rb = str(lease_a.get("resource")), str(lease_b.get("resource"))
            if lease_a.get("agent") == lease_b.get("agent"):
                continue
            if ra == rb or ra.startswith(rb + "/") or rb.startswith(ra + "/"):
                errors.append(
                    f"claims: COLLISION — {lease_a.get('agent')} and {lease_b.get('agent')} "
                    f"hold overlapping resources ({ra} / {rb})"
                )
    claimed = {(normalize_agent(d.get("agent", "")), str(d.get("resource"))) for d in live_leases}
    for event in active.values():
        session_project = canonical_project(str(event.get("project", "")))
        if project and session_project != canonical_project(project):
            continue
        agent = normalize_agent(str(event.get("agent", "")))
        cwd = expand_path(event.get("cwd") or event.get("repo"), REPO_ROOT)
        if not cwd:
            continue
        if not any(
            ag == agent and (str(cwd) == res or str(cwd).startswith(res + "/") or res.startswith(str(cwd) + "/"))
            for ag, res in claimed
        ):
            warnings.append(
                f"{session_project}: {agent} has an open session at {cwd} with no traffic claim "
                f"— run `traffic.sh acquire`"
            )

    print("Agent Council Doctor")
    print(f"home: {COUNCIL_HOME}")
    print(f"checked_at: {iso_now()}")
    for label, items in (("Errors", errors), ("Warnings", warnings), ("Info", infos)):
        if items:
            print(f"\n{label}")
            prefix = {"Errors": "ERROR", "Warnings": "WARN", "Info": "INFO"}[label]
            for item in items:
                print(f"  {prefix}: {item}")
    if not errors and not warnings:
        print("\nOK: no errors or warnings")
    return 2 if errors else 0


def generate_current(project: str, cwd: pathlib.Path | None = None) -> pathlib.Path:
    project = canonical_project(project)
    doc = load_project(project)
    if not doc:
        raise SystemExit(f"Unknown project: {project}")
    repo = expand_path(doc.get("repo"), REPO_ROOT) or cwd or REPO_ROOT
    events = ledger_events()
    active = open_sessions(events)
    project_events = [e for e in events if canonical_project(str(e.get("project", ""))) == project]
    current = {
        "generated_at": iso_now(),
        "project": project,
        "name": doc.get("name"),
        "boundary": doc.get("boundary"),
        "repo": doc.get("repo"),
        "git": git_state(repo),
        "verification": doc.get("verification") or {},
        "active_agents": [
            {
                "agent": normalize_agent(str(event.get("agent", ""))),
                "since": event.get("ts"),
                "summary": event.get("summary"),
                "harness": event.get("harness"),
                "session_id": session_id,
                "parent_session_id": event.get("parent_session_id"),
                "root_session_id": event.get("root_session_id") or session_id,
                "depth": event.get("depth", 0),
                "role": event.get("role"),
                "scope": event.get("scope"),
            }
            for session_id, event in active.items()
            if canonical_project(str(event.get("project", ""))) == project
        ],
        "alerts": [
            {
                "id": alert.get("id"),
                "severity": alert.get("severity"),
                "status": alert_status(alert),
                "message": alert.get("message"),
                "owner": alert.get("owner"),
                "next_check": alert.get("next_check"),
            }
            for alert in doc.get("alerts") or []
            if isinstance(alert, dict) and alert_status(alert) in {"active", "mitigated"}
        ],
        "recent_events": project_events[-10:],
        "next_best_action": doc.get("next_best_action"),
    }
    path = CURRENT_DIR / f"{project}.yaml"
    write_yaml(path, current)
    return path


def print_bootstrap(project: str) -> None:
    print(f"Agent Council Bootstrap: {project}")
    print("\nRecent activity")
    for event in ledger_events()[-10:]:
        print(f"  {str(event.get('ts', ''))[:16]} [{event.get('agent', '?')}] {event.get('event', '?')}: {str(event.get('summary', ''))[:100]}")
    print("\nActive alerts")
    for alert in load_project(project).get("alerts") or []:
        if isinstance(alert, dict) and alert_status(alert) in {"active", "mitigated"}:
            print(f"  [{alert.get('severity', 'info')}] {alert.get('message')}")
    print()
    doctor(project)


def session_lineage(args: argparse.Namespace, project: str, agent: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    if args.action == "start":
        session_id = args.session_id or make_session_id(project, agent)
        parent_session_id = args.parent_session_id or os.environ.get("COUNCIL_PARENT_SESSION_ID") or ""
        parent = find_session_start(parent_session_id, events)
        root_session_id = (
            args.root_session_id
            or os.environ.get("COUNCIL_ROOT_SESSION_ID")
            or (str(parent.get("root_session_id") or event_session_id(parent)) if parent else "")
            or session_id
        )
        if args.depth is not None:
            depth = args.depth
        elif parent:
            depth = int(parent.get("depth") or 0) + 1
        else:
            depth = 0
        return {
            "session_id": session_id,
            "parent_session_id": parent_session_id or None,
            "root_session_id": root_session_id,
            "depth": depth,
        }

    open_session = None
    if args.session_id:
        open_session = find_session_start(args.session_id, events)
    if not open_session:
        open_session = latest_open_session(project, agent, events)
    session_id = args.session_id or (event_session_id(open_session) if open_session else make_session_id(project, agent))
    return {
        "session_id": session_id,
        "parent_session_id": args.parent_session_id or (open_session or {}).get("parent_session_id"),
        "root_session_id": args.root_session_id or (open_session or {}).get("root_session_id") or session_id,
        "depth": args.depth if args.depth is not None else (open_session or {}).get("depth", 0),
    }


def session(args: argparse.Namespace) -> int:
    cwd = pathlib.Path(args.cwd or os.getcwd()).resolve()
    project = canonical_project(args.project or infer_project(cwd) or "")
    if not project:
        raise SystemExit("Could not infer project. Pass --project <slug>.")
    agent = normalize_agent(args.agent)
    events = ledger_events()
    lineage = session_lineage(args, project, agent, events)
    repo = expand_path(load_project(project).get("repo"), REPO_ROOT) or cwd
    gs = git_state(repo)
    event_name = f"session_{args.action}"
    event = {
        "ts": iso_now(),
        "agent": agent,
        "harness": args.harness,
        "project": project,
        "event": event_name,
        "summary": args.summary,
        "cwd": str(cwd),
        "branch": gs.get("branch"),
        "head": gs.get("head"),
        "dirty": gs.get("dirty"),
        "dirty_count": gs.get("dirty_count"),
        **lineage,
    }
    if args.role:
        event["role"] = args.role
    if args.scope:
        event["scope"] = args.scope
    if args.action == "end":
        event["files_touched"] = [f for f in (args.files or "").split(",") if f]
        event["issues_updated"] = [i for i in (args.issues or "").split(",") if i]
        event["prs_updated"] = [p for p in (args.prs or "").split(",") if p]
        event["remaining_blockers"] = args.blockers or ""
        event["next_best_action"] = args.next or ""
    append_ledger(event)
    update_agent_card(agent, project, args.summary, event_name)
    update_project_card(project, agent, args.harness, args.summary, event, cwd)
    path = generate_current(project, cwd)
    if args.action == "start":
        print_bootstrap(project)
    print(f"Logged {event_name} for {agent} on {project}")
    print(f"Session id: {event['session_id']}")
    print(f"Current state: {path}")
    return 0


def print_tree(project: str | None = None) -> int:
    events = ledger_events()
    starts: dict[str, dict[str, Any]] = {}
    ended: set[str] = set()
    for event in events:
        event_project = canonical_project(str(event.get("project", "")))
        if project and event_project != canonical_project(project):
            continue
        if event.get("event") == "session_start":
            starts[event_session_id(event)] = event
        elif event.get("event") == "session_end":
            ended.add(event_session_id(event))

    children: dict[str, list[str]] = {}
    roots: list[str] = []
    for session_id, event in starts.items():
        parent = str(event.get("parent_session_id") or "")
        if parent and parent in starts:
            children.setdefault(parent, []).append(session_id)
        else:
            roots.append(session_id)

    def sort_key(session_id: str) -> str:
        return str(starts[session_id].get("ts", ""))

    def render(session_id: str, indent: int) -> None:
        event = starts[session_id]
        status = "open" if session_id not in ended else "closed"
        agent = normalize_agent(str(event.get("agent", "?")))
        role = f" role={event.get('role')}" if event.get("role") else ""
        scope = f" scope={event.get('scope')}" if event.get("scope") else ""
        print(
            f"{'  ' * indent}- {session_id} [{status}] "
            f"{agent} depth={event.get('depth', indent)}{role}{scope}: {str(event.get('summary', ''))[:90]}"
        )
        if indent >= TREE_RENDER_DEPTH:
            if children.get(session_id):
                print(f"{'  ' * (indent + 1)}- ... depth limit reached")
            return
        for child_id in sorted(children.get(session_id, []), key=sort_key):
            render(child_id, indent + 1)

    title = f"Agent Council Session Tree: {canonical_project(project)}" if project else "Agent Council Session Tree"
    print(title)
    for root_id in sorted(roots, key=sort_key):
        render(root_id, 0)
    if not roots:
        print("(no session_start events)")
    return 0


# ── Traffic control: resource claims / leases ───────────────────────────────
#
# `session` records *that* an agent is working. It does not stop two agents
# from editing the same working directory at once. A "claim" is a short-lived
# lease on a resource (almost always a worktree path) that does: agents
# `acquire` before writing, `heartbeat` while working, and `release` when done.
# Leases auto-expire DEFAULT_CLAIM_TTL seconds after their last heartbeat, so a
# crashed agent never blocks a lane forever. No daemon — pure files, like the
# rest of the council.


def resolve_resource(resource: str) -> tuple[str, str]:
    """Return (canonical resource id, kind). Filesystem paths are resolved;
    anything else is treated as an opaque named resource."""
    text = str(resource or "").strip()
    if not text:
        raise SystemExit("--resource is required")
    if text.startswith(("~", "/", ".")) or "/" in text:
        path = expand_path(text, REPO_ROOT)
        if path is None:
            raise SystemExit(f"could not resolve resource path: {resource}")
        kind = "worktree" if (path / ".git").exists() else "path"
        return str(path), kind
    return text, "named"


def claim_path(resource_id: str) -> pathlib.Path:
    digest = hashlib.sha1(resource_id.encode()).hexdigest()[:10]
    base = pathlib.Path(resource_id).name or "resource"
    safe = "".join(c if c.isalnum() or c in "-._" else "-" for c in base)[:48]
    return CLAIMS_DIR / f"{safe}__{digest}.yaml"


def claim_is_live(lease: dict[str, Any]) -> bool:
    expires = parse_time(lease.get("expires_at"))
    return bool(expires and expires > now_utc())


def sweep_claims() -> list[dict[str, Any]]:
    """Delete expired lease files. Returns the leases that were swept."""
    swept: list[dict[str, Any]] = []
    if not CLAIMS_DIR.exists():
        return swept
    for path in sorted(CLAIMS_DIR.glob("*.yaml")):
        lease = load_yaml(path)
        if not lease:
            path.unlink(missing_ok=True)
            continue
        if not claim_is_live(lease):
            swept.append(lease)
            path.unlink(missing_ok=True)
            append_ledger({
                "ts": iso_now(),
                "agent": "council",
                "harness": "council",
                "project": lease.get("project", ""),
                "event": "claim_expired",
                "summary": (
                    f"swept stale lease on {lease.get('resource')} "
                    f"(held by {lease.get('agent')}, last heartbeat {lease.get('heartbeat_at')})"
                ),
            })
    return swept


def all_claims() -> list[dict[str, Any]]:
    if not CLAIMS_DIR.exists():
        return []
    return [lease for lease in (load_yaml(p) for p in sorted(CLAIMS_DIR.glob("*.yaml"))) if lease]


def _new_lease(args: argparse.Namespace, resource_id: str, kind: str) -> dict[str, Any]:
    ttl = int(getattr(args, "ttl", None) or DEFAULT_CLAIM_TTL)
    project = ""
    if getattr(args, "project", None):
        project = canonical_project(args.project)
    elif kind in {"worktree", "path"}:
        project = infer_project(pathlib.Path(resource_id)) or ""
    return {
        "resource": resource_id,
        "resource_kind": kind,
        "agent": normalize_agent(args.agent),
        "harness": args.harness,
        "project": project,
        "intent": getattr(args, "intent", "") or "",
        "acquired_at": iso_now(),
        "heartbeat_at": iso_now(),
        "expires_at": (now_utc() + dt.timedelta(seconds=ttl)).replace(microsecond=0).isoformat(),
        "ttl_seconds": ttl,
        "host_pid": os.getpid(),
    }


def _bump_lease(lease: dict[str, Any]) -> None:
    ttl = int(lease.get("ttl_seconds") or DEFAULT_CLAIM_TTL)
    lease["heartbeat_at"] = iso_now()
    lease["expires_at"] = (now_utc() + dt.timedelta(seconds=ttl)).replace(microsecond=0).isoformat()


def claim_acquire(args: argparse.Namespace) -> int:
    CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
    sweep_claims()
    resource_id, kind = resolve_resource(args.resource)
    lease_file = claim_path(resource_id)
    me = normalize_agent(args.agent)
    new_lease = _new_lease(args, resource_id, kind)
    try:
        # O_EXCL create — atomic. Whoever wins the race owns the lane.
        os.close(os.open(lease_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
    except FileExistsError:
        existing = load_yaml(lease_file)
        if existing and normalize_agent(existing.get("agent", "")) == me:
            _bump_lease(existing)
            if getattr(args, "intent", ""):
                existing["intent"] = args.intent
            write_yaml(lease_file, existing)
            print(f"GREEN — lease already yours; heartbeat refreshed: {resource_id}")
            return 0
        if existing and claim_is_live(existing):
            print(
                f"RED — {resource_id}\n"
                f"   held by {existing.get('agent')} ({existing.get('harness')}) "
                f"since {existing.get('acquired_at')}\n"
                f"   intent: {existing.get('intent') or '(none stated)'}\n"
                f"   expires: {existing.get('expires_at')} "
                f"(last heartbeat {existing.get('heartbeat_at')})\n"
                f"   -> do NOT write here. Use a separate worktree, pick another task, "
                f"or coordinate via the ledger."
            )
            append_ledger({
                "ts": iso_now(), "agent": me, "harness": args.harness,
                "project": new_lease.get("project", ""), "event": "claim_denied",
                "summary": (
                    f"denied claim on {resource_id} — held by {existing.get('agent')} "
                    f"until {existing.get('expires_at')}"
                ),
            })
            return 1
        # Stale lease — reclaim it.
        write_yaml(lease_file, new_lease)
        append_ledger({
            "ts": iso_now(), "agent": me, "harness": args.harness,
            "project": new_lease.get("project", ""), "event": "claim_stolen",
            "summary": f"reclaimed stale lease on {resource_id} from {(existing or {}).get('agent', 'unknown')}",
        })
        print(f"GREEN — reclaimed stale lease (was {(existing or {}).get('agent', '?')}): {resource_id}")
        return 0
    write_yaml(lease_file, new_lease)
    append_ledger({
        "ts": iso_now(), "agent": me, "harness": args.harness,
        "project": new_lease.get("project", ""), "event": "claim_acquired",
        "summary": f"acquired {kind} lease on {resource_id}: {new_lease['intent'] or '(no intent stated)'}",
    })
    print(f"GREEN — lease acquired ({kind}): {resource_id}")
    print(f"   ttl {new_lease['ttl_seconds']}s · expires {new_lease['expires_at']} · heartbeat to extend")
    return 0


def claim_heartbeat(args: argparse.Namespace) -> int:
    resource_id, _kind = resolve_resource(args.resource)
    lease_file = claim_path(resource_id)
    lease = load_yaml(lease_file)
    me = normalize_agent(args.agent)
    if not lease:
        print(f"no lease on {resource_id} — run `claim acquire` first")
        return 1
    if normalize_agent(lease.get("agent", "")) != me:
        print(f"RED — lease on {resource_id} is held by {lease.get('agent')}, not you")
        return 1
    _bump_lease(lease)
    write_yaml(lease_file, lease)
    print(f"heartbeat ok — {resource_id} held until {lease['expires_at']}")
    return 0


def claim_release(args: argparse.Namespace) -> int:
    resource_id, _kind = resolve_resource(args.resource)
    lease_file = claim_path(resource_id)
    lease = load_yaml(lease_file)
    me = normalize_agent(args.agent)
    if not lease:
        print(f"no lease on {resource_id} — nothing to release")
        return 0
    holder = normalize_agent(lease.get("agent", ""))
    if holder != me and not getattr(args, "force", False):
        print(f"RED — lease on {resource_id} is held by {holder}, not you. Use --force to override.")
        return 1
    lease_file.unlink(missing_ok=True)
    append_ledger({
        "ts": iso_now(), "agent": me, "harness": args.harness,
        "project": lease.get("project", ""), "event": "claim_released",
        "summary": f"released lease on {resource_id}" + (f" (forced, was {holder})" if holder != me else ""),
    })
    print(f"released lease on {resource_id}")
    return 0


def claim_check(args: argparse.Namespace) -> int:
    resource_id, _kind = resolve_resource(args.resource)
    lease = load_yaml(claim_path(resource_id))
    me = normalize_agent(getattr(args, "agent", "") or "")
    if not lease:
        print(f"GREEN — {resource_id} is unclaimed")
        return 0
    holder = normalize_agent(lease.get("agent", ""))
    if not claim_is_live(lease):
        print(f"GREEN — {resource_id}: lease by {holder} is STALE (expired {lease.get('expires_at')}); reclaimable")
        return 0
    if me and holder == me:
        print(f"YELLOW — {resource_id}: lease is yours, expires {lease.get('expires_at')}")
        return 0
    print(
        f"RED — {resource_id}: held by {holder} ({lease.get('harness')}), "
        f"intent: {lease.get('intent') or '(none)'}, expires {lease.get('expires_at')}"
    )
    return 1


def claim_board(_args: argparse.Namespace) -> int:
    CLAIMS_DIR.mkdir(parents=True, exist_ok=True)
    sweep_claims()
    leases = all_claims()
    print("=== Council Traffic Board ===")
    print(f"checked_at: {iso_now()}")
    if not leases:
        print("\nall lanes clear — no active resource claims")
    else:
        print(f"\nActive leases ({len(leases)}):")
        for lease in sorted(leases, key=lambda d: str(d.get("resource"))):
            mark = "LIVE " if claim_is_live(lease) else "stale"
            print(
                f"  [{mark}] {lease.get('resource')}\n"
                f"          {lease.get('agent')} ({lease.get('harness')}) · "
                f"project={lease.get('project') or '?'} · intent: {lease.get('intent') or '(none)'}\n"
                f"          acquired {lease.get('acquired_at')} · expires {lease.get('expires_at')}"
            )
    live = [d for d in leases if claim_is_live(d)]
    collisions: list[str] = []
    for i, a in enumerate(live):
        for b in live[i + 1:]:
            ra, rb = str(a.get("resource")), str(b.get("resource"))
            if a.get("agent") == b.get("agent"):
                continue
            if ra == rb or ra.startswith(rb + "/") or rb.startswith(ra + "/"):
                collisions.append(
                    f"  COLLISION: {a.get('agent')} and {b.get('agent')} hold overlapping paths\n"
                    f"      {ra}\n      {rb}"
                )
    if collisions:
        print("\nCOLLISIONS:")
        for line in collisions:
            print(line)
    # Open sessions in the ledger with no live claim on their cwd/repo.
    claimed = {(normalize_agent(d.get("agent", "")), str(d.get("resource"))) for d in live}
    unclaimed: list[str] = []
    for event in open_sessions(ledger_events()).values():
        agent = normalize_agent(str(event.get("agent", "")))
        cwd = expand_path(event.get("cwd") or event.get("repo"), REPO_ROOT)
        if not cwd:
            continue
        if not any(
            ag == agent and (str(cwd) == res or str(cwd).startswith(res + "/") or res.startswith(str(cwd) + "/"))
            for ag, res in claimed
        ):
            unclaimed.append(f"  {agent} has an open session at {cwd} with NO active claim")
    if unclaimed:
        print("\nOPEN SESSIONS WITHOUT A CLAIM:")
        for line in unclaimed:
            print(line)
    if not collisions and not unclaimed:
        print("\nNo collisions or unclaimed sessions detected.")
    return 2 if collisions else 0


def claim(args: argparse.Namespace) -> int:
    dispatch = {
        "acquire": claim_acquire,
        "heartbeat": claim_heartbeat,
        "release": claim_release,
        "check": claim_check,
        "board": claim_board,
        "sweep": lambda _a: (print(f"swept {len(sweep_claims())} stale lease(s)") or 0),
    }
    return dispatch[args.claim_action](args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Portable Agent Council")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor_parser = sub.add_parser("doctor")
    doctor_parser.add_argument("project", nargs="?")
    current_parser = sub.add_parser("current")
    current_parser.add_argument("project", nargs="?")
    current_parser.add_argument("--cwd")
    tree_parser = sub.add_parser("tree")
    tree_parser.add_argument("project", nargs="?")
    session_parser = sub.add_parser("session")
    session_parser.add_argument("action", choices=["start", "end"])
    session_parser.add_argument("--agent", required=True)
    session_parser.add_argument("--harness", required=True)
    session_parser.add_argument("--project")
    session_parser.add_argument("--summary", required=True)
    session_parser.add_argument("--cwd")
    session_parser.add_argument("--session-id")
    session_parser.add_argument("--parent-session-id")
    session_parser.add_argument("--root-session-id")
    session_parser.add_argument("--depth", type=int)
    session_parser.add_argument("--role", default="")
    session_parser.add_argument("--scope", default="")
    session_parser.add_argument("--files", default="")
    session_parser.add_argument("--issues", default="")
    session_parser.add_argument("--prs", default="")
    session_parser.add_argument("--blockers", default="")
    session_parser.add_argument("--next", default="")
    claim_parser = sub.add_parser("claim", help="acquire/release/check resource leases (traffic control)")
    claim_parser.add_argument("claim_action", choices=["acquire", "release", "heartbeat", "check", "board", "sweep"])
    claim_parser.add_argument("--agent", default="")
    claim_parser.add_argument("--harness", default="")
    claim_parser.add_argument("--resource", default="")
    claim_parser.add_argument("--intent", default="")
    claim_parser.add_argument("--project")
    claim_parser.add_argument("--ttl", type=int)
    claim_parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "claim":
        if args.claim_action in {"acquire", "heartbeat", "release"} and not args.agent:
            raise SystemExit(f"claim {args.claim_action} requires --agent")
        if args.claim_action in {"acquire", "heartbeat", "release", "check"} and not args.resource:
            raise SystemExit(f"claim {args.claim_action} requires --resource")
        return claim(args)
    if args.command == "doctor":
        return doctor(args.project)
    if args.command == "current":
        project = canonical_project(args.project or infer_project(pathlib.Path(args.cwd or os.getcwd())) or "")
        if not project:
            raise SystemExit("Could not infer project. Pass a project slug.")
        print(generate_current(project, pathlib.Path(args.cwd or os.getcwd()).resolve()))
        return 0
    if args.command == "tree":
        return print_tree(args.project)
    if args.command == "session":
        return session(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
