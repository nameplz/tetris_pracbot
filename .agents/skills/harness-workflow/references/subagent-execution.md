# Subagent Execution Protocol

이 문서는 Harness phase를 Codex 메인 세션과 역할별 worker 서브 에이전트로 실행하는 절차다. 메인 세션은 오케스트레이터이자 최종 결정자이고, 구현 worker는 한 번에 하나의 step을 구현한다. 리뷰·테스트·보안 worker는 같은 step을 읽기 전용으로 검증한다.

## Trigger

사용자가 phase 실행을 요청하면 이 프로토콜을 따른다. 예:

- "`0-mvp` phase 실행해줘"
- "`0-mvp`를 harness-workflow 방식으로 실행하고 push까지 해줘"

외부 headless CLI runner, sandbox 우회 옵션, 별도 실행 스크립트는 사용하지 않는다.

## Main Session Responsibilities

1. `phases/index.json`과 `phases/{phase}/index.json`을 읽는다.
2. 기존 `error` 또는 `blocked` step이 있으면 실행하지 않고 사용자에게 복구 방법을 보고한다.
3. `feat-{phase}` 브랜치를 checkout하거나 생성한다.
4. phase `created_at`이 없으면 기록한다.
5. 첫 번째 `pending` step부터 순차 실행한다.
6. 구현 worker를 실행해 코드와 테스트를 작성하게 한다.
7. code-review worker와 test worker를 병렬 실행한다. 둘 다 통과한 경우에만 다음 단계로 간다.
8. security-review worker를 실행한다.
9. 메인 세션이 모든 결과를 종합한다. 문제가 있으면 구현 worker에 정제된 실패 원인과 수정 제안을 전달하고 같은 검증 순서를 반복한다.
10. 리뷰가 통과한 경우에만 메인 세션이 커밋하고 PR CI를 확인한다.
11. PR CI가 실패하면 원인을 확인해 다음 구현 시도의 피드백으로 전달한다. CI가 성공한 뒤에만 병합한다.
12. 각 step의 `started_at`, `completed_at`, `failed_at`, `blocked_at`을 기록한다.
13. 전체 실행 결과를 `phases/{phase}/step{N}-output.json`에 저장한다.
14. 코드 변경과 metadata/output 변경을 분리 커밋한다.
15. 모든 step 완료 후 phase와 top-level index를 `completed`로 갱신한다.
16. 사용자가 push를 명시한 경우에만 `git push -u origin feat-{phase}`를 실행한다.

Implementation worker 시작 직전 메인 세션은 `started_at`을 기록하고 runtime heartbeat를
초기화한다. worker 실행 중 heartbeat는 약 60초마다 `progress`와 `updated_at`을 갱신하고,
메인 세션은 같은 주기로 사용자 status update를 제공한다. `started_at`부터 1800초가 지나면
heartbeat가 최근이어도 해당 attempt는 `stuck`이다. `stuck_retry`는 새 implementation
worker로 별도 재시도하고, `pipeline_attempt`(review/security/CI 실패 retry)와 합산하지 않는다.
최대 stuck retry를 넘으면 step은 `error`다.

메인 세션은 구현 세부 작업을 직접 수행하지 않는다. 단, worker 결과 검토, metadata 갱신, 커밋, 재시도 판단은 메인 세션이 담당한다.

## Worker Launch

각 pending step마다 구현 worker 하나를 먼저 실행한다. 구현 worker가 끝난 뒤 code-review worker와 test worker만 동시에 실행하고, 두 결과를 받은 뒤 security-review worker를 실행한다.

- `agent_type`: `worker`
- `fork_context`: `false`
- 서로 다른 step의 구현은 동시에 실행하지 않는다.
- code-review/test worker는 읽기 전용 요청(`read_only: true`, `allow_commit: false`)을 받는다.
- security-review worker도 읽기 전용 요청을 받는다.
- worker는 같은 코드베이스에서 혼자 작업하지 않는다는 전제를 반드시 받는다.

## Worker Prompt Template

아래 템플릿을 step별 값으로 채워 worker에게 전달한다.

