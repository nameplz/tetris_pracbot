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
    CompletionCriterionReview,
    CIResult,
    MainActions,
    PipelineResult,
    PipelineStatus,
    ReviewContractError,
    ReviewFinding,
    StepPipeline,
    sanitize_log,
    validate_paths_under_root,
    validate_relative_paths,
    validate_completion_conditions,
    validate_review_result,
)


REVIEW_COMMANDS = {
    "unit-tests": ("pytest", "tests/unit"),
    "integration-tests": ("pytest", "tests/integration"),
    "ruff": ("ruff", "check", "."),
    "mypy": ("mypy", "."),
    "pytest": ("pytest", "-q"),
    "coverage": ("pytest", "--cov=scripts", "--cov-fail-under=80"),
}
REVIEW_CHECKS = tuple(
    CheckResult(name=name, command=REVIEW_COMMANDS[name], passed=True, output="passed")
    for name in REVIEW_COMMANDS
)
SECURITY_CHECKS = tuple(
    CheckResult(name=name, command=(name,), passed=True, output="passed")
    for name in ("yaml", "paths", "inputs", "logs")
)
COMPLETION_CONDITIONS = ("criterion one",)


def run_pipeline(
    runner: "RecordingRunner",
    actions: "RecordingActions",
    *,
    phase: str,
    step: int,
    step_name: str,
    max_attempts: int = 3,
    conditions: tuple[str, ...] = COMPLETION_CONDITIONS,
) -> PipelineResult:
    with TemporaryDirectory() as temp:
        return StepPipeline(
            runner=runner, actions=actions, root=Path(temp), max_attempts=max_attempts
        ).run(
            phase=phase,
            step=step,
            step_name=step_name,
            completion_conditions=conditions,
            conditions_confirmed=True,
        )


def implementation_result(*, changed_files: tuple[str, ...] = ("src/app.py", "tests/test_app.py")) -> AgentResult:
    return AgentResult(
        role=AgentRole.IMPLEMENTATION,
        status=AgentStatus.COMPLETED,
        summary="implemented",
        changed_files=changed_files,
    )


