#!/usr/bin/env python3
"""Manage Harness phase worktrees and PR handoff."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHASE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STATUS_UPDATE_INTERVAL_SECONDS = 60
STUCK_AFTER_SECONDS = 1800
MAX_STUCK_RETRIES = 3
# Compatibility alias for callers using the original name.
MAX_STUCK_ATTEMPTS = MAX_STUCK_RETRIES
HEARTBEAT_STATUSES = frozenset({"running", "completed", "stuck", "error", "blocked"})


class PhaseWorktreeError(RuntimeError):
    """Raised when phase worktree operation is blocked."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("start", "validate", "open-pr"))
    parser.add_argument("phase")
    parser.add_argument("--root", default=".")
    return parser.parse_args()


def validate_phase_name(phase: str) -> str:
    if not PHASE_RE.match(phase):
        raise PhaseWorktreeError("phase must be kebab-case slug")
    return phase


def run_git(root: Path, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=120,
        shell=False,
    )
    if check and completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PhaseWorktreeError(detail or "git command failed")
    return completed


def require_main_and_clean(root: Path) -> None:
    branch = run_git(root, ["branch", "--show-current"]).stdout.strip()
    if branch != "main":
        raise PhaseWorktreeError("phase start must run from main branch")
    status = run_git(root, ["status", "--porcelain"]).stdout.strip()
    if status:
        raise PhaseWorktreeError("main worktree must be clean before phase start")


def start_phase(root: Path, phase: str) -> Path:
    phase = validate_phase_name(phase)
    root = root.resolve()
    require_main_and_clean(root)
    worktree = root / ".worktrees" / phase
    if worktree.exists():
        return worktree

    worktree.parent.mkdir(parents=True, exist_ok=True)
    branch = f"feat-{phase}"
    branch_exists = run_git(root, ["show-ref", "--verify", f"refs/heads/{branch}"], check=False).returncode == 0
    if branch_exists:
        run_git(root, ["worktree", "add", str(worktree), branch])
    else:
        run_git(root, ["worktree", "add", "-b", branch, str(worktree), "main"])
    return worktree


def ensure_phase_completed(root: Path, phase: str) -> dict[str, Any]:
    phase = validate_phase_name(phase)
    index = root / "phases" / phase / "index.json"
    if not index.exists():
        raise PhaseWorktreeError(f"missing phase index: {index}")
    data = json.loads(index.read_text(encoding="utf-8"))
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise PhaseWorktreeError("phase must define at least one step")
    incomplete = [
        str(item.get("step"))
        for item in steps
        if not isinstance(item, dict) or item.get("status") != "completed"
    ]
    if incomplete:
        raise PhaseWorktreeError("phase has incomplete steps: " + ", ".join(incomplete))
    return data


