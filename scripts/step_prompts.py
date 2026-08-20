#!/usr/bin/env python3
"""Prompt builders for the Harness step roles."""

from __future__ import annotations

from collections.abc import Sequence

from scripts.harness_validation import HarnessCommand
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
    step_kind: str = "feature",
    test_requirement: str = "required",
) -> str:
    safe_spec = sanitize_log(step_spec, max_length=12000)
    safe_feedback = sanitize_log(feedback) if feedback else ""
    criteria = _criteria_text(completion_conditions, criteria_path)
    return f"""You are the implementation sub-agent for Harness.

Phase: {phase}
Step: {step} / {step_name}
Step kind: {step_kind}
Test-change policy: {test_requirement}

Implement the step specification below. Follow the configured test-change policy, then
run the project-defined acceptance commands. You may edit implementation and test files, but
do not commit, push, or merge. Return changed relative paths and validation results.

At implementation start, initialize runtime heartbeat. Keep it updated about every 60
seconds with current progress and stop it with a terminal state when the attempt ends.
The attempt has a 30-minute limit measured from started_at, independent of heartbeat
updates. If it exceeds the limit, report stuck so the main session can start a new worker;
do not confuse that with review/CI pipeline retry.

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
    review_checks: Sequence[HarnessCommand] = (),
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

Project validation checks assigned to this reviewer:
{_checks_text(review_checks)}

Read the step specification and every changed file. Compare the specification with the
actual behavior, identify missing requirements, and do not edit files or commit. For code
review, compare completion criteria 1 through N one by one and report each as pass or fail
with evidence path:line. Give a concrete recommendation for every failed criterion. Directly
run every configured check assigned to this reviewer. Code review owns specification,
architecture, ADR, criteria, logic, contracts, maintainability, scope, and only its
assigned checks. Test review owns externally observable behavior, regression, coverage,
and only its assigned checks. Do not invent tools that are not in the project profile.

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


def _checks_text(checks: Sequence[HarnessCommand]) -> str:
    if not checks:
        return "No project validation checks configured. Do not substitute language-specific tools."
    return "\n".join(
        f"- {check.name}: {' '.join(check.command)} — {sanitize_log(check.reason, max_length=1000)}"
        for check in checks
    )