def review_result(
    role: AgentRole,
    *,
    findings: tuple[ReviewFinding, ...] = (),
    criteria_reviews: tuple[CompletionCriterionReview, ...] | None = None,
) -> AgentResult:
    if criteria_reviews is None and role == AgentRole.CODE_REVIEW:
        criteria_reviews = tuple(
            CompletionCriterionReview(number=index, status="pass", evidence=f"src/app.py:{index}")
            for index in range(1, len(COMPLETION_CONDITIONS) + 1)
        )
    return AgentResult(
        role=role,
        status=AgentStatus.PASSED if not findings else AgentStatus.FAILED,
        summary="reviewed",
        findings=findings,
        criteria_reviews=criteria_reviews or (),
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

        result = run_pipeline(runner, actions, phase="0-mvp", step=0, step_name="setup")

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
        self.assertIn("Ruff, Mypy, Pytest", code_request.prompt)
        self.assertIn("--cov-fail-under=80", code_request.prompt)
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

        result = run_pipeline(runner, actions, phase="0-mvp", step=1, step_name="core")

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

        result = run_pipeline(runner, actions, phase="0-mvp", step=2, step_name="secure")

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

        result = run_pipeline(runner, actions, phase="0-mvp", step=3, step_name="ci")

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

        result = run_pipeline(
            runner, actions, phase="0-mvp", step=4, step_name="invalid", max_attempts=1
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

        result = run_pipeline(
            runner, actions, phase="0-mvp", step=6, step_name="test-contract", max_attempts=1
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

        duplicate_checks = REVIEW_CHECKS + (REVIEW_CHECKS[0],)
        with self.assertRaises(ReviewContractError):
            validate_review_result(
                AgentResult(
                    role=AgentRole.CODE_REVIEW,
                    status=AgentStatus.PASSED,
                    summary="duplicate checks",
                    validation=duplicate_checks,
                    external_behavior_verified=True,
                )
            )

        unknown_checks = REVIEW_CHECKS + (
            CheckResult(name="unexpected", command=("echo",), passed=True),
        )
        with self.assertRaises(ReviewContractError):
            validate_review_result(
                AgentResult(
                    role=AgentRole.CODE_REVIEW,
                    status=AgentStatus.PASSED,
                    summary="unknown checks",
                    validation=unknown_checks,
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

        structured = AgentResult.from_payload(
            {
                "role": "implementation",
                "status": "completed",
                "summary": "structured log",
                "log": '{"password":"secret","token":"abc"}',
            }
        )
        self.assertNotIn("secret", structured.log)
        self.assertNotIn("abc", structured.log)

        authorization = AgentResult.from_payload(
            {
                "role": "implementation",
                "status": "completed",
                "summary": "authorization log",
                "log": "Authorization: Bearer abc.def",
            }
        )
        self.assertNotIn("abc.def", authorization.log)

        review = AgentResult.from_payload(
            {
                "role": "code-review",
                "status": "passed",
                "summary": "criteria checked",
                "criteria_reviews": [
                    {
                        "number": 1,
                        "status": "pass",
                        "evidence": "src/app.py:10",
                    }
                ],
            }
        )
        self.assertEqual(1, review.criteria_reviews[0].number)

    def test_security_boundaries_reject_traversal_and_redact_logs(self) -> None:
        with self.assertRaises(ValueError):
            validate_completion_conditions(("bad\x00criterion",), confirmed=True)
        with self.assertRaises(ValueError):
            validate_completion_conditions(tuple(f"criterion {i}" for i in range(101)), confirmed=True)
        with self.assertRaises(ValueError):
            validate_relative_paths(("../outside.txt",))
        with self.assertRaises(ValueError):
            validate_relative_paths(("/absolute/path.txt",))
        with self.assertRaises(ValueError):
            validate_relative_paths(("docs/\nspoof.md",))

        redacted = sanitize_log("token=super-secret password: customer@example.com", max_length=32)
        self.assertNotIn("super-secret", redacted)
        self.assertNotIn("customer@example.com", redacted)
        self.assertLessEqual(len(redacted), 32)

        with self.assertRaises(ValueError):
            CompletionCriterionReview(1, "pass", "trust me")

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
                phase="0-mvp",
                step=5,
                step_name="readonly",
                completion_conditions=COMPLETION_CONDITIONS,
                conditions_confirmed=True,
            )

            self.assertEqual(PipelineStatus.ERROR, result.status)
            self.assertEqual([], actions.commit_calls)
            self.assertTrue(any("modified" in error for error in result.errors))

    def test_pipeline_reviews_and_commits_unreported_workspace_changes(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)

            class UnreportedChangeRunner(RecordingRunner):
                def run(self, request: AgentRequest) -> AgentResult:
                    if request.role == AgentRole.IMPLEMENTATION:
                        target = root / "src/unreported.py"
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text("unreported = True", encoding="utf-8")
                    return super().run(request)

            runner = UnreportedChangeRunner(
                {
                    AgentRole.IMPLEMENTATION: [implementation_result()],
                    AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW)],
                    AgentRole.TEST: [review_result(AgentRole.TEST)],
                    AgentRole.SECURITY_REVIEW: [security_result()],
                }
            )
            actions = RecordingActions()
            result = StepPipeline(runner=runner, actions=actions, root=root).run(
                phase="0-mvp",
                step=13,
                step_name="workspace-diff",
                completion_conditions=COMPLETION_CONDITIONS,
                conditions_confirmed=True,
            )

            self.assertEqual(PipelineStatus.COMPLETED, result.status)
            code_request = next(
                request for request in runner.requests if request.role == AgentRole.CODE_REVIEW
            )
            self.assertIn("src/unreported.py", code_request.changed_files)
            self.assertIn("src/unreported.py", actions.commit_calls[0][2])

    def test_pipeline_restores_criteria_if_implementation_mutates_it(self) -> None:
        with TemporaryDirectory() as temp:
            root = Path(temp)

            class CriteriaMutatingRunner(RecordingRunner):
                def run(self, request: AgentRequest) -> AgentResult:
                    if request.role == AgentRole.IMPLEMENTATION:
                        (root / "docs/completion-criteria.md").write_text(
                            "tampered", encoding="utf-8"
                        )
                    return super().run(request)

            runner = CriteriaMutatingRunner(
                {
                    AgentRole.IMPLEMENTATION: [implementation_result()],
                    AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW)],
                    AgentRole.TEST: [review_result(AgentRole.TEST)],
                    AgentRole.SECURITY_REVIEW: [security_result()],
                }
            )
            actions = RecordingActions()
            result = StepPipeline(
                runner=runner, actions=actions, root=root, max_attempts=1
            ).run(
                phase="0-mvp",
                step=14,
                step_name="criteria-integrity",
                completion_conditions=COMPLETION_CONDITIONS,
                conditions_confirmed=True,
            )

            criteria = (root / "docs/completion-criteria.md").read_text(encoding="utf-8")
            self.assertEqual(PipelineStatus.ERROR, result.status)
            self.assertEqual([], actions.commit_calls)
            self.assertIn("criterion one", criteria)
            self.assertTrue(any("criteria file" in error for error in result.errors))

    def test_unconfirmed_conditions_block_before_worker_and_do_not_write_file(self) -> None:
        runner = RecordingRunner({})
        actions = RecordingActions()
        conditions = tuple(f"criterion {index}" for index in range(1, 11))

        with TemporaryDirectory() as temp:
            root = Path(temp)
            result = StepPipeline(runner=runner, actions=actions, root=root).run(
                phase="0-mvp",
                step=7,
                step_name="criteria",
                completion_conditions=conditions,
                conditions_confirmed=False,
            )

            self.assertEqual(PipelineStatus.BLOCKED, result.status)
            self.assertEqual(conditions, result.completion_conditions)
            self.assertEqual([], runner.requests)
            self.assertFalse((root / "docs/completion-criteria.md").exists())

    def test_unconfirmed_conditions_require_exactly_ten(self) -> None:
        runner = RecordingRunner({})
        actions = RecordingActions()
        for count in (9, 11):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    StepPipeline(runner=runner, actions=actions).run(
                        phase="0-mvp",
                        step=8,
                        step_name="criteria",
                        completion_conditions=tuple(f"criterion {i}" for i in range(count)),
                        conditions_confirmed=False,
                    )

    def test_latest_draft_can_change_before_confirmation_but_confirmation_must_match(self) -> None:
        runner = RecordingRunner({})
        actions = RecordingActions()
        initial = tuple(f"criterion {index}" for index in range(1, 11))
        revised = ("revised one", "revised two")
        with TemporaryDirectory() as temp:
            pipeline = StepPipeline(runner=runner, actions=actions, root=Path(temp))
            first = pipeline.run(
                phase="0-mvp",
                step=15,
                step_name="criteria-draft",
                completion_conditions=initial,
                conditions_confirmed=False,
            )
            second = pipeline.run(
                phase="0-mvp",
                step=15,
                step_name="criteria-draft",
                completion_conditions=revised,
                conditions_confirmed=False,
            )
            self.assertEqual(PipelineStatus.BLOCKED, first.status)
            self.assertEqual(PipelineStatus.BLOCKED, second.status)
            self.assertEqual(revised, second.completion_conditions)
            with self.assertRaises(ValueError):
                pipeline.run(
                    phase="0-mvp",
                    step=15,
                    step_name="criteria-draft",
                    completion_conditions=("different",),
                    conditions_confirmed=True,
                )
            self.assertFalse((Path(temp) / "docs/completion-criteria.md").exists())

    def test_confirmation_saves_dynamic_count_and_provides_same_conditions_to_workers(self) -> None:
        conditions = ("first criterion", "second criterion", "third criterion")
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result()],
                AgentRole.CODE_REVIEW: [
                    review_result(
                        AgentRole.CODE_REVIEW,
                        criteria_reviews=tuple(
                            CompletionCriterionReview(i, "pass", f"src/app.py:{i}")
                            for i in range(1, 4)
                        ),
                    )
                ],
                AgentRole.TEST: [review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result()],
            }
        )
        actions = RecordingActions()

        with TemporaryDirectory() as temp:
            root = Path(temp)
            result = StepPipeline(runner=runner, actions=actions, root=root).run(
                phase="0-mvp",
                step=9,
                step_name="criteria",
                completion_conditions=conditions,
                conditions_confirmed=True,
            )

            criteria_file = root / "docs/completion-criteria.md"
            content = criteria_file.read_text(encoding="utf-8")
            self.assertEqual(PipelineStatus.COMPLETED, result.status)
            self.assertIn("현재 확정 조건 수: 3", content)
            for condition in conditions:
                self.assertIn(condition, content)
            implementation_request = next(
                request for request in runner.requests if request.role == AgentRole.IMPLEMENTATION
            )
            code_request = next(
                request for request in runner.requests if request.role == AgentRole.CODE_REVIEW
            )
            for condition in conditions:
                self.assertIn(condition, implementation_request.prompt)
                self.assertIn(condition, code_request.prompt)
            self.assertIn("docs/completion-criteria.md", code_request.prompt)
            self.assertIn("docs/completion-criteria.md", actions.commit_calls[0][2])

    def test_confirmed_criteria_path_cannot_escape_workspace(self) -> None:
        runner = RecordingRunner({})
        actions = RecordingActions()
        with TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                StepPipeline(runner=runner, actions=actions, root=Path(temp)).run(
                    phase="0-mvp",
                    step=12,
                    step_name="criteria-path",
                    completion_conditions=("criterion",),
                    conditions_confirmed=True,
                    criteria_path="../criteria.md",
                )

    def test_code_review_requires_one_result_per_condition(self) -> None:
        conditions = ("first criterion", "second criterion")
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result()],
                AgentRole.CODE_REVIEW: [review_result(AgentRole.CODE_REVIEW, criteria_reviews=())],
                AgentRole.TEST: [review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result()],
            }
        )
        actions = RecordingActions()

        with TemporaryDirectory() as temp:
            result = StepPipeline(
                runner=runner, actions=actions, root=Path(temp), max_attempts=1
            ).run(
                phase="0-mvp",
                step=10,
                step_name="criteria-contract",
                completion_conditions=conditions,
                conditions_confirmed=True,
            )

        self.assertEqual(PipelineStatus.ERROR, result.status)
        self.assertEqual([], actions.commit_calls)
        self.assertTrue(any("criteria" in error for error in result.errors))

    def test_failed_condition_is_feedback_and_blocks_commit_until_fixed(self) -> None:
        conditions = ("first criterion", "second criterion")
        failed = CompletionCriterionReview(
            number=2,
            status="fail",
            evidence="src/app.py:20",
            recommendation="Add externally visible behavior test.",
        )
        passing = tuple(
            CompletionCriterionReview(i, "pass", f"src/app.py:{i}") for i in range(1, 3)
        )
        runner = RecordingRunner(
            {
                AgentRole.IMPLEMENTATION: [implementation_result(), implementation_result()],
                AgentRole.CODE_REVIEW: [
                    review_result(
                        AgentRole.CODE_REVIEW,
                        criteria_reviews=(
                            CompletionCriterionReview(1, "pass", "src/app.py:10"),
                            failed,
                        ),
                    ),
                    review_result(AgentRole.CODE_REVIEW, criteria_reviews=passing),
                ],
                AgentRole.TEST: [review_result(AgentRole.TEST), review_result(AgentRole.TEST)],
                AgentRole.SECURITY_REVIEW: [security_result()],
            }
        )
        actions = RecordingActions()

        result = run_pipeline(
            runner,
            actions,
            phase="0-mvp",
            step=11,
            step_name="criteria-feedback",
            conditions=conditions,
        )

        self.assertEqual(PipelineStatus.COMPLETED, result.status)
        implementation_requests = [
            request for request in runner.requests if request.role == AgentRole.IMPLEMENTATION
        ]
        self.assertIn("criterion 2", implementation_requests[1].feedback)
        self.assertIn("src/app.py:20", implementation_requests[1].feedback)
        self.assertIn("Add externally visible behavior test", implementation_requests[1].feedback)
        self.assertEqual(1, len(actions.commit_calls))


if __name__ == "__main__":
    unittest.main()
