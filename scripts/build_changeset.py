#!/usr/bin/env python3
"""Batch-verify optimized repository submissions and build a manager changeset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
REQUIRED_RECORDS = (
    "run-config.json", "roster.json", "spec.md", "plan.md", "decisions.jsonl",
    "development-log.md", "review.md", "review.json", "alignment-input.json",
    "alignment.md", "result.json",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manager-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-repo-count", required=True, type=int)
    parser.add_argument("--repo", action="append", required=True, metavar="TEAM=PATH")
    parser.add_argument("--manager-thread-id", default="")
    parser.add_argument("--alignment-summary", required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args], text=True, encoding="utf-8",
        errors="replace", capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed for {repo}: {detail}")
    return completed.stdout.strip()


def parse_repo(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"repository must use TEAM=PATH: {value}")
    team, raw_path = value.split("=", 1)
    if not team.strip() or not raw_path.strip():
        raise ValueError(f"repository must use TEAM=PATH: {value}")
    return team.strip(), Path(raw_path.strip()).resolve()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object in {path}")
    return value


def workflow_hash(workflow: object) -> str:
    canonical = json.dumps(
        workflow, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def safe_record_path(value: object, prefix: str, team: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise RuntimeError(f"invalid {prefix} path in roster for {team}")
    normalized = Path(value)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise RuntimeError(f"unsafe record path in roster for {team}: {value}")
    return normalized.as_posix()


def changed_files(repo: Path) -> list[dict]:
    output = git(repo, "diff-tree", "--root", "--no-commit-id", "--name-status", "--find-renames", "-r", "HEAD")
    result: list[dict] = []
    for line in output.splitlines():
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            result.append({"status": status, "from": parts[1], "path": parts[2]})
        elif len(parts) >= 2:
            result.append({"status": status, "path": parts[1]})
    return result


def validate_findings(findings: object, roles: set[str], team: str) -> None:
    if not isinstance(findings, list):
        raise RuntimeError(f"review findings must be a list for {team}")
    for finding in findings:
        if not isinstance(finding, dict):
            raise RuntimeError(f"invalid review finding for {team}")
        owner = finding.get("ownerRole")
        affected = finding.get("affectedRoles")
        if owner not in roles or not isinstance(affected, list) or any(r not in roles for r in affected):
            raise RuntimeError(f"review finding references unknown roles for {team}")


def verify_repository(team: str, requested_repo: Path, run_id: str, expected_count: int) -> dict:
    if not requested_repo.is_dir():
        raise RuntimeError(f"repository directory does not exist: {requested_repo}")
    git_root = Path(git(requested_repo, "rev-parse", "--show-toplevel")).resolve()
    if git_root != requested_repo:
        raise RuntimeError(f"use the exact Git root for {team}: {git_root}")
    dirty = git(git_root, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise RuntimeError(f"worktree is not clean for {team}:\n{dirty}")

    records_rel = Path("agent-team") / "runs" / run_id
    records_dir = git_root / records_rel
    missing = [name for name in REQUIRED_RECORDS if not (records_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"missing run records for {team}: {', '.join(missing)}")

    config = load_json(records_dir / "run-config.json")
    roster = load_json(records_dir / "roster.json")
    if config.get("schemaVersion") != 3 or roster.get("schemaVersion") != 3:
        raise RuntimeError(f"schema-3 configuration and roster are required for {team}")
    if config.get("runId") != run_id or roster.get("runId") != run_id:
        raise RuntimeError(f"run ID mismatch for {team}")
    if config.get("team") != team or roster.get("team") != team:
        raise RuntimeError(f"team mismatch for {team}")
    if config.get("workflow", {}).get("repositoryCount") != expected_count:
        raise RuntimeError(f"repository count mismatch for {team}")
    if Path(str(config.get("repository", ""))).resolve() != requested_repo:
        raise RuntimeError(f"repository path mismatch for {team}")
    config_hash = config.get("configurationHash")
    if not isinstance(config_hash, str) or workflow_hash(config.get("workflow")) != config_hash:
        raise RuntimeError(f"run configuration hash is invalid for {team}")
    if roster.get("configurationHash") != config_hash:
        raise RuntimeError(f"configuration hash mismatch for {team}")
    if roster.get("repositoryCount") != expected_count:
        raise RuntimeError(f"roster repository count mismatch for {team}")
    if Path(str(roster.get("repository", ""))).resolve() != requested_repo:
        raise RuntimeError(f"roster repository path mismatch for {team}")

    workers = roster.get("workers")
    if not isinstance(workers, list) or not workers:
        raise RuntimeError(f"roster has no workers for {team}")
    gates = [w for w in workers if w.get("stageKind") == "review-gate"]
    if len(gates) != 1:
        raise RuntimeError(f"roster must contain exactly one review gate for {team}")
    gate_role = gates[0].get("role")
    ordinary = sorted(
        [w for w in workers if w.get("stageKind") == "ordinary"], key=lambda w: w.get("order", 0)
    )
    if not ordinary:
        raise RuntimeError(f"roster has no ordinary roles for {team}")
    all_roles = {w.get("role") for w in workers}
    dynamic_records: list[str] = []
    for worker in ordinary:
        role = worker.get("role")
        responsibility = worker.get("responsibility")
        if not isinstance(role, str) or not isinstance(responsibility, str) or not responsibility.strip():
            raise RuntimeError(f"invalid ordinary role in roster for {team}")
        report_path = safe_record_path(worker.get("reportPath"), "role-reports/", team)
        handoff_path = safe_record_path(worker.get("handoffPath"), "handoffs/", team)
        dynamic_records.extend([report_path, handoff_path])
        handoff = load_json(records_dir / handoff_path)
        if handoff.get("runId") != run_id or handoff.get("role") != role or handoff.get("status") != "DONE":
            raise RuntimeError(f"ordinary handoff is incomplete for role {role} in {team}")
    if gates[0].get("reportPath") != "review.md" or gates[0].get("handoffPath") is not None:
        raise RuntimeError(f"review gate must not have an ordinary report or handoff for {team}")

    required_paths = [*REQUIRED_RECORDS, *dynamic_records]
    tracked = set(git(git_root, "ls-tree", "-r", "--name-only", "HEAD").splitlines())
    untracked_records = [
        (records_rel / name).as_posix()
        for name in required_paths
        if (records_rel / name).as_posix() not in tracked
    ]
    if untracked_records:
        raise RuntimeError(f"records are not tracked at HEAD for {team}: {', '.join(untracked_records)}")

    review = load_json(records_dir / "review.json")
    result = load_json(records_dir / "result.json")
    max_rounds = config.get("workflow", {}).get("maxReviewRounds")
    review_round = review.get("round")
    if not isinstance(max_rounds, int) or max_rounds < 1:
        raise RuntimeError(f"invalid maximum review rounds for {team}")
    if review.get("verdict") != "APPROVED" or review.get("reviewer", {}).get("role") != gate_role:
        raise RuntimeError(f"review gate approval is invalid for {team}")
    if review.get("maxRounds") != max_rounds or not isinstance(review_round, int) or not 1 <= review_round <= max_rounds:
        raise RuntimeError(f"review round is outside the configured limit for {team}")
    validate_findings(review.get("findings"), all_roles, team)
    ordinary_roles = [w["role"] for w in ordinary]
    if result.get("configurationHash") != config_hash or result.get("status") != "approved":
        raise RuntimeError(f"approved result is invalid for {team}")
    if result.get("review", {}).get("verdict") != "APPROVED" or result.get("review", {}).get("round") != review_round:
        raise RuntimeError(f"result and review do not agree for {team}")
    if set(result.get("executedRoles", [])) != set(ordinary_roles):
        raise RuntimeError(f"result does not list every ordinary role for {team}")

    alignment_input = load_json(records_dir / "alignment-input.json")
    if alignment_input.get("runId") != run_id or alignment_input.get("team") != team or alignment_input.get("status") != "SUBMITTED":
        raise RuntimeError(f"alignment input is not submitted for {team}")
    alignment = (records_dir / "alignment.md").read_text(encoding="utf-8")
    if "Status: ALIGNED" not in alignment or "Manager decision: PENDING" in alignment:
        raise RuntimeError(f"manager-hub alignment is incomplete for {team}")

    files = changed_files(git_root)
    records_prefix = records_rel.as_posix() + "/"
    if not any(item["path"].startswith(records_prefix) for item in files):
        raise RuntimeError(f"HEAD does not contain this run's records for {team}")
    metadata = git(git_root, "show", "-s", "--format=%an%x1f%ae%x1f%aI%x1f%s", "HEAD")
    author_name, author_email, committed_at, subject = metadata.split("\x1f", 3)
    ancestry = git(git_root, "rev-list", "--parents", "-n", "1", "HEAD").split()
    return {
        "team": team,
        "path": str(requested_repo),
        "gitRoot": str(git_root),
        "branch": git(git_root, "branch", "--show-current"),
        "commit": git(git_root, "rev-parse", "HEAD"),
        "parentCommit": ancestry[1] if len(ancestry) > 1 else None,
        "subject": subject,
        "author": {"name": author_name, "email": author_email},
        "committedAt": committed_at,
        "changedFiles": files,
        "configurationHash": config_hash,
        "workerRoles": [w.get("role") for w in workers],
        "ordinaryStageRoles": ordinary_roles,
        "reviewGateRole": gate_role,
        "maxReviewRounds": max_rounds,
        "review": {"verdict": "APPROVED", "round": review_round},
        "recordsDirectory": records_rel.as_posix(),
        "resultStatus": "approved",
    }


def main() -> int:
    args = parse_args()
    if not RUN_ID_RE.fullmatch(args.run_id):
        raise SystemExit("invalid run ID")
    if args.expected_repo_count < 1 or len(args.repo) != args.expected_repo_count:
        raise SystemExit("--repo argument count must equal --expected-repo-count")
    parsed = [parse_repo(value) for value in args.repo]
    teams = [team for team, _ in parsed]
    paths = [str(repo).casefold() for _, repo in parsed]
    if len(set(teams)) != len(teams) or len(set(paths)) != len(paths):
        raise SystemExit("repository team names and paths must be unique")

    repositories = [
        verify_repository(team, repo, args.run_id, args.expected_repo_count)
        for team, repo in parsed
    ]
    manager_dir = Path(args.manager_dir).resolve()
    if not manager_dir.is_dir():
        raise SystemExit(f"manager directory does not exist: {manager_dir}")
    destination_dir = manager_dir / "changesets"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{args.run_id}.json"
    if destination.exists() and not args.force:
        raise SystemExit(f"changeset already exists: {destination}; use --force only with authorization")
    payload = {
        "schemaVersion": 3,
        "id": args.run_id,
        "status": "complete",
        "generatedAt": utc_now(),
        "parameters": {"repositoryCount": args.expected_repo_count},
        "manager": {"threadId": args.manager_thread_id},
        "leaderAlignment": {"status": "aligned", "summary": args.alignment_summary},
        "repositories": repositories,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"changeset": str(destination), "commits": [r["commit"] for r in repositories]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
