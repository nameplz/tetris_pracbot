#!/usr/bin/env python3
"""Typed, validated contracts shared by Harness step agents."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
import re
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Protocol


PHASE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
INITIAL_COMPLETION_CONDITION_COUNT = 10
MAX_COMPLETION_CONDITIONS = 100
MAX_COMPLETION_CONDITIONS_LENGTH = 20_000
DEFAULT_COMPLETION_CRITERIA_PATH = "docs/completion-criteria.md"
REQUIRED_REVIEW_CHECKS = (
    "unit-tests",
    "integration-tests",
    "ruff",
    "mypy",
    "pytest",
    "coverage",
)
REQUIRED_SECURITY_CHECKS = ("yaml", "paths", "inputs", "logs")
REVIEW_COMMAND_TOKENS = {
    "unit-tests": "pytest",
    "integration-tests": "pytest",
    "ruff": "ruff",
    "mypy": "mypy",
    "pytest": "pytest",
    "coverage": "--cov-fail-under=80",
}
SENSITIVE_LOG_PATTERNS = (
    (
        re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+"),
        "[REDACTED_AUTHORIZATION]",
    ),
    (
        re.compile(
            r'(?i)(["\']?(?:api[_-]?key|authorization|password|secret|token)["\']?\s*[:=]\s*["\']?)([^"\'\s,;}\]]+)'
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(
            r"(?i)(\b(?:api[_-]?key|authorization|password|secret|token)\b\s*[:=]\s*)[^\s,;]+"
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED_EMAIL]"),
)
CRITERION_EVIDENCE_RE = re.compile(r"^[^:\r\n]+:\d+(?:-\d+)?(?:\s.*)?$")


class AgentRole(StrEnum):
    IMPLEMENTATION = "implementation"
    CODE_REVIEW = "code-review"
    TEST = "test"
    SECURITY_REVIEW = "security-review"


class AgentStatus(StrEnum):
    COMPLETED = "completed"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    BLOCKED = "blocked"


class PipelineStatus(StrEnum):
    COMPLETED = "completed"
    ERROR = "error"
    BLOCKED = "blocked"


class ReviewContractError(ValueError):
    """Raised when a review result does not satisfy the read-only review contract."""


class StepPipelineError(RuntimeError):
    """Raised for invalid orchestration state or a main-agent action failure."""


@dataclass(frozen=True)
class CheckResult:
    """One command or security check reported by a reviewer."""

    name: str
    command: tuple[str, ...]
    passed: bool
    output: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("check name must be a non-empty string")
        if not isinstance(self.command, tuple) or not self.command or not all(
            isinstance(part, str) and part for part in self.command
        ):
            raise ValueError("check command must be a non-empty tuple[str, ...]")
        object.__setattr__(
            self,
            "command",
            tuple(sanitize_log(part, max_length=512) for part in self.command),
        )
        if not isinstance(self.passed, bool):
            raise ValueError("check passed must be boolean")
        if not isinstance(self.output, str):
            raise ValueError("check output must be a string")
        object.__setattr__(self, "output", sanitize_log(self.output))


@dataclass(frozen=True)
class ReviewFinding:
    """A review issue that the implementation agent can act on."""

    severity: str
    title: str
    detail: str
    recommendation: str
    blocking: bool = True

    def __post_init__(self) -> None:
        if self.severity not in {"critical", "high", "medium", "low", "info"}:
            raise ValueError("finding severity is invalid")
        for name, value in (
            ("title", self.title),
            ("detail", self.detail),
            ("recommendation", self.recommendation),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"finding {name} must be a non-empty string")
        object.__setattr__(self, "title", sanitize_log(self.title))
        object.__setattr__(self, "detail", sanitize_log(self.detail))
        object.__setattr__(self, "recommendation", sanitize_log(self.recommendation))
        if not isinstance(self.blocking, bool):
            raise ValueError("finding blocking must be boolean")


@dataclass(frozen=True)
class CompletionCriterionReview:
    """One code-review result mapped to one completion criterion."""

    number: int
    status: str
    evidence: str
    recommendation: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.number, int) or isinstance(self.number, bool) or self.number < 1:
            raise ValueError("criterion number must be a positive integer")
        if self.status not in {"pass", "fail"}:
            raise ValueError("criterion status must be pass or fail")
        if not isinstance(self.evidence, str) or not self.evidence.strip():
            raise ValueError("criterion evidence must be a non-empty string")
        if not CRITERION_EVIDENCE_RE.fullmatch(self.evidence.strip()):
            raise ValueError("criterion evidence must include path:line")
        if self.status == "fail" and (
            not isinstance(self.recommendation, str) or not self.recommendation.strip()
        ):
            raise ValueError("failed criterion requires a recommendation")
        object.__setattr__(self, "evidence", sanitize_log(self.evidence, max_length=2000))
        object.__setattr__(
            self,
            "recommendation",
            sanitize_log(self.recommendation, max_length=2000),
        )


@dataclass(frozen=True)
class AgentRequest:
    """A constrained request sent by the main session to one sub-agent."""

    phase: str
    step: int
    step_name: str
    role: AgentRole
    prompt: str
    changed_files: tuple[str, ...] = ()
    feedback: str = ""
    read_only: bool = False
    allow_write: bool = False
    allow_commit: bool = False

    def __post_init__(self) -> None:
        validate_phase_and_step(self.phase, self.step, self.step_name)
        if not isinstance(self.role, AgentRole):
            raise ValueError("agent role is invalid")
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError("agent prompt must be a non-empty string")
        object.__setattr__(self, "changed_files", validate_relative_paths(self.changed_files))
        if not isinstance(self.feedback, str):
            raise ValueError("agent feedback must be a string")
        object.__setattr__(self, "feedback", sanitize_log(self.feedback))
        if not isinstance(self.read_only, bool) or not isinstance(self.allow_write, bool):
            raise ValueError("agent access flags must be boolean")
        if not isinstance(self.allow_commit, bool):
            raise ValueError("agent allow_commit must be boolean")
        if self.read_only and self.allow_write:
            raise ValueError("read-only agent cannot be granted write access")
        if self.read_only and self.allow_commit:
            raise ValueError("read-only agent cannot commit")


@dataclass(frozen=True)
class AgentResult:
    """Validated result returned by a worker or reviewer."""

    role: AgentRole
    status: AgentStatus
    summary: str
    changed_files: tuple[str, ...] = ()
    findings: tuple[ReviewFinding, ...] = ()
    criteria_reviews: tuple[CompletionCriterionReview, ...] = ()
    validation: tuple[CheckResult, ...] = ()
    security_checks: tuple[CheckResult, ...] = ()
    external_behavior_verified: bool = False
    customer_data_exposure: bool = False
    committed: bool = False
    log: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.role, AgentRole):
            raise ValueError("agent result role is invalid")
        if not isinstance(self.status, AgentStatus):
            raise ValueError("agent result status is invalid")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("agent summary must be a non-empty string")
        object.__setattr__(self, "summary", sanitize_log(self.summary))
        object.__setattr__(self, "changed_files", validate_relative_paths(self.changed_files))
        if not all(isinstance(item, ReviewFinding) for item in self.findings):
            raise ValueError("findings must contain ReviewFinding values")
        if not all(isinstance(item, CompletionCriterionReview) for item in self.criteria_reviews):
            raise ValueError("criteria_reviews must contain CompletionCriterionReview values")
        if not all(isinstance(item, CheckResult) for item in self.validation):
            raise ValueError("validation must contain CheckResult values")
        if not all(isinstance(item, CheckResult) for item in self.security_checks):
            raise ValueError("security_checks must contain CheckResult values")
        for name, value in (
            ("external_behavior_verified", self.external_behavior_verified),
            ("customer_data_exposure", self.customer_data_exposure),
            ("committed", self.committed),
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be boolean")
        if not isinstance(self.log, str):
            raise ValueError("agent log must be a string")
        object.__setattr__(self, "log", sanitize_log(self.log))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AgentResult":
        """Parse an untrusted JSON-like worker payload at the orchestration boundary."""

        if not isinstance(payload, Mapping):
            raise ValueError("agent result must be an object")
        try:
            role = AgentRole(payload["role"])
            status = AgentStatus(payload["status"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("agent result role or status is invalid") from exc
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError("agent result summary must be a non-empty string")
        return cls(
            role=role,
            status=status,
            summary=summary,
            changed_files=_string_tuple(payload.get("changed_files", ()), "changed_files"),
            findings=tuple(
                _finding_from_payload(item)
                for item in _sequence(payload.get("findings", ()), "findings")
            ),
            criteria_reviews=tuple(
                _criteria_review_from_payload(item)
                for item in _sequence(payload.get("criteria_reviews", ()), "criteria_reviews")
            ),
            validation=tuple(
                _check_from_payload(item)
                for item in _sequence(payload.get("validation", ()), "validation")
            ),
            security_checks=tuple(
                _check_from_payload(item)
                for item in _sequence(payload.get("security_checks", ()), "security_checks")
            ),
            external_behavior_verified=_boolean_value(
                payload.get("external_behavior_verified", False), "external_behavior_verified"
            ),
            customer_data_exposure=_boolean_value(
                payload.get("customer_data_exposure", False), "customer_data_exposure"
            ),
            committed=_boolean_value(payload.get("committed", False), "committed"),
            log=_string_value(payload.get("log", ""), "log"),
        )


@dataclass(frozen=True)
class CIResult:
    """The result of the post-PR CI gate."""

    status: str
    failures: tuple[str, ...] = ()
    log: str = ""

    def __post_init__(self) -> None:
        if self.status not in {"passed", "failed", "blocked", "pending"}:
            raise ValueError("CI status is invalid")
        if not all(isinstance(item, str) and item.strip() for item in self.failures):
            raise ValueError("CI failures must be non-empty strings")
        if not isinstance(self.log, str):
            raise ValueError("CI log must be a string")
        object.__setattr__(self, "failures", tuple(sanitize_log(item) for item in self.failures))
        object.__setattr__(self, "log", sanitize_log(self.log))

    @property
    def ok(self) -> bool:
        return self.status == "passed" and not self.failures

    @classmethod
    def passed(cls) -> "CIResult":
        return cls(status="passed")

    @classmethod
    def failed(cls, failures: Sequence[str], log: str = "") -> "CIResult":
        return cls(status="failed", failures=tuple(failures), log=log)


@dataclass(frozen=True)
class PipelineResult:
    status: PipelineStatus
    attempts: int
    changed_files: tuple[str, ...] = ()
    commit_sha: str | None = None
    errors: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    completion_conditions: tuple[str, ...] = ()


class AgentRunner(Protocol):
    """The main session's adapter for launching a sub-agent."""

    def run(self, request: AgentRequest) -> AgentResult:
        ...


