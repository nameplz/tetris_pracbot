#!/usr/bin/env python3
"""Prompt builders for the Harness step roles."""

from __future__ import annotations

from collections.abc import Sequence

from scripts.step_contracts import (
    DEFAULT_COMPLETION_CRITERIA_PATH,
    AgentRole,
    CIResult,
    CompletionCriterionReview,
    ReviewFinding,
    sanitize_log,
)


def implementation_prompt(
    *,
    phase: str,
    step: int,
    step_name: str,
    step_spec: str,
    feedback: str,
    completion_conditions: Sequence[str] = (),
    criteria_path: str = DEFAULT_COMPLETION_CRITERIA_PATH,
) -> str:
    safe_spec = sanitize_log(step_spec, max_length=12000)
    safe_feedback = sanitize_log(feedback) if feedback else ""
    criteria = _criteria_text(completion_conditions, criteria_path)
    return f"""You are the implementation sub-agent for Harness.

Phase: {phase}
Step: {step} / {step_name}

Implement the step specification below. Write the code and add or update tests first,
then run the step acceptance commands. You may edit implementation and test files, but
do not commit, push, or merge. Return changed relative paths and validation results.

Read the confirmed completion criteria file before writing. Preserve every criterion.
{criteria}

Step specification:
{safe_spec}

Feedback from the previous review or CI attempt:
{safe_feedback or "None"}
"""


def review_prompt(
    *,
    role: AgentRole,
    phase: str,
    step: int,
    step_name: str,
    step_spec: str,
    changed_files: Sequence[str],
    feedback: str,
    completion_conditions: Sequence[str] = (),
    criteria_path: str = DEFAULT_COMPLETION_CRITERIA_PATH,
) -> str:
    role_label = "code review" if role == AgentRole.CODE_REVIEW else "test review"
    safe_spec = sanitize_log(step_spec, max_length=12000)
    safe_feedback = sanitize_log(feedback) if feedback else ""
    criteria = _criteria_text(completion_conditions, criteria_path)
    return f"""You are the read-only {role_label} sub-agent for Harness.

Phase: {phase}
Step: {step} / {step_name}
Changed files: {", ".join(changed_files) or "none"}

Completion criteria:
{criteria}

Read the step specification and every changed file. Compare the specification with the
actual behavior, identify missing requirements, and do not edit files or commit. For code
review, compare completion criteria 1 through N one by one and report each as pass or fail
with evidence path:line. Give a concrete recommendation for every failed criterion. Directly
run unit tests and integration tests, then run Ruff, Mypy, Pytest, and
`pytest --cov --cov-fail-under=80`. Verify that tests exercise externally observable
behavior rather than implementation details. Report every failure with its cause and a
concrete recommendation for the implementation agent.

Step specification:
{safe_spec}

Previous feedback:
{safe_feedback or "None"}
"""


def security_review_prompt(
    *,
    phase: str,
    step: int,
    step_name: str,
    step_spec: str,
    changed_files: Sequence[str],
    feedback: str,
) -> str:
    safe_spec = sanitize_log(step_spec, max_length=12000)
    safe_feedback = sanitize_log(feedback) if feedback else ""
    return f"""You are the read-only security review sub-agent for Harness.

Phase: {phase}
Step: {step} / {step_name}
Changed files: {", ".join(changed_files) or "none"}

Read the step specification and changed files. Inspect YAML and workflow behavior,
relative paths and traversal, untrusted input validation, subprocess boundaries, and logs
for credentials or customer data exposure. Do not edit files and do not commit. Report
four explicit checks named yaml, paths, inputs, and logs, plus severity, cause, and a
concrete fix recommendation for every issue.

Step specification:
{safe_spec}

Previous feedback:
{safe_feedback or "None"}
"""


def ci_feedback(result: CIResult) -> str:
    failures = "; ".join(sanitize_log(item) for item in result.failures) or "CI did not pass"
    log = sanitize_log(result.log)
    suffix = f" Log: {log}" if log else ""
    return (
        f"PR CI failed ({result.status}): {failures}.{suffix} "
        "Diagnose the failure and fix it in the next implementation attempt."
    )


def finding_feedback(role: AgentRole, findings: Sequence[ReviewFinding]) -> list[str]:
    return [
        f"{role} finding [{finding.severity}] {sanitize_log(finding.title)}: "
        f"{sanitize_log(finding.detail)} Fix: {sanitize_log(finding.recommendation)}"
        for finding in findings
        if finding.blocking
    ]


def criteria_feedback(reviews: Sequence[CompletionCriterionReview]) -> list[str]:
    return [
        f"completion criterion {review.number} failed: evidence {sanitize_log(review.evidence)} "
        f"Fix: {sanitize_log(review.recommendation)}"
        for review in reviews
        if review.status == "fail"
    ]


def _criteria_text(conditions: Sequence[str], criteria_path: str) -> str:
    if not conditions:
        return f"File: {criteria_path}\nNo completion criteria supplied."
    numbered = "\n".join(
        f"{number}. {sanitize_log(condition, max_length=2000)}"
        for number, condition in enumerate(conditions, start=1)
    )
    return f"File: {criteria_path}\n{numbered}"