def write_heartbeat(
    *,
    root: Path,
    phase: str,
    step: int,
    attempt: int,
    status: str,
    message: str | None = None,
    started_at: datetime | str | None = None,
    now: datetime | str | None = None,
    progress: str | None = None,
    stuck_retry: int = 0,
    pipeline_attempt: int | None = None,
    status_update_interval_seconds: int = STATUS_UPDATE_INTERVAL_SECONDS,
    stuck_after_seconds: int = STUCK_AFTER_SECONDS,
    max_stuck_retries: int = MAX_STUCK_RETRIES,
) -> Path:
    """Persist one immutable runtime state snapshot for an implementation attempt."""

    phase = validate_phase_name(phase)
    if not isinstance(status, str) or status not in HEARTBEAT_STATUSES:
        raise PhaseWorktreeError(f"invalid heartbeat status: {status}")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise PhaseWorktreeError("attempt must be a positive integer")
    for name, value in (("stuck_retry", stuck_retry),):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise PhaseWorktreeError(f"{name} must be a non-negative integer")
    for name, value in (
        ("status_update_interval_seconds", status_update_interval_seconds),
        ("stuck_after_seconds", stuck_after_seconds),
        ("max_stuck_retries", max_stuck_retries),
    ):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise PhaseWorktreeError(f"{name} must be positive")

    current = _as_utc_datetime(now)
    started = _as_utc_datetime(started_at) if started_at is not None else current
    if started > current:
        raise PhaseWorktreeError("started_at cannot be later than updated_at")
    elapsed_seconds = int((current - started).total_seconds())
    progress_text = progress if progress is not None else message or ""
    if not isinstance(progress_text, str):
        raise PhaseWorktreeError("progress must be a string")
    pipeline_number = pipeline_attempt if pipeline_attempt is not None else attempt
    if not isinstance(pipeline_number, int) or isinstance(pipeline_number, bool) or pipeline_number < 1:
        raise PhaseWorktreeError("pipeline_attempt must be a positive integer")

    directory = root / ".harness" / "runtime" / phase
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"step{step}-attempt{attempt}.json"
    payload = {
        "phase": phase,
        "step": step,
        "attempt": attempt,
        "pipeline_attempt": pipeline_number,
        "status": status,
        "message": message,
        "progress": progress_text,
        "started_at": started.isoformat(),
        "updated_at": current.isoformat(),
        "elapsed_seconds": elapsed_seconds,
        "status_update_interval_seconds": status_update_interval_seconds,
        "stuck_after_seconds": stuck_after_seconds,
        "stuck_retry": stuck_retry,
        "stuck_retries": stuck_retry,
        "max_stuck_retries": max_stuck_retries,
        "max_stuck_attempts": max_stuck_retries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def is_stuck(
    *,
    started_at: datetime | str,
    now: datetime | str,
    status: str,
    stuck_after_seconds: int = STUCK_AFTER_SECONDS,
) -> bool:
    """Return true only when a non-finished implementation exceeds its start timeout."""

    if status != "running":
        return False
    if not isinstance(stuck_after_seconds, int) or isinstance(stuck_after_seconds, bool) or stuck_after_seconds < 0:
        raise PhaseWorktreeError("stuck_after_seconds must be a non-negative integer")
    started = _as_utc_datetime(started_at)
    current = _as_utc_datetime(now)
    return current >= started and (current - started).total_seconds() >= stuck_after_seconds


def next_stuck_state(stuck_retries: int, *, max_stuck_retries: int = MAX_STUCK_RETRIES) -> tuple[str, int]:
    """Return next stuck lifecycle state without changing pipeline retry count."""

    if not isinstance(stuck_retries, int) or isinstance(stuck_retries, bool) or stuck_retries < 0:
        raise PhaseWorktreeError("stuck_retries must be a non-negative integer")
    if not isinstance(max_stuck_retries, int) or isinstance(max_stuck_retries, bool) or max_stuck_retries < 1:
        raise PhaseWorktreeError("max_stuck_retries must be positive")
    if stuck_retries >= max_stuck_retries:
        return "error", stuck_retries
    return "stuck", stuck_retries + 1


def _as_utc_datetime(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as exc:
            raise PhaseWorktreeError("timestamp must be ISO-8601") from exc
    if not isinstance(value, datetime):
        raise PhaseWorktreeError("timestamp must be datetime or ISO-8601 string")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def validate_phase(root: Path, phase: str) -> None:
    ensure_phase_completed(root, phase)


def open_pr(root: Path, phase: str) -> None:
    phase = validate_phase_name(phase)
    worktree = root.resolve() / ".worktrees" / phase
    if not worktree.exists():
        raise PhaseWorktreeError(f"missing worktree: {worktree}")
    ensure_phase_completed(worktree, phase)
    if run_git(worktree, ["status", "--porcelain"]).stdout.strip():
        raise PhaseWorktreeError("phase worktree must be clean before PR handoff")

    run_command(worktree, [sys.executable, "scripts/validate_project.py", "--root", ".", "--strict"])
    repo = run_command(worktree, ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"]).strip()
    branch = f"feat-{phase}"
    title = f"feat: {phase} phase"
    body = pr_body_for_phase(phase)
    existing = subprocess.run(
        ["gh", "pr", "view", "--repo", repo, "--head", branch, "--json", "number"],
        cwd=worktree,
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,
    )
    if existing.returncode != 0:
        run_command(
            worktree,
            ["gh", "pr", "create", "--repo", repo, "--base", "main", "--head", branch, "--title", title, "--body", body],
        )
    run_command(worktree, [sys.executable, "scripts/check_github_pr_gate.py", "--repo", repo])
    head_sha = run_git(worktree, ["rev-parse", "HEAD"]).stdout.strip()
    run_command(
        worktree,
        ["gh", "pr", "merge", "--auto", "--merge", "--delete-branch", "--match-head-commit", head_sha],
    )


def run_command(root: Path, command: list[str]) -> str:
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=600, shell=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PhaseWorktreeError(detail or f"command failed: {' '.join(command)}")
    return completed.stdout.strip()


def pr_body_for_phase(phase: str) -> str:
    return f"""## 작업 목적
`{phase}` phase 변경을 main에 병합합니다.

## 변경 범위
phase 산출물과 관련 코드 변경.

## 테스트 내용
Harness validation과 phase Acceptance Criteria.

## 검증 결과
`phase_worktree.py open-pr` 사전 검증 통과 후 auto-merge 대기.

## 영향 범위
해당 phase 범위.

## 롤백 방법
merge commit revert.
"""


def main() -> int:
    args = parse_args()
    root = Path(args.root)
    try:
        if args.command == "start":
            print(start_phase(root, args.phase))
        elif args.command == "validate":
            validate_phase(root, args.phase)
            print("phase validation passed")
        else:
            open_pr(root, args.phase)
            print("PR auto-merge requested")
    except (OSError, json.JSONDecodeError, PhaseWorktreeError) as exc:
        print(f"phase {args.command} blocked: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
