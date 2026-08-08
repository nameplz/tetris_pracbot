#!/usr/bin/env python3
"""Run one Harness step through implementation, reviews, CI, and merge."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import cast

from scripts.step_contracts import (
    DEFAULT_COMPLETION_CRITERIA_PATH,
    AgentRequest,
    AgentResult,
    AgentRole,
    AgentRunner,
    AgentStatus,
    CIResult,
    CheckResult,
    CompletionCriterionReview,
    MainActions,
    PipelineResult,
    PipelineStatus,
    ReviewContractError,
    ReviewFinding,
    StepPipelineError,
    render_completion_criteria,
    sanitize_log,
    save_completion_criteria,
    validate_completion_conditions,
    validate_phase_and_step,
    validate_implementation_result,
    validate_paths_under_root,
    validate_relative_paths,
    validate_review_result,
    validate_security_result,
)
from scripts.step_prompts import (
    ci_feedback,
    criteria_feedback,
    finding_feedback,
    implementation_prompt,
    review_prompt,
    security_review_prompt,
)


REVIEW_MUTATION_IGNORES = {
    ".git",
    ".harness/runtime",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".coverage",
}

__all__ = [
    "AgentRequest",
    "AgentResult",
    "AgentRole",
    "AgentRunner",
    "AgentStatus",
    "CIResult",
    "CheckResult",
    "CompletionCriterionReview",
    "MainActions",
    "PipelineResult",
    "PipelineStatus",
    "ReviewContractError",
    "ReviewFinding",
    "StepPipeline",
    "StepPipelineError",
    "sanitize_log",
    "save_completion_criteria",
    "render_completion_criteria",
    "validate_completion_conditions",
    "validate_implementation_result",
    "validate_paths_under_root",
    "validate_relative_paths",
    "validate_review_result",
    "validate_security_result",
]


@dataclass(frozen=True)
class _ReviewRequests:
    code: AgentRequest
    tests: AgentRequest


class StepPipeline:
    """Retry implementation until reviews and post-PR CI permit a merge."""

    def __init__(
        self,
        *,
        runner: AgentRunner,
        actions: MainActions,
        root: Path | None = None,
        max_attempts: int = 3,
    ) -> None:
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        self._runner = runner
        self._actions = actions
        self._root = (root or Path.cwd()).resolve()
        self._max_attempts = max_attempts
        self._pending_conditions: tuple[str, ...] | None = None
        self._criteria_confirmed = False

    def run(
        self,
        *,
        phase: str,
        step: int,
        step_name: str,
        step_spec: str = "",
        completion_conditions: Sequence[str] = (),
        conditions_confirmed: bool = False,
        criteria_path: str = DEFAULT_COMPLETION_CRITERIA_PATH,
    ) -> PipelineResult:
        validate_phase_and_step(phase, step, step_name)
        if not isinstance(step_spec, str):
            raise ValueError("step_spec must be a string")
        if conditions_confirmed:
            conditions = validate_completion_conditions(completion_conditions, confirmed=True)
            if (
                self._pending_conditions is not None
                and not self._criteria_confirmed
                and conditions != self._pending_conditions
            ):
                raise ValueError("confirmation must match the latest completion criteria draft")
            self._criteria_confirmed = True
            self._pending_conditions = conditions
        else:
            conditions = validate_completion_conditions(
                completion_conditions, confirmed=self._pending_conditions is not None
            )
            self._pending_conditions = conditions
            self._criteria_confirmed = False
            return self._result(
                status=PipelineStatus.BLOCKED,
                attempts=0,
                changed_files=(),
                commit_sha=None,
                errors=["completion criteria require user confirmation"],
                events=["completion criteria: awaiting user confirmation"],
                completion_conditions=conditions,
            )
        criteria_root = self._root or Path.cwd().resolve()
        criteria_file = save_completion_criteria(criteria_root, criteria_path, conditions)
        criteria_relative_path = criteria_file.relative_to(criteria_root).as_posix()
        criteria_digest = hashlib.sha256(
            render_completion_criteria(conditions).encode("utf-8")
        ).hexdigest()

        errors: list[str] = []
        events: list[str] = []
        all_changed_files: list[str] = []
        feedback = ""
        last_commit_sha: str | None = None
        events.append(f"completion criteria confirmed: {len(conditions)}")

        for attempt in range(1, self._max_attempts + 1):
            before_implementation = _snapshot_workspace(self._root)
            before_git = _snapshot_git_metadata(self._root)
            events.append(f"attempt {attempt}: implementation")
            implementation = self._run_implementation(
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                feedback=feedback,
                completion_conditions=conditions,
                criteria_path=criteria_relative_path,
                errors=errors,
            )
            if _snapshot_git_metadata(self._root) != before_git:
                message = "implementation modified git metadata"
                errors.append(message)
                restore_error = _restore_completion_criteria(criteria_file, conditions)
                if restore_error:
                    errors.append(restore_error)
                return self._result(
                    status=PipelineStatus.ERROR,
                    attempts=attempt,
                    changed_files=all_changed_files,
                    commit_sha=last_commit_sha,
                    errors=errors,
                    events=events,
                    completion_conditions=conditions,
                )
            if _file_digest(criteria_file) != criteria_digest:
                message = "implementation modified completion criteria file"
                errors.append(message)
                feedback = message
                restore_error = _restore_completion_criteria(criteria_file, conditions)
                if restore_error:
                    errors.append(restore_error)
                continue
            if implementation is None:
                feedback = errors[-1]
                continue
            if implementation.status == AgentStatus.BLOCKED:
                return self._result(
                    status=PipelineStatus.BLOCKED,
                    attempts=attempt,
                    changed_files=all_changed_files,
                    commit_sha=last_commit_sha,
                    errors=errors or [implementation.summary],
                    events=events,
                    completion_conditions=conditions,
                )
            if implementation.status != AgentStatus.COMPLETED or implementation.committed:
                message = "implementation did not complete without committing"
                errors.append(message)
                feedback = f"{message}: {sanitize_log(implementation.summary)}"
                continue
            try:
                validate_implementation_result(implementation)
            except ValueError as exc:
                message = "implementation contract failed: " + sanitize_log(str(exc))
                errors.append(message)
                feedback = message
                continue

            try:
                after_implementation = _snapshot_workspace(self._root)
                actual_changed_files = validate_paths_under_root(
                    self._root, _changed_paths(before_implementation, after_implementation)
                )
                reported_changed_files = validate_paths_under_root(
                    self._root, implementation.changed_files
                )
            except ValueError as exc:
                message = "implementation path validation failed: " + sanitize_log(str(exc))
                errors.append(message)
                feedback = message
                continue
            current_changed_files = tuple(
                _merge_paths(
                    _merge_paths(actual_changed_files, reported_changed_files),
                    (criteria_relative_path,),
                )
            )
            all_changed_files = _merge_paths(all_changed_files, current_changed_files)
            reviews = self._run_parallel_reviews(
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                changed_files=current_changed_files,
                feedback=feedback,
                completion_conditions=conditions,
                criteria_path=criteria_relative_path,
                events=events,
                errors=errors,
            )
            if reviews is None:
                feedback = errors[-1]
                if "review agent modified" in feedback or "review agent violated" in feedback:
                    restore_error = _restore_completion_criteria(criteria_file, conditions)
                    if restore_error:
                        errors.append(restore_error)
                    return self._result(
                        status=PipelineStatus.ERROR,
                        attempts=attempt,
                        changed_files=all_changed_files,
                        commit_sha=last_commit_sha,
                        errors=errors,
                        events=events,
                        completion_conditions=conditions,
                    )
                continue
            review_feedback = self._review_feedback(reviews, conditions, errors)
            if review_feedback:
                feedback = review_feedback
                continue

            security_snapshot = _snapshot_workspace(self._root) if self._root else None
            security_git_snapshot = _snapshot_git_metadata(self._root)
            events.append(f"attempt {attempt}: security review")
            security = self._run_security_review(
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                changed_files=current_changed_files,
                feedback=feedback,
                errors=errors,
            )
            if security is None:
                feedback = errors[-1]
                continue
            if security_snapshot is not None and _snapshot_workspace(self._root) != security_snapshot:
                message = "security review agent modified the workspace"
                errors.append(message)
                restore_error = _restore_completion_criteria(criteria_file, conditions)
                if restore_error:
                    errors.append(restore_error)
                return self._result(
                    status=PipelineStatus.ERROR,
                    attempts=attempt,
                    changed_files=all_changed_files,
                    commit_sha=last_commit_sha,
                    errors=errors,
                    events=events,
                    completion_conditions=conditions,
                )
            if _snapshot_git_metadata(self._root) != security_git_snapshot:
                message = "security review agent modified git metadata"
                errors.append(message)
                restore_error = _restore_completion_criteria(criteria_file, conditions)
                if restore_error:
                    errors.append(restore_error)
                return self._result(
                    status=PipelineStatus.ERROR,
                    attempts=attempt,
                    changed_files=all_changed_files,
                    commit_sha=last_commit_sha,
                    errors=errors,
                    events=events,
                    completion_conditions=conditions,
                )
            security_feedback = self._security_feedback(security, errors)
            if security_feedback:
                feedback = security_feedback
                continue

            commit_result = self._commit_and_check_ci(
                phase=phase,
                step=step,
                step_name=step_name,
                changed_files=current_changed_files,
                attempt=attempt,
                events=events,
                errors=errors,
            )
            if commit_result is None:
                feedback = errors[-1]
                continue
            commit_sha, ci_result = commit_result
            last_commit_sha = commit_sha
            if not ci_result.ok:
                feedback = ci_feedback(ci_result)
                errors.append(feedback)
                events.append(f"attempt {attempt}: CI failed")
                continue

            try:
                self._actions.merge(phase=phase, commit_sha=commit_sha)
            except Exception as exc:  # pragma: no cover - integration adapter failure
                message = "main merge action failed: " + sanitize_log(str(exc))
                errors.append(message)
                return self._result(
                    status=PipelineStatus.ERROR,
                    attempts=attempt,
                    changed_files=all_changed_files,
                    commit_sha=commit_sha,
                    errors=errors,
                    events=events,
                    completion_conditions=conditions,
                )
            events.append(f"attempt {attempt}: merged")
            return self._result(
                status=PipelineStatus.COMPLETED,
                attempts=attempt,
                changed_files=all_changed_files,
                commit_sha=commit_sha,
                errors=errors,
                events=events,
                completion_conditions=conditions,
            )

        return self._result(
            status=PipelineStatus.ERROR,
            attempts=self._max_attempts,
            changed_files=all_changed_files,
            commit_sha=last_commit_sha,
            errors=errors or ["step pipeline exhausted retry attempts"],
            events=events,
            completion_conditions=conditions,
        )

    def _run_implementation(
        self,
        *,
        phase: str,
        step: int,
        step_name: str,
        step_spec: str,
        feedback: str,
        completion_conditions: Sequence[str],
        criteria_path: str,
        errors: list[str],
    ) -> AgentResult | None:
        request = AgentRequest(
            phase=phase,
            step=step,
            step_name=step_name,
            role=AgentRole.IMPLEMENTATION,
            prompt=implementation_prompt(
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                feedback=feedback,
                completion_conditions=completion_conditions,
                criteria_path=criteria_path,
            ),
            feedback=feedback,
            allow_write=True,
        )
        return self._run_agent(request, errors)

    def _run_parallel_reviews(
        self,
        *,
        phase: str,
        step: int,
        step_name: str,
        step_spec: str,
        changed_files: tuple[str, ...],
        feedback: str,
        completion_conditions: Sequence[str],
        criteria_path: str,
        events: list[str],
        errors: list[str],
    ) -> tuple[AgentResult, AgentResult] | None:
        requests = _ReviewRequests(
            code=self._review_request(
                role=AgentRole.CODE_REVIEW,
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                changed_files=changed_files,
                feedback=feedback,
                completion_conditions=completion_conditions,
                criteria_path=criteria_path,
            ),
            tests=self._review_request(
                role=AgentRole.TEST,
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                changed_files=changed_files,
                feedback=feedback,
                completion_conditions=completion_conditions,
                criteria_path=criteria_path,
            ),
        )
        before = _snapshot_workspace(self._root) if self._root else None
        before_git = _snapshot_git_metadata(self._root)
        events.append("code review + test review: parallel")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="harness-review") as pool:
            futures = [
                pool.submit(self._run_agent, request, errors)
                for request in (requests.code, requests.tests)
            ]
            results = [future.result() for future in futures]
        if before is not None and _snapshot_workspace(self._root) != before:
            errors.append("review agent modified the workspace")
            return None
        if _snapshot_git_metadata(self._root) != before_git:
            errors.append("review agent modified git metadata")
            return None
        if any(result is None for result in results):
            return None
        return cast(tuple[AgentResult, AgentResult], (results[0], results[1]))

    @staticmethod
    def _review_request(
        *,
        role: AgentRole,
        phase: str,
        step: int,
        step_name: str,
        step_spec: str,
        changed_files: tuple[str, ...],
        feedback: str,
        completion_conditions: Sequence[str],
        criteria_path: str,
    ) -> AgentRequest:
        return AgentRequest(
            phase=phase,
            step=step,
            step_name=step_name,
            role=role,
            prompt=review_prompt(
                role=role,
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                changed_files=changed_files,
                feedback=feedback,
                completion_conditions=completion_conditions,
                criteria_path=criteria_path,
            ),
            changed_files=changed_files,
            feedback=feedback,
            read_only=True,
        )

    def _run_security_review(
        self,
        *,
        phase: str,
        step: int,
        step_name: str,
        step_spec: str,
        changed_files: tuple[str, ...],
        feedback: str,
        errors: list[str],
    ) -> AgentResult | None:
        request = AgentRequest(
            phase=phase,
            step=step,
            step_name=step_name,
            role=AgentRole.SECURITY_REVIEW,
            prompt=security_review_prompt(
                phase=phase,
                step=step,
                step_name=step_name,
                step_spec=step_spec,
                changed_files=changed_files,
                feedback=feedback,
            ),
            changed_files=changed_files,
            feedback=feedback,
            read_only=True,
        )
        return self._run_agent(request, errors)

    def _run_agent(self, request: AgentRequest, errors: list[str]) -> AgentResult | None:
        try:
            result = self._runner.run(request)
        except Exception as exc:  # pragma: no cover - adapter-specific failure
            errors.append(f"{request.role} agent failed: {sanitize_log(str(exc))}")
            return None
        if not isinstance(result, AgentResult):
            errors.append(f"{request.role} agent returned an invalid result")
            return None
        if result.role != request.role:
            errors.append(f"agent role mismatch: expected {request.role}, got {result.role}")
            return None
        if request.read_only and (result.changed_files or result.committed):
            errors.append(f"{request.role} agent violated read-only contract")
            return None
        return result

    @staticmethod
    def _review_feedback(
        results: tuple[AgentResult, AgentResult],
        completion_conditions: Sequence[str],
        errors: list[str],
    ) -> str:
        feedback: list[str] = []
        for result in results:
            try:
                validate_review_result(result, completion_conditions=completion_conditions)
            except ReviewContractError as exc:
                message = f"{result.role} contract failed: {sanitize_log(str(exc))}"
                errors.append(message)
                feedback.append(message)
                continue
            if result.status not in {AgentStatus.COMPLETED, AgentStatus.PASSED}:
                feedback.append(f"{result.role} reported {result.status}: {sanitize_log(result.summary)}")
            feedback.extend(finding_feedback(result.role, result.findings))
            if result.role == AgentRole.CODE_REVIEW:
                failed_criteria = criteria_feedback(result.criteria_reviews)
                feedback.extend(failed_criteria)
                errors.extend(failed_criteria)
        return "\n".join(feedback)

    @staticmethod
    def _security_feedback(result: AgentResult, errors: list[str]) -> str:
        try:
            validate_security_result(result)
        except ReviewContractError as exc:
            message = f"security review contract failed: {sanitize_log(str(exc))}"
            errors.append(message)
            return message
        feedback: list[str] = []
        if result.status not in {AgentStatus.COMPLETED, AgentStatus.PASSED}:
            feedback.append(f"security review reported {result.status}: {sanitize_log(result.summary)}")
        feedback.extend(finding_feedback(result.role, result.findings))
        return "\n".join(feedback)

    def _commit_and_check_ci(
        self,
        *,
        phase: str,
        step: int,
        step_name: str,
        changed_files: tuple[str, ...],
        attempt: int,
        events: list[str],
        errors: list[str],
    ) -> tuple[str, CIResult] | None:
        events.append(f"attempt {attempt}: main decision")
        try:
            commit_sha = self._actions.commit(
                phase=phase,
                step=step,
                changed_files=changed_files,
                message=f"feat({phase}): step {step} - {step_name}",
            )
            if not isinstance(commit_sha, str) or not commit_sha.strip():
                raise StepPipelineError("main commit action returned an invalid commit SHA")
            events.append(f"attempt {attempt}: committed")
            ci_result = self._actions.check_ci(phase=phase, commit_sha=commit_sha)
            if not isinstance(ci_result, CIResult):
                raise StepPipelineError("main CI action returned an invalid result")
            return commit_sha, ci_result
        except Exception as exc:  # pragma: no cover - integration adapter failure
            errors.append("main action failed: " + sanitize_log(str(exc)))
            return None

    @staticmethod
    def _result(
        *,
        status: PipelineStatus,
        attempts: int,
        changed_files: Sequence[str],
        commit_sha: str | None,
        errors: Sequence[str],
        events: Sequence[str],
        completion_conditions: Sequence[str] = (),
    ) -> PipelineResult:
        return PipelineResult(
            status=status,
            attempts=attempts,
            changed_files=validate_relative_paths(changed_files),
            commit_sha=commit_sha,
            errors=tuple(sanitize_log(error) for error in errors),
            events=tuple(events),
            completion_conditions=tuple(completion_conditions),
        )


def _merge_paths(existing: Sequence[str], new_paths: Sequence[str]) -> list[str]:
    merged = list(validate_relative_paths(existing))
    for path in validate_relative_paths(new_paths):
        if path not in merged:
            merged.append(path)
    return merged


def _changed_paths(before: dict[str, str], after: dict[str, str]) -> tuple[str, ...]:
    paths = set(before) | set(after)
    return tuple(sorted(path for path in paths if before.get(path) != after.get(path)))


def _file_digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _restore_completion_criteria(path: Path, conditions: Sequence[str]) -> str | None:
    try:
        path.write_text(render_completion_criteria(conditions), encoding="utf-8")
    except OSError as exc:
        return "could not restore completion criteria file: " + sanitize_log(str(exc))
    return None


def _snapshot_git_metadata(root: Path | None) -> dict[str, str]:
    if root is None:
        return {}
    git_entry = root / ".git"
    if not git_entry.exists():
        return {}
    git_dirs = [git_entry] if git_entry.is_dir() else []
    if git_entry.is_file():
        try:
            pointer = git_entry.read_text(encoding="utf-8").strip()
        except OSError:
            pointer = ""
        if pointer.startswith("gitdir:"):
            target = Path(pointer[7:].strip())
            git_dirs.append((root / target).resolve() if not target.is_absolute() else target)

    snapshot: dict[str, str] = {".git": _file_digest(git_entry) or "missing"}
    for git_dir in git_dirs:
        for relative in ("HEAD", "index", "packed-refs", "config"):
            path = git_dir / relative
            digest = _file_digest(path)
            if digest is not None:
                snapshot[f".git/{relative}"] = digest
        for directory_name in ("refs", "logs", "hooks"):
            directory = git_dir / directory_name
            if directory.is_dir():
                for path in directory.rglob("*"):
                    if path.is_file():
                        digest = _file_digest(path)
                        if digest is not None:
                            relative = path.relative_to(directory).as_posix()
                            snapshot[f".git/{directory_name}/{relative}"] = digest
    return snapshot


def _snapshot_workspace(root: Path | None) -> dict[str, str]:
    if root is None or not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file() or _is_ignored_review_path(path, root):
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable"
        snapshot[path.relative_to(root).as_posix()] = digest
    return snapshot


def _is_ignored_review_path(path: Path, root: Path) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(relative == ignored or relative.startswith(ignored + "/") for ignored in REVIEW_MUTATION_IGNORES)