class MainActions(Protocol):
    """Operations reserved for the main agent after all reviews pass."""

    def commit(self, *, phase: str, step: int, changed_files: tuple[str, ...], message: str) -> str:
        ...

    def check_ci(self, *, phase: str, commit_sha: str) -> CIResult:
        ...

    def merge(self, *, phase: str, commit_sha: str) -> None:
        ...


def validate_phase_and_step(phase: str, step: int, step_name: str) -> None:
    if not isinstance(phase, str) or not PHASE_RE.fullmatch(phase):
        raise ValueError("phase must be a kebab-case slug")
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        raise ValueError("step must be a non-negative integer")
    if not isinstance(step_name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", step_name):
        raise ValueError("step_name must be a kebab-case slug")


def validate_completion_conditions(
    conditions: Sequence[str], *, confirmed: bool
) -> tuple[str, ...]:
    """Validate the initial ten-condition draft or a confirmed variable-size list."""

    if not isinstance(confirmed, bool):
        raise ValueError("confirmed must be boolean")
    if isinstance(conditions, (str, bytes)) or not isinstance(conditions, Sequence):
        raise ValueError("completion conditions must be a sequence of strings")
    normalized: list[str] = []
    seen: set[str] = set()
    total_length = 0
    for condition in conditions:
        if not isinstance(condition, str):
            raise ValueError("completion conditions must contain strings")
        value = condition.strip()
        if not value:
            raise ValueError("completion condition must be non-empty")
        if "\n" in value or "\r" in value:
            raise ValueError("completion condition must be one line")
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("completion condition contains a control character")
        if len(value) > 2000:
            raise ValueError("completion condition is too long")
        total_length += len(value.encode("utf-8"))
        if total_length > MAX_COMPLETION_CONDITIONS_LENGTH:
            raise ValueError("completion conditions are too large")
        if value in seen:
            raise ValueError("completion conditions must be unique")
        seen.add(value)
        normalized.append(value)

    if len(normalized) > MAX_COMPLETION_CONDITIONS:
        raise ValueError(f"completion conditions cannot exceed {MAX_COMPLETION_CONDITIONS} items")
    if confirmed and not normalized:
        raise ValueError("confirmed completion conditions must not be empty")
    if not confirmed and len(normalized) != INITIAL_COMPLETION_CONDITION_COUNT:
        raise ValueError(
            "unconfirmed completion conditions must contain exactly "
            f"{INITIAL_COMPLETION_CONDITION_COUNT} items"
        )
    return tuple(normalized)


def save_completion_criteria(
    root: Path, relative_path: str, conditions: Sequence[str]
) -> Path:
    """Write confirmed criteria to one safe Markdown path under the workspace."""

    if not isinstance(root, Path):
        raise ValueError("root must be a Path")
    normalized_conditions = validate_completion_conditions(conditions, confirmed=True)
    if not isinstance(relative_path, str) or not relative_path.lower().endswith(".md"):
        raise ValueError("completion criteria path must be a Markdown file")
    normalized_path = validate_paths_under_root(root, (relative_path,))[0]
    target = root.resolve() / normalized_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_completion_criteria(normalized_conditions), encoding="utf-8")
    return target


