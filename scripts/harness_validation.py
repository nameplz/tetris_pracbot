#!/usr/bin/env python3
"""Shared validation helpers for Harness skeleton tooling."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class HarnessValidationError(ValueError):
    """Raised when Harness config is invalid."""


@dataclass(frozen=True)
class HarnessCommand:
    name: str
    command: tuple[str, ...]
    reason: str
    roles: tuple[str, ...] = ("validation", "stop")
    required: bool = True


@dataclass(frozen=True)
class ValidationConfig:
    schema_version: int
    mode: str
    profiles: tuple[str, ...]
    commands: tuple[HarnessCommand, ...]
    checks: dict[str, bool]
    stop_checks: tuple[HarnessCommand, ...] = ()
    review_checks: dict[str, tuple[HarnessCommand, ...]] = field(default_factory=dict)
    step_policies: dict[str, str] = field(default_factory=dict)
    review_mutation_ignore: tuple[str, ...] = ()
    max_completion_conditions: int = 100


@dataclass
class ValidationResult:
    root: Path
    configured: bool
    profiles: list[str]
    errors: list[str]
    command_results: list[dict[str, Any]]

    @property
    def ok(self) -> bool:
        return not self.errors


DEFAULT_CHECKS = {"docs": True, "deploy": True, "phase": True}
DEFAULT_CONFIG = ValidationConfig(
    schema_version=1,
    mode="language-neutral",
    profiles=(),
    commands=(),
    checks=DEFAULT_CHECKS.copy(),
)

DEFAULT_STEP_POLICIES = {
    "feature": "required",
    "bugfix": "regression",
    "refactor": "optional",
    "docs": "none",
    "ci": "none",
    "config": "none",
    "dependency": "optional",
    "metadata": "none",
}
DEFAULT_REVIEW_MUTATION_IGNORES = (
    ".git",
    ".harness/runtime",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".coverage",
)

DOC_FILES = ("docs/PRD.md", "docs/ARCHITECTURE.md", "docs/ADR.md")
PLACEHOLDER_RE = re.compile(r"\{[^{}\n]+\}")
PROFILE_EVIDENCE = {
    "node": ("package.json", "tsconfig.json", "next.config.js", "next.config.mjs", "vite.config.ts"),
    "python": ("pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"),
    "go": ("go.mod",),
    "rust": ("Cargo.toml",),
}
DEPLOY_FILE_NAMES = {
    "Dockerfile",
    "Procfile",
    "app.yaml",
    "cloudbuild.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
    "fly.toml",
    "netlify.toml",
    "railway.json",
    "render.yaml",
    "render.yml",
    "serverless.yml",
    "vercel.json",
}
DEPLOY_DIR_NAMES = {"helm", "k8s", "kubernetes", "terraform", ".netlify", ".vercel"}
UNSAFE_TOKENS = {
    "add",
    "ci",
    "deploy",
    "external-login",
    "install",
    "login",
    "migrate",
    "migration",
    "publish",
    "reset",
    "seed",
    "watch",
}
FORMATTER_TOKENS = {"format", "fmt"}


def detect_profiles(root: Path) -> list[str]:
    root = root.resolve()
    profiles: list[str] = []
    for profile, markers in PROFILE_EVIDENCE.items():
        if any((root / marker).exists() for marker in markers):
            profiles.append(profile)
    return profiles


def active_profiles(root: Path, configured_profiles: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    profiles: list[str] = []
    for profile in [*detect_profiles(root), *configured_profiles]:
        if profile not in seen:
            seen.add(profile)
            profiles.append(profile)
    return profiles


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HarnessValidationError(f"Config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HarnessValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise HarnessValidationError(f"Config must be a JSON object: {path}")
    return data


def load_validation_config(path: Path) -> ValidationConfig:
    data = load_json(path)
    if data.get("schemaVersion") != 1:
        raise HarnessValidationError("validation schemaVersion must be 1")
    mode = data.get("mode", "language-neutral")
    if mode not in {"language-neutral", "profile"}:
        raise HarnessValidationError('validation mode must be "language-neutral" or "profile"')

    profiles = data.get("profiles", [])
    if not isinstance(profiles, list) or not all(isinstance(item, str) for item in profiles):
        raise HarnessValidationError("profiles must be a list of strings")
    profile = data.get("profile")
    if profile is not None:
        if not isinstance(profile, str) or not profile.strip():
            raise HarnessValidationError("profile must be a non-empty string")
        profiles = [*profiles, profile]
    profiles = _unique_strings(profiles, "profiles")

    commands_raw = data.get("commands", data.get("validationChecks", []))
    if not isinstance(commands_raw, list):
        raise HarnessValidationError("commands must be a list")
    commands = tuple(validate_command_item(item) for item in commands_raw)
    _ensure_unique_command_names(commands)
    command_map = {command.name: command for command in commands}

    stop_raw = data.get("stopChecks")
    if stop_raw is None:
        stop_checks = tuple(command for command in commands if "stop" in command.roles)
    else:
        stop_checks, command_map = _resolve_commands(stop_raw, command_map, "stopChecks")

    review_checks: dict[str, tuple[HarnessCommand, ...]] = {}
    review_raw = data.get("reviewChecks")
    if review_raw is None:
        for role in ("code-review", "test-review"):
            review_checks[role] = tuple(
                command for command in command_map.values() if role in command.roles
            )
    else:
        if not isinstance(review_raw, dict):
            raise HarnessValidationError("reviewChecks must be an object")
        for role, raw_checks in review_raw.items():
            normalized_role = _review_role_name(role)
            resolved, command_map = _resolve_commands(
                raw_checks, command_map, f"reviewChecks.{role}"
            )
            review_checks[normalized_role] = resolved

    checks_raw = data.get("checks", DEFAULT_CHECKS)
    if not isinstance(checks_raw, dict):
        raise HarnessValidationError("checks must be an object")
    checks = DEFAULT_CHECKS.copy()
    for name in DEFAULT_CHECKS:
        if name in checks_raw:
            value = checks_raw[name]
            if not isinstance(value, bool):
                raise HarnessValidationError(f"checks.{name} must be boolean")
            checks[name] = value

    step_policies = _load_step_policies(data.get("stepPolicies", data.get("stepValidation", {})))
    mutation_ignore = _load_mutation_ignore(data.get("reviewMutationIgnore", ()))
    max_completion_conditions = data.get("maxCompletionConditions", 100)
    if (
        not isinstance(max_completion_conditions, int)
        or isinstance(max_completion_conditions, bool)
        or max_completion_conditions < 1
    ):
        raise HarnessValidationError("maxCompletionConditions must be a positive integer")

    return ValidationConfig(
        schema_version=1,
        mode=mode,
        profiles=tuple(profiles),
        commands=tuple(command_map.values()),
        checks=checks,
        stop_checks=stop_checks,
        review_checks=review_checks,
        step_policies=step_policies,
        review_mutation_ignore=mutation_ignore,
        max_completion_conditions=max_completion_conditions,
    )


def validate_command_item(item: Any) -> HarnessCommand:
    if not isinstance(item, dict):
        raise HarnessValidationError("command entry must be an object")

    name = item.get("name")
    command = item.get("command")
    reason = item.get("reason")
    if not isinstance(name, str) or not name.strip():
        raise HarnessValidationError("command.name must be non-empty string")
    if not isinstance(reason, str) or not reason.strip():
        raise HarnessValidationError("command.reason must be non-empty string")
    if not isinstance(command, list) or not command:
        raise HarnessValidationError("command.command must be a non-empty list[str]")
    if not all(isinstance(part, str) and part for part in command):
        raise HarnessValidationError("command.command must contain only non-empty strings")

    roles = item.get("roles", ["validation", "stop"])
    if not isinstance(roles, list) or not roles or not all(isinstance(role, str) and role for role in roles):
        raise HarnessValidationError("command.roles must be a non-empty list[str]")
    normalized_roles = _command_roles(roles)
    required = item.get("required", True)
    if not isinstance(required, bool):
        raise HarnessValidationError("command.required must be boolean")

    reason_text = unsafe_command_reason(command)
    if reason_text:
        raise HarnessValidationError(f"Unsafe command {name}: {reason_text}")
    return HarnessCommand(
        name=name,
        command=tuple(command),
        reason=reason,
        roles=normalized_roles,
        required=required,
    )


def get_stop_checks(config: ValidationConfig) -> tuple[HarnessCommand, ...]:
    """Return project-defined checks used by stop/pre-commit gates."""

    return config.stop_checks


def get_review_checks(config: ValidationConfig, role: str) -> tuple[HarnessCommand, ...]:
    """Return only checks assigned to one reviewer role."""

    return config.review_checks.get(_review_role_name(role), ())


def step_validation_policy(config: ValidationConfig, step_kind: str) -> str:
    if not isinstance(step_kind, str) or not step_kind.strip():
        raise HarnessValidationError("step kind must be a non-empty string")
    return config.step_policies.get(step_kind, DEFAULT_STEP_POLICIES.get(step_kind, "required"))


def _resolve_commands(
    raw_checks: Any,
    command_map: dict[str, HarnessCommand],
    field_name: str,
) -> tuple[tuple[HarnessCommand, ...], dict[str, HarnessCommand]]:
    if not isinstance(raw_checks, list):
        raise HarnessValidationError(f"{field_name} must be a list")
    resolved: list[HarnessCommand] = []
    updated = dict(command_map)
    for item in raw_checks:
        if isinstance(item, str):
            command = updated.get(item)
            if command is None:
                raise HarnessValidationError(f"{field_name} references unknown command: {item}")
        elif isinstance(item, dict):
            command = validate_command_item(item)
            existing = updated.get(command.name)
            if existing is not None and existing != command:
                raise HarnessValidationError(f"command {command.name} is defined inconsistently")
            updated[command.name] = command
        else:
            raise HarnessValidationError(f"{field_name} entries must be command names or objects")
        if command not in resolved:
            resolved.append(command)
    return tuple(resolved), updated


def _ensure_unique_command_names(commands: tuple[HarnessCommand, ...]) -> None:
    names = [command.name for command in commands]
    if len(names) != len(set(names)):
        raise HarnessValidationError("command names must be unique")


def _review_role_name(role: str) -> str:
    if not isinstance(role, str) or not role.strip():
        raise HarnessValidationError("review role must be a non-empty string")
    normalized = role.strip().lower()
    aliases = {
        "code": "code-review",
        "code-review": "code-review",
        "test": "test-review",
        "test-review": "test-review",
    }
    if normalized not in aliases:
        raise HarnessValidationError(f"unsupported review role: {role}")
    return aliases[normalized]


def _command_roles(roles: list[str]) -> tuple[str, ...]:
    aliases = {
        "code": "code-review",
        "code-review": "code-review",
        "test": "test-review",
        "test-review": "test-review",
        "validation": "validation",
        "stop": "stop",
    }
    normalized: list[str] = []
    for role in _unique_strings(roles, "command.roles"):
        if role not in aliases:
            raise HarnessValidationError(f"unsupported command role: {role}")
        value = aliases[role]
        if value not in normalized:
            normalized.append(value)
    return tuple(normalized)


def _load_step_policies(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HarnessValidationError("stepPolicies must be an object")
    allowed = {"required", "regression", "optional", "none"}
    policies: dict[str, str] = {}
    for kind, value in raw.items():
        if not isinstance(kind, str) or not kind.strip():
            raise HarnessValidationError("step policy name must be a non-empty string")
        if isinstance(value, dict):
            value = value.get("testChange", value.get("test_change"))
        if value not in allowed:
            raise HarnessValidationError(
                f"stepPolicies.{kind} must be one of {', '.join(sorted(allowed))}"
            )
        policies[kind] = value
    return policies


def _load_mutation_ignore(raw: Any) -> tuple[str, ...]:
    if raw in (None, ()):
        raw = []
    if not isinstance(raw, list):
        raise HarnessValidationError("reviewMutationIgnore must be a list")
    values = list(DEFAULT_REVIEW_MUTATION_IGNORES)
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise HarnessValidationError("reviewMutationIgnore entries must be non-empty strings")
        normalized = item.strip().replace("\\", "/")
        if not normalized or normalized.startswith(("/", "~")) or ".." in normalized.split("/"):
            raise HarnessValidationError(f"unsafe reviewMutationIgnore path: {item}")
        if normalized not in values:
            values.append(normalized)
    return tuple(values)


def _unique_strings(values: list[str], field_name: str) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            raise HarnessValidationError(f"{field_name} entries must be non-empty strings")
        if normalized not in result:
            result.append(normalized)
    return result


def unsafe_command_reason(command: list[str]) -> str | None:
    lowered = [part.lower() for part in command]
    lowered_base = [Path(part).name.lower() for part in command]
    token_set = set(lowered) | set(lowered_base)

    unsafe = sorted(token_set & UNSAFE_TOKENS)
    if unsafe:
        return f"forbidden token: {unsafe[0]}"

    if token_set & FORMATTER_TOKENS:
        return "formatter rewrite command is forbidden"

    if "ruff" in token_set and "--fix" in token_set:
        return "formatter rewrite command is forbidden"
    if "eslint" in token_set and "--fix" in token_set:
        return "formatter rewrite command is forbidden"
    if "prettier" in token_set and "--write" in token_set:
        return "formatter rewrite command is forbidden"

    check_only = "--check" in token_set or "--check-only" in token_set
    if ("black" in token_set or "isort" in token_set) and not check_only:
        return "formatter rewrite command is forbidden"
    if command[:2] == ["go", "fmt"] or command[:2] == ["cargo", "fmt"]:
        return "formatter rewrite command is forbidden"
    return None


def validate_project(
    *,
    root: Path,
    strict: bool,
    config_path: Path | None,
    run_commands: bool,
) -> ValidationResult:
    root = root.resolve()
    default_config_path = root / ".harness/validation.json"
    selected_config_path = config_path or (default_config_path if default_config_path.exists() else None)
    configured = strict or selected_config_path is not None
    errors: list[str] = []
    command_results: list[dict[str, Any]] = []

    try:
        config = load_validation_config(selected_config_path) if selected_config_path else DEFAULT_CONFIG
    except HarnessValidationError as exc:
        return ValidationResult(root, configured, [], [str(exc)], command_results)

    profiles = active_profiles(root, config.profiles)

    if config.profiles and not config.commands:
        errors.append("configured validation profile must define at least one validation command")

    if config.checks.get("docs", True):
        errors.extend(check_docs(root, configured=configured))
    if config.checks.get("deploy", True):
        errors.extend(check_deploy(root))
    if config.checks.get("phase", True):
        errors.extend(check_phase_metadata(root))

    if run_commands and not errors:
        for command in config.commands:
            result = run_harness_command(root, command)
            command_results.append(result)
            if result["returncode"] != 0:
                errors.append(f"{command.name} failed with exit code {result['returncode']}")

    return ValidationResult(root, configured, profiles, errors, command_results)


def check_docs(root: Path, *, configured: bool) -> list[str]:
    errors: list[str] = []
    for relative in DOC_FILES:
        path = root / relative
        if not path.exists():
            errors.append(f"Missing required doc: {relative}")

    if configured:
        scan_paths = [root / relative for relative in DOC_FILES]
        agents = root / "AGENTS.md"
        if agents.exists():
            scan_paths.append(agents)
        for path in scan_paths:
            if path.exists() and PLACEHOLDER_RE.search(path.read_text(encoding="utf-8")):
                errors.append(f"Unresolved placeholder in configured project: {path.relative_to(root)}")
    return errors


def check_deploy(root: Path) -> list[str]:
    errors: list[str] = []
    ignored_roots = {".git", ".worktrees", ".harness", ".pytest_cache", "node_modules", ".next"}
    for path in root.rglob("*"):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if not relative.parts or relative.parts[0] in ignored_roots or relative.parts[0] == "deploy":
            continue
        if path.is_file() and path.name in DEPLOY_FILE_NAMES:
            errors.append(f"Deployment file must live under deploy/: {relative}")
        if path.is_dir() and path.name in DEPLOY_DIR_NAMES:
            errors.append(f"Deployment directory must live under deploy/: {relative}")
    return errors


def check_phase_metadata(root: Path) -> list[str]:
    index = root / "phases/index.json"
    if not index.exists():
        return []
    try:
        data = load_json(index)
    except HarnessValidationError as exc:
        return [str(exc)]
    phases = data.get("phases")
    if not isinstance(phases, list):
        return ["phases/index.json must contain phases list"]
    errors: list[str] = []
    for item in phases:
        if not isinstance(item, dict):
            errors.append("phase entry must be object")
            continue
        if not isinstance(item.get("dir"), str) or not item["dir"]:
            errors.append("phase entry dir must be non-empty string")
        if item.get("status") not in {"pending", "completed", "error", "blocked"}:
            errors.append("phase entry status is invalid")
    return errors


def run_harness_command(root: Path, command: HarnessCommand) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command.command),
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "name": command.name,
            "command": list(command.command),
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc)[-4000:],
        }
    return {
        "name": command.name,
        "command": list(command.command),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def result_to_json(result: ValidationResult) -> dict[str, Any]:
    return {
        "root": str(result.root),
        "configured": result.configured,
        "profiles": result.profiles,
        "ok": result.ok,
        "errors": result.errors,
        "commandResults": result.command_results,
    }
