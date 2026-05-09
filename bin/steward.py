#!/usr/bin/env python3
"""Optional local Agent Council Steward.

The steward is read-mostly by design. It inspects Council files, detects stale
or abandoned work, and writes reports under `.council/steward/reports/`.

If Ollama is available, it can ask a local Gemma-style model for a short
summary. If not, it falls back to deterministic local checks.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import council  # noqa: E402


DEFAULT_MODEL = os.environ.get("COUNCIL_STEWARD_MODEL", "gemma3:4b")
REPORT_DIR = council.COUNCIL_HOME / "steward" / "reports"


def summarize_project(project: str | None) -> dict[str, Any]:
    events = council.ledger_events()
    active = council.open_sessions(events)
    project_filter = council.canonical_project(project) if project else None
    now = council.now_utc()
    stale_cutoff = dt.timedelta(hours=council.STALE_SESSION_HOURS)

    starts: dict[str, dict[str, Any]] = {}
    ended: set[str] = set()
    stale: list[dict[str, Any]] = []
    active_rows: list[dict[str, Any]] = []

    for event in events:
        event_project = council.canonical_project(str(event.get("project", "")))
        if project_filter and event_project != project_filter:
            continue
        session_id = council.event_session_id(event)
        if event.get("event") == "session_start":
            starts[session_id] = event
        elif event.get("event") == "session_end":
            ended.add(session_id)

    for session_id, event in active.items():
        event_project = council.canonical_project(str(event.get("project", "")))
        if project_filter and event_project != project_filter:
            continue
        started_at = council.parse_time(event.get("ts"))
        age_hours = ((now - started_at).total_seconds() / 3600) if started_at else None
        row = {
            "session_id": session_id,
            "project": event_project,
            "agent": event.get("agent"),
            "harness": event.get("harness"),
            "summary": event.get("summary"),
            "parent_session_id": event.get("parent_session_id"),
            "root_session_id": event.get("root_session_id") or session_id,
            "depth": event.get("depth", 0),
            "role": event.get("role"),
            "scope": event.get("scope"),
            "age_hours": round(age_hours, 2) if age_hours is not None else None,
        }
        active_rows.append(row)
        if started_at and now - started_at > stale_cutoff:
            stale.append(row)

    roots: dict[str, list[dict[str, Any]]] = {}
    for session_id, event in starts.items():
        root = str(event.get("root_session_id") or session_id)
        roots.setdefault(root, []).append(
            {
                "session_id": session_id,
                "project": council.canonical_project(str(event.get("project", ""))),
                "agent": event.get("agent"),
                "summary": event.get("summary"),
                "parent_session_id": event.get("parent_session_id"),
                "depth": event.get("depth", 0),
                "status": "closed" if session_id in ended else "open",
                "role": event.get("role"),
                "scope": event.get("scope"),
            }
        )

    alerts: list[dict[str, Any]] = []
    project_cards = [project_filter] if project_filter else [
        path.stem for path in council.PROJECT_DIR.glob("*.yaml") if not council.load_yaml(path).get("alias_for")
    ]
    for slug in sorted(set(filter(None, project_cards))):
        card = council.load_project(str(slug))
        for alert in card.get("alerts") or []:
            if not isinstance(alert, dict):
                continue
            if council.alert_status(alert) in {"active", "mitigated"}:
                alerts.append(
                    {
                        "project": slug,
                        "id": alert.get("id"),
                        "severity": alert.get("severity"),
                        "message": alert.get("message"),
                        "owner": alert.get("owner"),
                        "next_check": alert.get("next_check"),
                    }
                )

    return {
        "generated_at": council.iso_now(),
        "project": project_filter or "all",
        "active_sessions": active_rows,
        "stale_sessions": stale,
        "alerts": alerts,
        "session_roots": roots,
        "recent_events": [
            event for event in events[-20:]
            if not project_filter or council.canonical_project(str(event.get("project", ""))) == project_filter
        ],
    }


def deterministic_summary(snapshot: dict[str, Any]) -> str:
    lines = [
        f"# Agent Council Steward Report",
        "",
        f"Generated: {snapshot['generated_at']}",
        f"Project: {snapshot['project']}",
        "",
        "## Status",
        f"- Active sessions: {len(snapshot['active_sessions'])}",
        f"- Stale sessions: {len(snapshot['stale_sessions'])}",
        f"- Active alerts: {len(snapshot['alerts'])}",
        f"- Root workstreams: {len(snapshot['session_roots'])}",
    ]
    if snapshot["stale_sessions"]:
        lines.append("")
        lines.append("## Stale Sessions")
        for row in snapshot["stale_sessions"]:
            lines.append(f"- {row['session_id']} ({row['agent']}): {row.get('summary', '')}")
    if snapshot["alerts"]:
        lines.append("")
        lines.append("## Alerts")
        for alert in snapshot["alerts"][:12]:
            lines.append(f"- [{alert.get('severity', 'info')}] {alert.get('project')}: {alert.get('message')}")
    lines.append("")
    lines.append("## Recommendation")
    if snapshot["stale_sessions"]:
        lines.append("Close or refresh stale sessions before starting more parallel work.")
    elif snapshot["alerts"]:
        lines.append("Review active alerts, then keep agent scopes narrow and explicit.")
    else:
        lines.append("No stale sessions or active alerts found. Continue normal Council logging.")
    return "\n".join(lines) + "\n"


def local_model_summary(snapshot: dict[str, Any], model: str) -> str | None:
    if not shutil.which("ollama"):
        return None
    prompt = (
        "You are a local read-only Agent Council Steward. Summarize this JSON "
        "in concise markdown. Flag stale sessions, abandoned child agents, "
        "overlapping scopes, and the next safest action. Do not invent facts.\n\n"
        + json.dumps(snapshot, indent=2, sort_keys=True)[:20000]
    )
    try:
        proc = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=90,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout.strip() + "\n"


def write_report(snapshot: dict[str, Any], body: str) -> pathlib.Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = council.now_utc().strftime("%Y%m%dT%H%M%SZ")
    base = REPORT_DIR / f"{stamp}-{snapshot['project']}"
    json_path = base.with_suffix(".json")
    md_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n")
    md_path.write_text(body)
    latest = REPORT_DIR / "latest.md"
    latest.write_text(body)
    return md_path


def run_once(project: str | None, model: str, no_model: bool) -> pathlib.Path:
    snapshot = summarize_project(project)
    body = None if no_model else local_model_summary(snapshot, model)
    if not body:
        body = deterministic_summary(snapshot)
    report = write_report(snapshot, body)
    print(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Optional local Agent Council Steward")
    parser.add_argument("--project", help="Limit report to one project slug")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name")
    parser.add_argument("--no-model", action="store_true", help="Use deterministic checks only")
    parser.add_argument("--watch", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=900, help="Watch interval in seconds")
    args = parser.parse_args()

    if not args.watch:
        run_once(args.project, args.model, args.no_model)
        return 0

    while True:
        run_once(args.project, args.model, args.no_model)
        time.sleep(max(args.interval, 60))


if __name__ == "__main__":
    raise SystemExit(main())