def render_completion_criteria(conditions: Sequence[str]) -> str:
    """Render validated confirmed criteria deterministically."""

    normalized_conditions = validate_completion_conditions(conditions, confirmed=True)
    return (
        "# Completion Criteria\n\n"
        f"현재 확정 조건 수: {len(normalized_conditions)}\n\n"
        + "\n".join(f"- [ ] {condition}" for condition in normalized_conditions)
        + "\n"
    )


def validate_completion_reviews(
    reviews: Sequence[CompletionCriterionReview], conditions: Sequence[str]
) -> None:
    """Require exactly one pass/fail review with evidence for every condition."""

    expected = set(range(1, len(conditions) + 1))
    if len(reviews) != len(expected):
        raise ReviewContractError(
            f"code review must report {len(expected)} completion criteria"
        )
    numbers = [review.number for review in reviews]
    if set(numbers) != expected or len(numbers) != len(set(numbers)):
        raise ReviewContractError("code review criteria numbers must match 1..N exactly")


def validate_relative_paths(paths: Sequence[str]) -> tuple[str, ...]:
    """Return canonical relative paths and reject traversal or absolute paths."""

    if isinstance(paths, (str, bytes)) or not isinstance(paths, Sequence):
        raise ValueError("paths must be a sequence of strings")
    result: list[str] = []
    seen: set[str] = set()
    for raw_path in paths:
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("path must be a non-empty string")
        normalized = raw_path.replace("\\", "/")
        if (
            "\x00" in normalized
            or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
            or normalized.startswith(("/", "~"))
            or re.match(r"^[A-Za-z]:", normalized)
            or normalized.endswith("/")
        ):
            raise ValueError(f"unsafe path: {raw_path}")
        path = PurePosixPath(normalized)
        if path == PurePosixPath(".") or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError(f"unsafe path: {raw_path}")
        canonical = path.as_posix()
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return tuple(result)


