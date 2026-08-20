#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
payload_file="${TMPDIR:-/tmp}/codex-pre-commit-validation.$$"
cat > "$payload_file"

HARNESS_ROOT="$ROOT" python3 - "$payload_file" <<'PY'
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def load_payload(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def extract_command(payload: dict) -> str:
    tool_input = payload.get("tool_input") or payload.get("input") or {}
    if isinstance(tool_input, dict):
        command = tool_input.get("command") or tool_input.get("cmd") or ""
        return command if isinstance(command, str) else ""
    return ""


def is_git_commit(command: str) -> bool:
    return bool(re.search(r"(^|[;&|]\s*)git\s+commit(\s|$)", command))


def load_stop_checks(cwd: Path):
    config_path = cwd / ".harness/validation.json"
    if not config_path.exists():
        return ()
    try:
        sys.path.insert(0, os.environ["HARNESS_ROOT"])
        from scripts.harness_validation import get_stop_checks, load_validation_config

        return get_stop_checks(load_validation_config(config_path))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid Harness validation profile: {exc}") from exc


def sanitize_output(value: str) -> str:
    try:
        sys.path.insert(0, os.environ["HARNESS_ROOT"])
        from scripts.step_contracts import sanitize_log

        return sanitize_log(value)
    except (ImportError, ValueError):
        return value[-3000:]


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": reason,
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
            },
            ensure_ascii=False,
        )
    )


def main() -> int:
    payload = load_payload(sys.argv[1])
    command = extract_command(payload)
    if not is_git_commit(command):
        return 0

    cwd = Path(payload.get("cwd") or ".").resolve()
    try:
        commands = load_stop_checks(cwd)
    except ValueError as exc:
        deny(str(exc))
        return 0
    if not commands:
        return 0

    failures: list[str] = []
    for configured in commands:
        command_parts = list(configured.command)
        try:
            result = run_command(command_parts, cwd)
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"`{' '.join(command_parts)}` failed: {exc}")
            continue
        if result.returncode != 0:
            output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
            failures.append(
                f"`{' '.join(command_parts)}` failed with exit code {result.returncode}.\n"
                f"{sanitize_output(output[-3000:])}"
            )

    if failures:
        deny(
            "Pre-commit project validation failed. Fix configured checks before committing:\n\n"
            + "\n\n".join(failures)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

status=$?
rm -f "$payload_file"
exit "$status"
