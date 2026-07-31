from __future__ import annotations

import sys
import threading
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.step_pipeline import (  # noqa: E402
    AgentRequest,
    AgentResult,
    AgentRole,
    AgentStatus,
    CheckResult,
    CIResult,
    MainActions,
    PipelineStatus,
    ReviewContractError,
    ReviewFinding,
    StepPipeline,
    sanitize_log,
    validate_paths_under_root,
    validate_relative_paths,
    validate_review_result,
)


REVIEW_COMMANDS = {
    "unit-tests": ("pytest", "tests/unit"),
    "integration-tests": ("pytest", "tests/integration"),
    "ruff": ("ruff", "check", "."),
    "mypy": ("mypy", "."),
    "pytest": ("pytest", "-q"),
}
REVIEW_CHECKS = tuple(
    CheckResult(name=name, command=REVIEW_COMMANDS[name], passed=True, output="passed")
    for name in REVIEW_COMMANDS
)
SECURITY_CHECKS = tuple(
    CheckResult(name=name, command=(name,), passed=True, output="passed")
    for name in ("yaml", "paths", "inputs", "logs")
)


def implementation_result(*, changed_files: tuple[str, ...] = ("src/app.py", "tests/test_app.py")) -> AgentResult:
    return AgentResult(
        role=AgentRole.IMPLEMENTATION,
        status=AgentStatus.COMPLETED,
        summary="implemented",
        changed_files=changed_files,
    )


def review_result(role: AgentRole, *, findings: tuple[ReviewFinding, ...] = ()) -> AgentResult:
    return AgentResult(
        role=role,
        status=AgentStatus.PASSED if not findings else AgentStatus.FAILED,
        summary="reviewed",
        findings=findings,
        validation=REVIEW_CHECKS,
        external_behavior_verified=True,
    )


def security_result(*, findings: tuple[ReviewFinding, ...] = ()) -> AgentResult:
    return AgentResult(
        role=AgentRole.SECURITY_REVIEW,
        status=AgentStatus.PASSED if not findings else AgentStatus.FAILED,
        summary="security reviewed",
        findings=findings,
        security_checks=SECURITY_CHECKS,
        customer_data_exposure=False,
    )


class RecordingRunner:
    def __init__(self, results: dict[AgentRole, list[AgentResult]]) -> None:
        self.results = {role: list(items) for role, items in results.items()}
        self.requests: list[AgentRequest] = []
        self._lock = threading.Lock()

    def run(self, request: AgentRequest) -> AgentResult:
        with self._lock:
            self.requests.append(request)
            candidates = self.results[request.role]
            result = candidates.pop(0) if len(candidates) > 1 else candidates[0]
        return result


class RecordingActions(MainActions):
    def __init__(self, ci_results: list[CIResult] | None = None) -> None:
        self.commit_calls: list[tuple[str, int, tuple[str, ...]]] = []
        self.merge_calls: list[str] = []
        self.ci_results = list(ci_results or [CIResult.passed()])

    def commit(self, *, phase: str, step: int, changed_files: tuple[str, ...], message: str) -> str:
        self.commit_calls.append((phase, step, changed_files))
        return f"commit-{len(self.commit_calls)}"

    def check_ci(self, *, phase: str, commit_sha: str) -> CIResult:
        result = self.ci_results.pop(0) if len(self.ci_results) > 1 else self.ci_results[0]
        return result

    def merge(self, *, phase: str, commit_sha: str) -> None:
        self.merge_calls.append(commit_sha)