def validate_paths_under_root(root: Path, paths: Sequence[str]) -> tuple[str, ...]:
    """Reject relative paths whose symlinks resolve outside the target workspace."""

    if not isinstance(root, Path):
        raise ValueError("root must be a Path")
    normalized = validate_relative_paths(paths)
    resolved_root = root.resolve()
    for relative in normalized:
        candidate = (resolved_root / relative).resolve(strict=False)
        try:
            candidate.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"path resolves outside workspace: {relative}") from exc
    return normalized


def sanitize_log(value: str, *, max_length: int = 4000) -> str:
    """Redact credentials and customer email addresses before a log is persisted."""

    if not isinstance(value, str):
        raise ValueError("log must be a string")
    if not isinstance(max_length, int) or isinstance(max_length, bool) or max_length < 1:
        raise ValueError("max_length must be a positive integer")
    redacted = value
    for pattern, replacement in SENSITIVE_LOG_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    if len(redacted) <= max_length:
        return redacted
    return redacted[: max_length - 1] + "…"


def validate_review_result(
    result: AgentResult, *, completion_conditions: Sequence[str] = ()
) -> None:
    """Validate the code-review/test-agent contract without deciding findings."""

    errors: list[str] = []
    if result.role not in {AgentRole.CODE_REVIEW, AgentRole.TEST}:
        errors.append("result is not from a code review or test agent")
    if result.committed:
        errors.append("review agent reported a commit")
    if result.changed_files:
        errors.append("review agent changed files")
    errors.extend(_check_name_errors(result.validation, REQUIRED_REVIEW_CHECKS, "review"))
    checks = {check.name: check for check in result.validation}
    for required in REQUIRED_REVIEW_CHECKS:
        check = checks.get(required)
        if check is None:
            errors.append(f"review did not run {required}")
        else:
            if not check.passed:
                errors.append(f"review check failed: {required}")
            command = " ".join(check.command).lower()
            expected_token = REVIEW_COMMAND_TOKENS[required]
            if expected_token not in command:
                errors.append(f"review command for {required} did not execute {expected_token}")
    if not result.external_behavior_verified:
        errors.append("review did not verify external behavior")
    if result.role == AgentRole.CODE_REVIEW and completion_conditions:
        try:
            validate_completion_reviews(result.criteria_reviews, completion_conditions)
        except ReviewContractError as exc:
            errors.append(str(exc))
    if errors:
        raise ReviewContractError("; ".join(errors))


