#!/usr/bin/env python3
"""Initialize optimized, non-destructive run records in one repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Exact repository directory")
    parser.add_argument("--run-id", required=True, help="Filesystem-safe run identifier")
    parser.add_argument("--team-name", required=True, help="Unique team or repository name")
    parser.add_argument("--repository-count", required=True, type=int)
    parser.add_argument("--worker-role", action="append", required=True)
    parser.add_argument(
        "--role-responsibility", action="append", required=True, metavar="ROLE=TEXT"
    )
    parser.add_argument("--review-role", required=True)
    parser.add_argument("--max-review-rounds", type=int, default=3)
    parser.add_argument("--resume", action="store_true", help="Create only missing templates")
    return parser.parse_args()


def validate_roles(raw_roles: list[str], review_role: str) -> list[str]:
    roles = [role.strip() for role in raw_roles]
    if any(not role for role in roles):
        raise SystemExit("worker roles must not be empty")
    folded = [role.casefold() for role in roles]
    if len(set(folded)) != len(roles):
        raise SystemExit("worker roles must be unique, ignoring case")
    matches = [role for role in roles if role.casefold() == review_role.casefold()]
    if len(matches) != 1:
        raise SystemExit("--review-role must match exactly one --worker-role")
    if len(roles) < 2:
        raise SystemExit("configure at least one ordinary role plus the review-gate role")
    return roles


def parse_responsibilities(values: list[str], roles: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    canonical = {role.casefold(): role for role in roles}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"role responsibility must use ROLE=TEXT: {value}")
        raw_role, raw_text = value.split("=", 1)
        key = raw_role.strip().casefold()
        text = raw_text.strip()
        if key not in canonical:
            raise SystemExit(f"responsibility supplied for unknown role: {raw_role.strip()}")
        if key in parsed:
            raise SystemExit(f"duplicate responsibility for role: {canonical[key]}")
        if not text:
            raise SystemExit(f"responsibility must not be empty for role: {canonical[key]}")
        parsed[key] = text
    missing = [role for role in roles if role.casefold() not in parsed]
    if missing:
        raise SystemExit(f"missing responsibilities for roles: {', '.join(missing)}")
    return parsed


def safe_stem(role: str, order: int) -> str:
    stem = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in role)
    return stem.strip(".-_")[:48] or f"role-{order}"


def configuration_hash(workflow: dict) -> str:
    canonical = json.dumps(
        workflow, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> int:
    args = parse_args()
    if not RUN_ID_RE.fullmatch(args.run_id):
        raise SystemExit("run ID must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}")
    if args.repository_count < 1:
        raise SystemExit("repository count must be positive")
    if args.max_review_rounds < 1:
        raise SystemExit("maximum review rounds must be positive")

    requested_review_role = args.review_role.strip()
    roles = validate_roles(args.worker_role, requested_review_role)
    responsibilities = parse_responsibilities(args.role_responsibility, roles)
    review_role = next(role for role in roles if role.casefold() == requested_review_role.casefold())
    role_definitions = [
        {
            "name": role,
            "responsibility": responsibilities[role.casefold()],
            "order": order,
            "stageKind": "review-gate" if role == review_role else "ordinary",
        }
        for order, role in enumerate(roles, 1)
    ]
    workflow = {
        "repositoryCount": args.repository_count,
        "roles": role_definitions,
        "reviewGateRole": review_role,
        "maxReviewRounds": args.max_review_rounds,
    }
    config_hash = configuration_hash(workflow)

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        raise SystemExit(f"repository directory does not exist: {repo}")
    run_dir = repo / "agent-team" / "runs" / args.run_id
    config_path = run_dir / "run-config.json"
    roster_path = run_dir / "roster.json"
    if run_dir.exists() and any(run_dir.iterdir()) and not args.resume:
        raise SystemExit(f"run directory already contains files: {run_dir}; use --resume")
    if args.resume and run_dir.exists() and any(run_dir.iterdir()):
        if not config_path.is_file() or not roster_path.is_file():
            raise SystemExit("resume rejected: schema-3 run-config or roster is missing")
        existing_config = json.loads(config_path.read_text(encoding="utf-8"))
        existing_roster = json.loads(roster_path.read_text(encoding="utf-8"))
        if existing_config.get("configurationHash") != config_hash:
            raise SystemExit("resume rejected: workflow configuration differs")
        if existing_config.get("team") != args.team_name:
            raise SystemExit("resume rejected: team name differs")
        if Path(str(existing_config.get("repository", ""))).resolve() != repo:
            raise SystemExit("resume rejected: repository differs")
        if existing_roster.get("configurationHash") != config_hash:
            raise SystemExit("resume rejected: roster configuration hash differs")
    run_dir.mkdir(parents=True, exist_ok=True)

    workers = []
    dynamic_templates: dict[str, str] = {}
    for definition in role_definitions:
        role = definition["name"]
        order = definition["order"]
        is_gate = definition["stageKind"] == "review-gate"
        stem = safe_stem(role, order)
        report_path = "review.md" if is_gate else f"role-reports/{order:02d}-{stem}.md"
        handoff_path = None if is_gate else f"handoffs/{order:02d}-{stem}.json"
        workers.append(
            {
                "role": role,
                "responsibility": definition["responsibility"],
                "order": order,
                "stageKind": definition["stageKind"],
                "reportPath": report_path,
                "handoffPath": handoff_path,
                "title": "",
                "threadId": "",
                "hostId": "",
                "status": "unassigned",
                "lastVerifiedAt": None,
            }
        )
        if not is_gate:
            dynamic_templates[report_path] = (
                f"# Role report: {role}\n\nRun: `{args.run_id}`\n\n"
                "## Responsibility\n\n## Inputs\n\n## Actions and evidence\n\n"
                "## Handoff\n\n## Risks and requests\n"
            )
            dynamic_templates[handoff_path] = json_text(
                {
                    "schemaVersion": 3,
                    "runId": args.run_id,
                    "role": role,
                    "order": order,
                    "status": "PENDING",
                    "summary": "",
                    "changedFiles": [],
                    "tests": [],
                    "decisions": [],
                    "risks": [],
                    "request": None,
                    "completedAt": None,
                }
            )

    now = utc_now()
    templates = {
        "run-config.json": json_text(
            {
                "schemaVersion": 3,
                "runId": args.run_id,
                "team": args.team_name,
                "repository": str(repo),
                "createdAt": now,
                "configurationHash": config_hash,
                "workflow": workflow,
            }
        ),
        "roster.json": json_text(
            {
                "schemaVersion": 3,
                "runId": args.run_id,
                "repositoryCount": args.repository_count,
                "team": args.team_name,
                "repository": str(repo),
                "configurationHash": config_hash,
                "rosterVersion": 1,
                "createdAt": now,
                "manager": {
                    "title": "manager", "threadId": "", "hostId": "",
                    "status": "unassigned", "lastVerifiedAt": None,
                },
                "leader": {
                    "title": "", "threadId": "", "hostId": "",
                    "status": "unassigned", "lastVerifiedAt": None,
                },
                "workers": workers,
                "peerLeaders": [],
            }
        ),
        "spec.md": f"# Specification\n\nRun: `{args.run_id}`\n\n## Goal\n\n## Scope\n\n## Constraints\n\n## Interfaces\n\n## Acceptance criteria\n\n## Excluded work\n",
        "plan.md": f"# Plan\n\nRun: `{args.run_id}`\n\n## Ordinary role stages\n\n## Work items\n\n## Dependencies\n\n## Test plan\n\n## Risks\n",
        "decisions.jsonl": "",
        "development-log.md": f"# Development log\n\nRun: `{args.run_id}`\n\n## Changes\n\n## Commands and outcomes\n\n## Deviations\n\n## Open risks\n",
        "review.md": f"# Review\n\nRun: `{args.run_id}`\n\nReview role: {review_role}\nMaximum rounds: {args.max_review_rounds}\n\nVerdict: PENDING\n\n## Findings\n\n## Tests checked\n",
        "review.json": json_text(
            {
                "schemaVersion": 3,
                "runId": args.run_id,
                "round": 0,
                "maxRounds": args.max_review_rounds,
                "verdict": "PENDING",
                "reviewer": {"role": review_role, "title": "", "threadId": ""},
                "findings": [],
                "testsChecked": [],
                "reviewedAt": None,
            }
        ),
        "alignment-input.json": json_text(
            {
                "schemaVersion": 3,
                "runId": args.run_id,
                "team": args.team_name,
                "status": "PENDING",
                "provides": [],
                "requires": [],
                "migrations": [],
                "commitOrder": None,
                "rollback": [],
                "tests": [],
                "risks": [],
                "submittedAt": None,
            }
        ),
        "alignment.md": f"# Manager-hub alignment\n\nRun: `{args.run_id}`\n\nStatus: PENDING\nManager decision: PENDING\n\n## Interfaces and data contracts\n\n## Commit or deployment order\n\n## Migrations and rollback\n\n## Cross-repository tests\n\n## Accepted differences\n",
        "result.json": json_text(
            {
                "schemaVersion": 3,
                "runId": args.run_id,
                "configurationHash": config_hash,
                "status": "initialized",
                "executedRoles": [],
                "review": {"verdict": "PENDING", "round": 0, "maxRounds": args.max_review_rounds},
                "tests": [],
                "risks": [],
                "approvedAt": None,
            }
        ),
        **dynamic_templates,
    }

    created: list[str] = []
    preserved: list[str] = []
    for name, content in templates.items():
        path = run_dir / name
        if path.exists():
            preserved.append(name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        created.append(name)

    print(json.dumps(
        {
            "runId": args.run_id,
            "configurationHash": config_hash,
            "ordinaryRoles": [d["name"] for d in role_definitions if d["stageKind"] == "ordinary"],
            "reviewRole": review_role,
            "maxReviewRounds": args.max_review_rounds,
            "recordsDirectory": str(run_dir),
            "created": created,
            "preserved": preserved,
        }, ensure_ascii=False, indent=2
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