class StepPipelineTests(unittest.TestCase):
    def test_reviews_run_before_security_and_only_main_commits_and_merges(self) -> None:
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result()],
                AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW)],
                AgentRole.TEST: [review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result()],
            }
        )
        actions = RecordingActions()

        result = StepPipeline(runner=runner, actions=actions).run(
            phase="0-mvp", step=0, step_name="setup"
        )

        self.assertEqual(PipelineStatus.COMPLETED, result.status)
        self.assertEqual(1, len(actions.commit_calls))
        self.assertEqual(["commit-1"], actions.merge_calls)
        roles = [request.role for request in runner.requests]
        self.assertEqual(AgentRole.IMPLEMENTATION, roles[0])
        last_parallel_review = max(
            index
            for index, role in enumerate(roles)
            if role in {AgentRole.CODE_REVIEW, AgentRole.TEST}
        )
        self.assertLess(last_parallel_review, roles.index(AgentRole.SECURITY_REVIEW))
        for request in runner.requests:
            if request.role != AgentRole.IMPLEMENTATION:
                self.assertTrue(request.read_only)
                self.assertFalse(request.allow_commit)
        code_request = next(
            request for request in runner.requests if request.role == AgentRole.CODE_REVIEW
        )
        security_request = next(
            request for request in runner.requests if request.role == AgentRole.SECURITY_REVIEW
        )
        self.assertIn("Ruff, Mypy, and Pytest", code_request.prompt)
        self.assertIn("yaml, paths, inputs, and logs", security_request.prompt)

    def test_failed_review_retries_implementation_and_all_reviews(self) -> None:
        finding = ReviewFinding(
            severity="high",
            title="missing behavior",
            detail="The step requirement is not covered.",
            recommendation="Add an externally visible test.",
        )
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result(), implementation_result()],
                AgentRole.CODE_REVIEW: [
                    review_result(AgentRole.CODE_REVIEW, findings=(finding,)),
                    review_result(AgentRole.CODE_REVIEW),
                ],
                AgentRole.TEST: [review_result(AgentRole.TEST), review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result()],
            }
        )
        actions = RecordingActions()

        result = StepPipeline(runner=runner, actions=actions).run(
            phase="0-mvp", step=1, step_name="core"
        )

        self.assertEqual(PipelineStatus.COMPLETED, result.status)
        self.assertEqual(2, result.attempts)
        counts = defaultdict(int)
        for request in runner.requests:
            counts[request.role] += 1
        self.assertEqual(2, counts[AgentRole.IMPLEMENTATION])
        self.assertEqual(2, counts[AgentRole.CODE_REVIEW])
        self.assertEqual(2, counts[AgentRole.TEST])
        self.assertEqual(1, counts[AgentRole.SECURITY_REVIEW])

    def test_security_failure_restarts_the_full_review_chain(self) -> None:
        finding = ReviewFinding(
            severity="critical",
            title="unsafe log",
            detail="A log can expose customer data.",
            recommendation="Redact the value before logging.",
        )
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result(), implementation_result()],
                AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW), review_result(AgentRole.CODE_REVIEW)],
                AgentRole.TEST: [review_result(AgentRole.TEST), review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result(findings=(finding,)), security_result()],
            }
        )
        actions = RecordingActions()

        result = StepPipeline(runner=runner, actions=actions).run(
            phase="0-mvp", step=2, step_name="secure"
        )

        self.assertEqual(PipelineStatus.COMPLETED, result.status)
        self.assertEqual(2, result.attempts)
        self.assertEqual(1, len(actions.commit_calls))
        self.assertEqual(["commit-1"], actions.merge_calls)

    def test_ci_failure_is_repaired_before_merge(self) -> None:
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result(), implementation_result()],
                AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW), review_result(AgentRole.CODE_REVIEW)],
                AgentRole.TEST: [review_result(AgentRole.TEST), review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result(), security_result()],
            }
        )
        actions = RecordingActions(
            [
                CIResult.failed(("project-validation: pytest failed",)),
                CIResult.passed(),
            ]
        )

        result = StepPipeline(runner=runner, actions=actions).run(
            phase="0-mvp", step=3, step_name="ci"
        )

        self.assertEqual(PipelineStatus.COMPLETED, result.status)
        self.assertEqual(2, result.attempts)
        self.assertEqual(2, len(actions.commit_calls))
        self.assertEqual(["commit-2"], actions.merge_calls)
        implementation_requests = [
            request for request in runner.requests if request.role == AgentRole.IMPLEMENTATION
        ]
        self.assertIn("project-validation: pytest failed", implementation_requests[1].feedback)

    def test_pipeline_never_commits_when_review_contract_is_invalid(self) -> None:
        invalid_review = AgentResult(
            role=AgentRole.CODE_REVIEW,
            status=AgentStatus.PASSED,
            summary="reviewed without required checks",
            external_behavior_verified=False,
        )
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result()],
                AgentRole.CODE_REVIEW: [invalid_review],
                AgentRole.TEST: [review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result()],
            }
        )
        actions = RecordingActions()

        result = StepPipeline(runner=runner, actions=actions, max_attempts=1).run(
            phase="0-mvp", step=4, step_name="invalid"
        )

        self.assertEqual(PipelineStatus.ERROR, result.status)
        self.assertEqual([], actions.commit_calls)
        self.assertTrue(any("review" in error.lower() for error in result.errors))

    def test_implementation_must_report_a_test_change(self) -> None:
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result(changed_files=("src/app.py",))],
                AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW)],
                AgentRole.TEST: [review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result()],
            }
        )
        actions = RecordingActions()

        result = StepPipeline(runner=runner, actions=actions, max_attempts=1).run(
            phase="0-mvp", step=6, step_name="test-contract"
        )

        self.assertEqual(PipelineStatus.ERROR, result.status)
        self.assertEqual([], actions.commit_calls)
        self.assertTrue(any("test file" in error for error in result.errors))

    def test_review_contract_requires_external_behavior_and_all_validation_commands(self) -> None:
        with self.assertRaises(ReviewContractError):
            validate_review_result(
                AgentResult(
                    role=AgentRole.CODE_REVIEW,
                    status=AgentStatus.PASSED,
                    summary="incomplete",
                    validation=(CheckResult(name="pytest", command=("pytest",), passed=True),),
                    external_behavior_verified=False,
                )
            )

        incomplete_commands = list(REVIEW_CHECKS)
        incomplete_commands[-1] = CheckResult(name="ruff", command=("echo",), passed=True)
        with self.assertRaises(ReviewContractError):
            validate_review_result(
                AgentResult(
                    role=AgentRole.CODE_REVIEW,
                    status=AgentStatus.PASSED,
                    summary="wrong command",
                    validation=tuple(incomplete_commands),
                    external_behavior_verified=True,
                )
            )

    def test_worker_payload_is_validated_at_the_boundary(self) -> None:
        with self.assertRaises(ValueError):
            AgentResult.from_payload(
                {
                    "role": "implementation",
                    "status": "completed",
                    "summary": "bad path",
                    "changed_files": ["../outside.py"],
                }
            )

        result = AgentResult.from_payload(
            {
                "role": "implementation",
                "status": "completed",
                "summary": "safe",
                "changed_files": ["src/app.py"],
                "log": "token=secret customer@example.com",
            }
        )
        self.assertNotIn("secret", result.log)
        self.assertNotIn("customer@example.com", result.log)

    def test_security_boundaries_reject_traversal_and_redact_logs(self) -> None:
        with self.assertRaises(ValueError):
            validate_relative_paths(("../outside.txt",))
        with self.assertRaises(ValueError):
            validate_relative_paths(("/absolute/path.txt",))

        redacted = sanitize_log("token=super-secret password: customer@example.com", max_length=32)
        self.assertNotIn("super-secret", redacted)
        self.assertNotIn("customer@example.com", redacted)
        self.assertLessEqual(len(redacted), 32)

        with TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            outside = Path(temp) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "link").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                validate_paths_under_root(root, ("link/secret.txt",))

    def test_workspace_snapshot_blocks_a_review_agent_that_writes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "src/app.py"
            target.parent.mkdir(parents=True)
            target.write_text("original", encoding="utf-8")

            class MutatingRunner(RecordingRunner):
                def run(self, request: AgentRequest) -> AgentResult:
                    if request.role == AgentRole.CODE_REVIEW:
                        target.write_text("review changed code", encoding="utf-8")
                    return super().run(request)

            runner = MutatingRunner(
                {
                    AgentRole.IMPLEMENTATION: [implementation_result()],
                    AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW)],
                    AgentRole.TEST: [review_result(AgentRole.TEST)],
                    AgentRole.SECURITY_REVIEW: [security_result()],
                }
            )
            actions = RecordingActions()

            result = StepPipeline(runner=runner, actions=actions, root=root, max_attempts=1).run(
                phase="0-mvp", step=5, step_name="readonly"
            )

            self.assertEqual(PipelineStatus.ERROR, result.status)
            self.assertEqual([], actions.commit_calls)
            self.assertTrue(any("modified" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