```markdown
You are handling one Harness step in this repository.

You are not alone in the codebase. Do not revert edits made by others. Adjust your implementation to accommodate existing changes.

## Scope

- Phase: `{phase}`
- Step: `{step_number}` / `{step_name}`
- Step file: `phases/{phase}/step{step_number}.md`
- Phase index: `phases/{phase}/index.json`

## Required Reading

Read these files before editing:

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `docs/PRD.md`
- `docs/UI_GUIDE.md` if present
- `phases/{phase}/step{step_number}.md`

Previous completed step summaries:

{completed_step_summaries}

## Rules

- Implement or review only this step.
- Do not implement future steps.
- Do not modify phase metadata files.
- The implementation worker may edit code and tests but must not commit, push, or merge.
- The code-review/test/security worker must not edit files, commit, push, or merge.
- Code Review와 Test Review는 `.harness/validation.json`의 `reviewChecks`에 배정된 argv만 직접 실행한다. Code Review는 spec/architecture/ADR/criteria/logic/contract/scope를 담당하고, Test Review는 externally observable behavior, regression, coverage와 배정된 test check를 담당한다. profile에 없는 Python/Node/Go/Rust 도구를 추측하지 않으며 같은 전체 suite를 중복 실행하지 않는다.
- The security worker must report explicit `yaml`, `paths`, `inputs`, and `logs` checks, including any credential or customer-data exposure.
- Every reviewer must report failure cause and a concrete fix recommendation; the main session sends those findings back to the implementation worker.
- Run the Acceptance Criteria commands from the step file when the role permits it.
- If a required secret, account, network permission, external service, or manual setup is missing, stop and return `blocked`.

## Final Response Contract

Return:

- `status`: implementation `completed` | `error` | `blocked`; reviewer `completed`/`passed` | `failed` | `error` | `blocked`
- `summary`: one-line summary when completed
- `changed_files`: list of changed paths
- `validation`: commands run and results
- `error_message`: required when status is `error`
- `blocked_reason`: required when status is `blocked`

Review results additionally include:

- `role`: `code-review`, `test`, or `security-review`
- `changed_files`: must be empty for a reviewer
- `committed`: must be `false` for a reviewer
- `findings`: severity, cause, and a concrete recommendation
- `validation`: project profile이 reviewer에게 배정한 check의 name, argv, pass/fail, output
- `security_checks`: `yaml`, `paths`, `inputs`, and `logs` for security review
```

On retry, append:

```markdown
## Previous Attempt Failure

{previous_error_message}

Fix the cause above. Do not repeat the failed approach.
```

## Result Handling

### Completed

When implementation and all reviews return successful results:

1. Review changed files enough to confirm scope.
2. Compare the step specification with the implementation and both review results.
3. Update the step entry only after security review and PR CI pass:
   - `status`: `completed`
   - `summary`: implementation and review summary
   - `completed_at`: current timestamp
4. Save `step{N}-output.json` with implementation, code review, test review, security review, main decision, and CI results.
5. Commit code changes first:
   - `feat({phase}): step {N} - {step-name}`
6. Commit metadata/output changes:
   - `chore({phase}): step {N} output`
7. Continue to the next pending step.

If a code review, test review, security review, or PR CI check fails:

1. Do not mark the step completed and do not merge.
2. Keep the failure cause, command result, and recommendation in the output record.
3. Send the sanitized feedback to a new implementation attempt.
4. Re-run code review and test review, then security review, in that order.
5. Stop as `error` after the retry limit or `blocked` when manual/external intervention is required.

### Blocked

When worker returns `blocked`:

1. Update the step entry:
   - `status`: `blocked`
   - `blocked_reason`: worker reason
   - `blocked_at`: current timestamp
2. Update `phases/index.json` phase status to `blocked`.
3. Save `step{N}-output.json`.
4. Commit metadata/output changes if possible.
5. Stop execution and report the reason.

### Error

When worker returns `error`, violates the response contract, or leaves the step incomplete:

1. Retry up to 3 total attempts.
2. Include the previous error in the next worker prompt.
3. If all attempts fail, update the step entry:
   - `status`: `error`
   - `error_message`: final error with attempt count
   - `failed_at`: current timestamp
4. Update `phases/index.json` phase status to `error`.
5. Save `step{N}-output.json`.
6. Commit metadata/output changes if possible.
7. Stop execution and report the error.

## Output JSON

Save each attempt result to `phases/{phase}/step{N}-output.json` with this shape:

```json
{
  "step": 0,
  "name": "step-name",
  "attempt": 1,
  "status": "completed",
  "summary": "one-line summary",
  "changed_files": ["path/to/file"],
  "implementation": {"status": "completed", "summary": "..."},
  "code_review": {"status": "passed", "findings": []},
  "test_review": {"status": "passed", "findings": []},
  "security_review": {"status": "passed", "findings": []},
  "validation": ["command: result"],
  "ci": {"status": "passed", "failures": []},
  "decision": "merge",
  "error_message": null,
  "blocked_reason": null,
  "started_at": "YYYY-MM-DDTHH:MM:SS+0900",
  "finished_at": "YYYY-MM-DDTHH:MM:SS+0900"
}
```

## Recovery

- To retry an `error` step, set its `status` to `pending` and remove `error_message` and `failed_at`.
- To retry a `blocked` step, resolve the blocker, set `status` to `pending`, and remove `blocked_reason` and `blocked_at`.
- Preserve completed step summaries; they are the context bridge for later workers.
