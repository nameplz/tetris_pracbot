#!/usr/bin/env python3
"""Run available project validation commands when a Codex turn stops."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.harness_validation import (  # noqa: E402
    HarnessCommand,
    HarnessValidationError,
    get_stop_checks,
    load_validation_config,
)
from scripts.step_contracts import sanitize_log  # noqa: E402



def _read_payload() -> dict:
    try:
        return json.load(sys.stdin)
    except json.JSONDecodeError:
        return {}


def _load_stop_checks(cwd: Path) -> tuple[HarnessCommand, ...]:
    config_path = cwd / ".harness/validation.json"
    if not config_path.exists():
        return ()
    try:
        return get_stop_checks(load_validation_config(config_path))
    except (HarnessValidationError, OSError) as exc:
        raise ValueError(f"invalid Harness validation profile: {exc}") from exc


def _run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=90,
    )


def main() -> int:
    payload = _read_payload()
    cwd = Path(payload.get("cwd") or ".").resolve()
    if payload.get("stop_hook_active"):
        print(json.dumps({"continue": True}))
        return 0

    try:
        commands = _load_stop_checks(cwd)
    except ValueError as exc:
        print(json.dumps({"decision": "block", "reason": str(exc)}, ensure_ascii=False))
        return 0
    if not commands:
        print(json.dumps({"continue": True}))
        return 0

    failures: list[str] = []
    for command in commands:
        try:
            result = _run_command(list(command.command), cwd)
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append(f"`{' '.join(command.command)}` failed: {sanitize_log(str(exc))}")
            continue
        if result.returncode != 0:
            output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
            failures.append(
                f"`{' '.join(command.command)}` failed with exit code {result.returncode}.\n"
                f"{sanitize_log(output[-3000:])}"
            )

    if not failures:
        print(json.dumps({"continue": True}))
        return 0

    print(
        json.dumps(
            {
                "decision": "block",
                "reason": "Project validation failed. Fix the following before finishing:\n\n"
                + "\n\n".join(failures),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