def validate_implementation_result(result: AgentResult) -> None:
    """Require implementation output to include a test change and no commit."""

    if result.role != AgentRole.IMPLEMENTATION:
        raise ValueError("result is not from the implementation agent")
    if result.committed:
        raise ValueError("implementation agent must not commit")
    test_change = any(_looks_like_test_path(path) for path in result.changed_files)
    if not test_change:
        raise ValueError("implementation did not add or update a test file")


def _looks_like_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    filename = parts[-1]
    return (
        any(part in {"test", "tests", "__tests__", "e2e"} for part in parts[:-1])
        or filename.startswith("test_")
        or ".test." in filename
        or ".spec." in filename
    )


def validate_security_result(result: AgentResult) -> None:
    """Validate the security review contract without hiding blocking findings."""

    errors: list[str] = []
    if result.role != AgentRole.SECURITY_REVIEW:
        errors.append("result is not from the security review agent")
    if result.committed:
        errors.append("security review agent reported a commit")
    if result.changed_files:
        errors.append("security review agent changed files")
    errors.extend(_check_name_errors(result.security_checks, REQUIRED_SECURITY_CHECKS, "security"))
    checks = {check.name: check for check in result.security_checks}
    for required in REQUIRED_SECURITY_CHECKS:
        check = checks.get(required)
        if check is None:
            errors.append(f"security review did not check {required}")
        elif not check.passed:
            errors.append(f"security check failed: {required}")
    if result.customer_data_exposure:
        errors.append("security review reported customer data exposure")
    if errors:
        raise ReviewContractError("; ".join(errors))


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be a list")
    return value


def _check_name_errors(
    checks: Sequence[CheckResult], required: Sequence[str], label: str
) -> list[str]:
    names = [check.name for check in checks]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    unknown = sorted(set(names) - set(required))
    errors: list[str] = []
    if duplicates:
        errors.append(f"{label} checks contain duplicates: {', '.join(duplicates)}")
    if unknown:
        errors.append(f"{label} checks contain unknown names: {', '.join(unknown)}")
    return errors


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    items = _sequence(value, name)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{name} must contain strings")
    return tuple(items)


def _string_value(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _boolean_value(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _finding_from_payload(value: Any) -> ReviewFinding:
    if not isinstance(value, Mapping):
        raise ValueError("finding must be an object")
    return ReviewFinding(
        severity=_string_value(value.get("severity"), "finding.severity"),
        title=_string_value(value.get("title"), "finding.title"),
        detail=_string_value(value.get("detail"), "finding.detail"),
        recommendation=_string_value(value.get("recommendation"), "finding.recommendation"),
        blocking=_boolean_value(value.get("blocking", True), "finding.blocking"),
    )


def _criteria_review_from_payload(value: Any) -> CompletionCriterionReview:
    if not isinstance(value, Mapping):
        raise ValueError("criterion review must be an object")
    return CompletionCriterionReview(
        number=value.get("number"),
        status=_string_value(value.get("status"), "criterion_review.status"),
        evidence=_string_value(value.get("evidence"), "criterion_review.evidence"),
        recommendation=_string_value(
            value.get("recommendation", ""), "criterion_review.recommendation"
        ),
    )


def _check_from_payload(value: Any) -> CheckResult:
    if not isinstance(value, Mapping):
        raise ValueError("check must be an object")
    return CheckResult(
        name=_string_value(value.get("name"), "check.name"),
        command=_string_tuple(value.get("command"), "check.command"),
        passed=_boolean_value(value.get("passed"), "check.passed"),
        output=_string_value(value.get("output", ""), "check.output"),
    )
