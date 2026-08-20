#!/usr/bin/env python3
"""Run one Harness step through implementation, reviews, CI, and merge."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import fnmatch
import hashlib
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, cast

from scripts.harness_validation import (
    DEFAULT_REVIEW_MUTATION_IGNORES,
    HarnessCommand,
    ValidationConfig,
    load_validation_config,
    step_validation_policy,
)
from scripts.phase_worktree import (
    MAX_STUCK_RETRIES,
    STATUS_UPDATE_INTERVAL_SECONDS,
    STUCK_AFTER_SECONDS,
    is_stuck,
    next_stuck_state,
    write_heartbeat,
)
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
    load_completion_criteria,
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


REVIEW_MUTATION_IGNORES = DEFAULT_REVIEW_MUTATION_IGNORES

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
    "load_completion_criteria",
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


@dataclass(frozen=True)
class _ImplementationOutcome:
    result: AgentResult | None
    stuck: bool = False
    started_at: datetime | None = None


class StepPipeline:
    """Retry implementation until reviews and post-PR CI permit a merge."""

    def __init__(
        self,
        *,
        runner: AgentRunner,
        actions: MainActions,
        root: Path | None = None,
        max_attempts: int = 3,
        max_stuck_retries: int = MAX_STUCK_RETRIES,
        max_completion_conditions: int | None = None,
        status_update_interval_seconds: int = STATUS_UPDATE_INTERVAL_SECONDS,
        stuck_after_seconds: int = STUCK_AFTER_SECONDS,
        clock: Callable[[], datetime] | None = None,
        status_update: Callable[[str], None] | None = None,
    ) -> None:
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if not isinstance(max_stuck_retries, int) or isinstance(max_stuck_retries, bool) or max_stuck_retries < 1:
            raise ValueError("max_stuck_retries must be positive")
        if (
            not isinstance(status_update_interval_seconds, int)
            or isinstance(status_update_interval_seconds, bool)
            or status_update_interval_seconds < 1
        ):
            raise ValueError("status_update_interval_seconds must be positive")
        if (
            not isinstance(stuck_after_seconds, int)
            or isinstance(stuck_after_seconds, bool)
            or stuck_after_seconds < 1
        ):
            raise ValueError("stuck_after_seconds must be positive")
        if max_completion_conditions is not None and (
            not isinstance(max_completion_conditions, int)
            or isinstance(max_completion_conditions, bool)
            or max_completion_conditions < 1
        ):
            raise ValueError("max_completion_conditions must be positive")
        if clock is not None and not callable(clock):
            raise ValueError("clock must be callable")
        if status_update is not None and not callable(status_update):
            raise ValueError("status_update must be callable")
        self._runner = runner
        self._actions = actions
        self._root = (root or Path.cwd()).resolve()
        self._max_attempts = max_attempts
        self._max_stuck_retries = max_stuck_retries
        self._status_update_interval_seconds = status_update_interval_seconds
        self._stuck_after_seconds = stuck_after_seconds
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._status_update = status_update
        self._validation_config = self._load_validation_config()
        self._max_completion_conditions = (
            max_completion_conditions
            if max_completion_conditions is not None
            else self._validation_config.max_completion_conditions
        )
        self._review_mutation_ignores = self._validation_config.review_mutation_ignore or REVIEW_MUTATION_IGNORES

    def _load_validation_config(self) -> ValidationConfig:
        path = self._root / ".harness/validation.json"
        if not path.exists():
            return ValidationConfig(
                schema_version=1,
                mode="language-neutral",
                profiles=(),
                commands=(),
                checks={"docs": True, "deploy": True, "phase": True},
            )
        try:
            return load_validation_config(path)
        except Exception as exc:
            raise ValueError(f"invalid Harness validation profile: {exc}") from exc

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
        step_kind: str = "feature",
    ) -> PipelineResult:
        validate_phase_and_step(phase, step, step_name)
        if not isinstance(step_spec, str):
            raise ValueError("step_spec must be a string")
        conditions = validate_completion_conditions(
            completion_conditions,
            confirmed=conditions_confirmed,
            max_conditions=self._max_completion_conditions,
        )
        if not conditions_confirmed:
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
        criteria_file = save_completion_criteria(
            criteria_root,
            criteria_path,
            conditions,
            max_conditions=self._max_completion_conditions,
        )
        if load_completion_criteria(
            criteria_root,
            criteria_path,
            max_conditions=self._max_completion_conditions,
        ) != tuple(conditions):
            raise ValueError("saved completion criteria artifact could not be reloaded")
        criteria_relative_path = criteria_file.relative_to(criteria_root).as_posix()
        criteria_digest = hashlib.sha256(
            render_completion_criteria(
                conditions,
                max_conditions=self._max_completion_conditions,
            ).encode("utf-8")
        ).hexdigest()

        errors: list[str] = []
        events: list[str] = []
        all_changed_files: list[str] = []
        feedback = ""
        last_commit_sha: str | None = None
        stuck_retries = 0
        events.append(f"completion criteria confirmed: {len(conditions)}")

        for attempt in range(1, self._max_attempts + 1):
            stuck_retries = 0
            implementation: AgentResult | None = None
            before_implementation: dict[str, str] = {}
            while True:
                before_implementation = _snapshot_workspace(
                    self._root, ignores=self._review_mutation_ignores
                )
                before_git = _snapshot_git_metadata(self._root)
                events.append(
                    f"attempt {attempt}: implementation (stuck retry {stuck_retries})"
                )
                outcome = self._run_implementation(
                    phase=phase,
                    step=step,
                    step_name=step_name,
                    step_spec=step_spec,
                    feedback=feedback,
                    completion_conditions=conditions,
                    criteria_path=criteria_relative_path,
                    pipeline_attempt=attempt,
                    stuck_retry=stuck_retries,
                    step_kind=step_kind,
                    errors=errors,
                )
                if _snapshot_git_metadata(self._root) != before_git:
                    message = "implementation modified git metadata"
                    errors.append(message)
                    restore_error = _restore_completion_criteria(
                        criteria_file, conditions, max_conditions=self._max_completion_conditions
                    )
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
                        stuck_retries=stuck_retries,
                    )
                if _file_digest(criteria_file) != criteria_digest:
                    message = "implementation modified completion criteria file"
                    errors.append(message)
                    feedback = message
                    restore_error = _restore_completion_criteria(
                        criteria_file, conditions, max_conditions=self._max_completion_conditions
                    )
                    if restore_error:
                        errors.append(restore_error)
                    implementation = None
                    break
                if outcome.stuck:
                    state, stuck_retries = next_stuck_state(
                        stuck_retries,
                        max_stuck_retries=self._max_stuck_retries,
                    )
                    events.append(
                        f"attempt {attempt}: implementation {state} "
                        f"({stuck_retries}/{self._max_stuck_retries})"
                    )
                    if state == "error":
                        message = "implementation exceeded maximum stuck retries"
                        errors.append(message)
                        write_heartbeat(
                            root=self._root,
                            phase=phase,
                            step=step,
                            attempt=attempt,
                            pipeline_attempt=attempt,
                            status="error",
                            message=message,
                            progress="error",
                            started_at=outcome.started_at or self._clock(),
                            now=self._clock(),
                            stuck_retry=stuck_retries,
                            status_update_interval_seconds=self._status_update_interval_seconds,
                            stuck_after_seconds=self._stuck_after_seconds,
                            max_stuck_retries=self._max_stuck_retries,
                        )
                        return self._result(
                            status=PipelineStatus.ERROR,
                            attempts=attempt,
                            changed_files=all_changed_files,
                            commit_sha=last_commit_sha,
                            errors=errors,
                            events=events,
                            completion_conditions=conditions,
                            stuck_retries=stuck_retries,
                        )
                    feedback = "implementation attempt stuck; start a new implementation worker"
                    continue
                implementation = outcome.result
                break
            if implementation is None:
                feedback = errors[-1] if errors else feedback
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
                    stuck_retries=stuck_retries,
                )
            if implementation.status != AgentStatus.COMPLETED or implementation.committed:
                message = "implementation did not complete without committing"
                errors.append(message)
                feedback = f"{message}: {sanitize_log(implementation.summary)}"
                continue
            try:
                validate_implementation_result(
                    implementation,
                    test_requirement=step_validation_policy(self._validation_config, step_kind),
                )
            except ValueError as exc:
                message = "implementation contract failed: " + sanitize_log(str(exc))
                errors.append(message)
                feedback = message
                continue

            try:
                after_implementation = _snapshot_workspace(
                    self._root, ignores=self._review_mutation_ignores
                )
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
                review_checks=self._validation_config.review_checks,
                events=events,
                errors=errors,
            )
            if reviews is None:
                feedback = errors[-1]
                if "review agent modified" in feedback or "review agent violated" in feedback:
                    restore_error = _restore_completion_criteria(
                        criteria_file, conditions, max_conditions=self._max_completion_conditions
                    )
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
            review_feedback = self._review_feedback(
                reviews,
                conditions,
                errors,
                self._validation_config.review_checks,
            )
            if review_feedback:
                feedback = review_feedback
                continue

            security_snapshot = (
                _snapshot_workspace(self._root, ignores=self._review_mutation_ignores)
                if self._root
                else None
            )
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
            if security_snapshot is not None and _snapshot_workspace(
                self._root, ignores=self._review_mutation_ignores
            ) != security_snapshot:
                message = "security review agent modified the workspace"
                errors.append(message)
                restore_error = _restore_completion_criteria(
                    criteria_file, conditions, max_conditions=self._max_completion_conditions
                )
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
                restore_error = _restore_completion_criteria(
                    criteria_file, conditions, max_conditions=self._max_completion_conditions
                )
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
        pipeline_attempt: int,
        stuck_retry: int,
        step_kind: str,
        errors: list[str],
    ) -> _ImplementationOutcome:
        started_at = self._clock()
        heartbeat_kwargs = {
            "root": self._root,
            "phase": phase,
            "step": step,
            "attempt": pipeline_attempt,
            "pipeline_attempt": pipeline_attempt,
            "started_at": started_at,
            "stuck_retry": stuck_retry,
            "status_update_interval_seconds": self._status_update_interval_seconds,
            "stuck_after_seconds": self._stuck_after_seconds,
            "max_stuck_retries": self._max_stuck_retries,
        }
        heartbeat_path = write_heartbeat(
            status="running",
            message="implementation started",
            progress="implementation started",
            now=started_at,
            **heartbeat_kwargs,
        )
        self._emit_status_update(
            phase=phase,
            step=step,
            attempt=pipeline_attempt,
            progress="implementation started",
            started_at=started_at,
        )
        test_requirement = step_validation_policy(self._validation_config, step_kind)
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
                step_kind=step_kind,
                test_requirement=test_requirement,
            ),
            feedback=feedback,
            allow_write=True,
            started_at=started_at.isoformat(),
            deadline_at=(started_at + timedelta(seconds=self._stuck_after_seconds)).isoformat(),
            heartbeat_path=heartbeat_path.relative_to(self._root).as_posix(),
            status_update_interval_seconds=self._status_update_interval_seconds,
            stuck_after_seconds=self._stuck_after_seconds,
        )
        result_box: list[AgentResult | None] = []
        finished = threading.Event()

        def run_worker() -> None:
            result_box.append(self._run_agent(request, errors))
            finished.set()

        worker = threading.Thread(target=run_worker, name="harness-implementation", daemon=True)
        worker.start()
        deadline = time.monotonic() + self._stuck_after_seconds
        while not finished.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                current = self._clock()
                write_heartbeat(
                    status="stuck",
                    message="implementation attempt exceeded time limit",
                    progress="stuck",
                    now=current,
                    **heartbeat_kwargs,
                )
                self._emit_status_update(
                    phase=phase,
                    step=step,
                    attempt=pipeline_attempt,
                    progress="stuck",
                    started_at=started_at,
                )
                return _ImplementationOutcome(result=None, stuck=True, started_at=started_at)
            if finished.wait(timeout=min(self._status_update_interval_seconds, remaining)):
                break
            current = self._clock()
            elapsed = max(0, int((current - started_at).total_seconds()))
            progress = f"implementation running; elapsed {elapsed}s"
            write_heartbeat(
                status="running",
                message=progress,
                progress=progress,
                now=current,
                **heartbeat_kwargs,
            )
            self._emit_status_update(
                phase=phase,
                step=step,
                attempt=pipeline_attempt,
                progress=progress,
                started_at=started_at,
            )

        current = self._clock()
        result = result_box[0] if result_box else None
        if result is None and is_stuck(
            started_at=started_at,
            now=current,
            status="running",
            stuck_after_seconds=self._stuck_after_seconds,
        ):
            write_heartbeat(
                status="stuck",
                message="implementation attempt exceeded time limit",
                progress="stuck",
                now=current,
                **heartbeat_kwargs,
            )
            return _ImplementationOutcome(result=None, stuck=True, started_at=started_at)
        terminal_status = "error"
        if result is not None:
            terminal_status = {
                AgentStatus.COMPLETED: "completed",
                AgentStatus.BLOCKED: "blocked",
                AgentStatus.ERROR: "error",
                AgentStatus.FAILED: "error",
                AgentStatus.PASSED: "completed",
            }.get(result.status, "error")
        terminal_progress = result.summary if result is not None else "implementation failed"
        write_heartbeat(
            status=terminal_status,
            message=terminal_progress,
            progress=terminal_progress,
            now=current,
            **heartbeat_kwargs,
        )
        self._emit_status_update(
            phase=phase,
            step=step,
            attempt=pipeline_attempt,
            progress=terminal_progress,
            started_at=started_at,
        )
        return _ImplementationOutcome(result=result, started_at=started_at)

    def _emit_status_update(
        self,
        *,
        phase: str,
        step: int,
        attempt: int,
        progress: str,
        started_at: datetime,
    ) -> None:
        if self._status_update is None:
            return
        elapsed = max(0, int((self._clock() - started_at).total_seconds()))
        message = (
            f"Phase {phase} / Step {step} implementation in progress. "
            f"{progress}. Current attempt {attempt}, elapsed {elapsed}s."
        )
        try:
            self._status_update(message)
        except Exception:  # pragma: no cover - platform callback failure
            # User-facing progress must never turn a successful implementation into a failure.
            return

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
        review_checks: dict[str, tuple[HarnessCommand, ...]],
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
                review_checks=review_checks.get("code-review", ()),
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
                review_checks=review_checks.get("test-review", ()),
            ),
        )
        before = (
            _snapshot_workspace(self._root, ignores=self._review_mutation_ignores)
            if self._root
            else None
        )
        before_git = _snapshot_git_metadata(self._root)
        events.append("code review + test review: parallel")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="harness-review") as pool:
            futures = [
                pool.submit(self._run_agent, request, errors)
                for request in (requests.code, requests.tests)
            ]
            results = [future.result() for future in futures]
        if before is not None and _snapshot_workspace(
            self._root, ignores=self._review_mutation_ignores
        ) != before:
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
        review_checks: Sequence[HarnessCommand],
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
                review_checks=review_checks,
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
        review_checks: dict[str, tuple[HarnessCommand, ...]],
    ) -> str:
        feedback: list[str] = []
        for result in results:
            try:
                validate_review_result(
                    result,
                    completion_conditions=completion_conditions,
                    review_checks=review_checks.get(
                        "code-review" if result.role == AgentRole.CODE_REVIEW else "test-review",
                        (),
                    ),
                )
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
        stuck_retries: int = 0,
    ) -> PipelineResult:
        return PipelineResult(
            status=status,
            attempts=attempts,
            changed_files=validate_relative_paths(changed_files),
            commit_sha=commit_sha,
            errors=tuple(sanitize_log(error) for error in errors),
            events=tuple(events),
            completion_conditions=tuple(completion_conditions),
            stuck_retries=stuck_retries,
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


def _restore_completion_criteria(
    path: Path,
    conditions: Sequence[str],
    *,
    max_conditions: int = 100,
) -> str | None:
    try:
        path.write_text(
            render_completion_criteria(conditions, max_conditions=max_conditions),
            encoding="utf-8",
        )
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


def _snapshot_workspace(
    root: Path | None,
    *,
    ignores: Sequence[str] = REVIEW_MUTATION_IGNORES,
) -> dict[str, str]:
    if root is None or not root.exists():
        return {}
    git_snapshot = _snapshot_git_worktree(root, ignores=ignores)
    if git_snapshot is not None:
        return git_snapshot
    snapshot: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file() or _is_ignored_review_path(path, root, ignores):
            continue
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            digest = "unreadable"
        snapshot[path.relative_to(root).as_posix()] = digest
    return snapshot


def _snapshot_git_worktree(root: Path, *, ignores: Sequence[str]) -> dict[str, str] | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all", "-z"],
            capture_output=True,
            text=False,
            timeout=30,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    snapshot: dict[str, str] = {}
    records = completed.stdout.split(b"\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        text = record.decode("utf-8", errors="replace")
        relative = text[3:] if len(text) >= 4 else ""
        paths = [relative]
        if " -> " in relative:
            paths = relative.split(" -> ")
            if index < len(records) and records[index]:
                index += 1
        for item in paths:
            normalized = item.replace("\\", "/")
            if not normalized or _is_ignored_review_relative(normalized, ignores):
                continue
            digest = _file_digest(root / normalized) or "missing"
            snapshot[normalized] = f"{text[:2]}:{digest}"
    return snapshot


def _is_ignored_review_path(path: Path, root: Path, ignores: Sequence[str]) -> bool:
    relative = path.relative_to(root).as_posix()
    return _is_ignored_review_relative(relative, ignores)


def _is_ignored_review_relative(relative: str, ignores: Sequence[str]) -> bool:
    return any(
        relative == ignored
        or relative.startswith(ignored.rstrip("/") + "/")
        or fnmatch.fnmatch(relative, ignored)
        for ignored in ignores
    )
