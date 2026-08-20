---
name: harness-workflow
description: Use this skill when planning or executing Harness framework phases and steps, creating `phases/index.json`, `phases/{task}/index.json`, `stepN.md` files, or orchestrating phase execution with Codex worker subagents.
origin: harness_framework
---

# Harness Workflow

이 프로젝트는 Harness 프레임워크를 사용한다. 작업을 phase와 step으로 나누어 설계하고, 승인된 step 파일은 Codex 메인 세션이 worker 서브 에이전트로 순차 실행한다. 한 step의 구현이 끝나면 메인 세션은 구현 결과를 그대로 커밋하지 않고, Code Review·Test Review를 병렬로 실행한 뒤 Security Review와 trusted CI gate까지 통과시킨다. Implementation은 시작 시 heartbeat를 초기화하고 약 60초마다 runtime progress를 갱신한다.

## Workflow

### A. 탐색

`/docs/` 하위 문서(PRD, ARCHITECTURE, ADR 등)를 읽고 프로젝트의 기획, 아키텍처, 설계 의도를 파악한다. 필요시 독립적인 탐색 작업을 병렬화한다.

### B. 논의

구현을 위해 구체화하거나 기술적으로 결정해야 할 사항이 있으면 사용자에게 제시하고 논의한다.

### C. Step 설계

사용자가 구현 계획 작성을 지시하면 여러 step으로 나뉜 초안을 작성해 피드백을 요청한다.

설계 원칙:

1. **Scope 최소화**: 하나의 step에서 하나의 레이어 또는 모듈만 다룬다. 여러 모듈을 동시에 수정해야 하면 step을 쪼갠다.
2. **자기완결성**: 각 step 파일은 독립된 worker 서브 에이전트가 수행한다. 외부 대화 참조 없이 필요한 정보를 전부 파일 안에 적는다.
3. **사전 준비 강제**: 관련 문서 경로와 이전 step에서 생성/수정된 파일 경로를 명시한다.
4. **시그니처 수준 지시**: 함수/클래스의 인터페이스만 제시하고 내부 구현은 에이전트 재량에 맡긴다. 단, 멱등성, 보안, 데이터 무결성 같은 핵심 규칙은 명시한다.
5. **AC는 실행 가능한 커맨드**: `.harness/validation.json` 또는 step specification에 정의된 실제 검증 커맨드를 포함한다. `npm`, Python, Go 등 도구는 프로젝트 profile이 선택한다.
6. **주의사항은 구체적으로**: "X를 하지 마라. 이유: Y" 형식으로 적는다.
7. **네이밍**: step name은 kebab-case slug로, 핵심 모듈/작업을 한두 단어로 표현한다.

## Files To Create

### `phases/index.json`

여러 task를 관리하는 top-level 인덱스. 이미 존재하면 `phases` 배열에 새 항목을 추가한다.

```json
{
  "phases": [
    {
      "dir": "0-mvp",
      "status": "pending"
    }
  ]
}
```

- `dir`: task 디렉토리명.
- `status`: `"pending"` | `"completed"` | `"error"` | `"blocked"`.
- 타임스탬프(`completed_at`, `failed_at`, `blocked_at`)는 실행 오케스트레이터가 상태 변경 시 기록한다. 생성 시 넣지 않는다.

### `phases/{task-name}/index.json`

```json
{
  "project": "<프로젝트명>",
  "phase": "<task-name>",
  "steps": [
    { "step": 0, "name": "project-setup", "status": "pending" },
    { "step": 1, "name": "core-types", "status": "pending" },
    { "step": 2, "name": "api-layer", "status": "pending" }
  ]
}
```

- `project`: 프로젝트명 (`AGENTS.md` 참조).
- `phase`: task 이름. 디렉토리명과 일치시킨다.
- `steps[].step`: 0부터 시작하는 순번.
- `steps[].name`: kebab-case slug.
- `steps[].status`: 초기값은 모두 `"pending"`.

상태 전이:

| 전이 | 기록되는 필드 | 기록 주체 |
|------|-------------|----------|
| → `completed` | `completed_at`, `summary` | worker (summary), 메인 세션 (metadata) |
| → `error` | `failed_at`, `error_message` | worker (message), 메인 세션 (metadata) |
| → `blocked` | `blocked_at`, `blocked_reason` | worker (reason), 메인 세션 (metadata) |

`summary`는 다음 step 프롬프트에 컨텍스트로 누적 전달되므로, 생성된 파일과 핵심 결정을 한 줄로 담는다.

### `phases/{task-name}/step{N}.md`

```markdown
# Step {N}: {이름}

## 읽어야 할 파일

먼저 아래 파일들을 읽고 프로젝트의 아키텍처와 설계 의도를 파악하라:

- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`
- {이전 step에서 생성/수정된 파일 경로}

## 작업

{구체적인 구현 지시. 파일 경로, 클래스/함수 시그니처, 로직 설명을 포함.
코드 스니펫은 인터페이스/시그니처 수준만 제시하고, 구현체는 에이전트에게 맡겨라.
단, 설계 의도에서 벗어나면 안 되는 핵심 규칙은 명확히 박아넣어라.}

## Acceptance Criteria

```bash
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 검증 절차

1. 위 AC 커맨드를 실행한다.
2. 아키텍처 체크리스트를 확인한다:
   - ARCHITECTURE.md 디렉토리 구조를 따르는가?
   - ADR 기술 스택을 벗어나지 않았는가?
   - AGENTS.md CRITICAL 규칙을 위반하지 않았는가?
3. 최종 응답에 결과를 보고한다:
   - 성공 → `status: completed`, `summary: "산출물 한 줄 요약"`
   - 실패 → `status: error`, `error_message: "구체적 에러 내용"`
   - 사용자 개입 필요 → `status: blocked`, `blocked_reason: "구체적 사유"`

## 금지사항

- {이 step에서 하지 말아야 할 것. "X를 하지 마라. 이유: Y" 형식}
- 기존 테스트를 깨뜨리지 마라
- phase metadata와 git commit은 메인 세션이 담당하므로 worker가 직접 수정하지 마라
```

## Execute

사용자가 phase 실행을 요청하면 메인 세션이 오케스트레이터가 된다. 외부 headless CLI runner나 sandbox 우회 방식은 사용하지 않는다.

상세 실행 프로토콜은 `references/subagent-execution.md`를 읽고 따른다.

메인 세션이 자동으로 처리하는 것:

- `feat-{task-name}` 브랜치 생성/checkout
- 각 pending step을 worker 서브 에이전트에 하나씩 위임
- `AGENTS.md` + `docs/*.md` 경로와 완료된 step `summary`를 worker 프롬프트에 전달
- 구현 worker 완료 후 code-review worker와 test worker를 병렬 실행
- 두 리뷰가 모두 통과한 뒤 security-review worker를 실행
- 리뷰 결과를 종합하고, 실패하면 구현 worker에 원인·수정 제안을 전달해 재실행
- 리뷰 통과 후에만 커밋하고 PR을 생성/갱신하며, PR CI 성공을 확인한 뒤 병합
- PR CI가 실패하면 실패 원인과 안전하게 정제된 로그를 다음 구현 시도의 피드백으로 전달
- review/security/CI 실패는 `pipeline_attempt`로 최대 3회 재시도
- implementation이 `started_at` 기준 1800초를 넘기면 `stuck`으로 종료하고 `stuck_retry`를 별도로 증가시켜 새 implementation worker를 실행한다. 최대 3회 초과 시 step은 `error`다.
- heartbeat는 60초 간격 runtime state이고, Main session은 같은 주기로 phase/step/attempt/progress 사용자 status update를 제공한다.
- 코드 변경(`feat`)과 메타데이터(`chore`)를 분리 커밋
- `started_at`, `completed_at`, `failed_at`, `blocked_at` 기록
- 사용자가 명시한 경우에만 `git push -u origin feat-{task-name}` 실행

worker가 담당하는 것:

- 구현 worker는 step 파일과 관련 문서를 직접 읽고 코드와 테스트를 작성한다
- 구현 worker는 AC 커맨드를 실행하지만 git commit, push, merge는 하지 않는다
- Code Review는 step specification, Completion Criteria 1..N, architecture/ADR/AGENTS 규칙, logic, API/data contract, maintainability, scope와 profile에서 자신에게 배정된 check를 검증한다. Completion Criteria는 각 항목을 정확히 한 번씩 `pass/fail` 및 `path:line` 근거로 보고한다.
- Test Review는 profile에서 자신에게 배정된 unit/integration/e2e/regression/coverage check와 externally observable behavior를 검증한다. Code Review와 같은 전체 test suite를 중복 실행하지 않는다.
- profile에 없는 언어 도구를 추측하거나 실행하지 않는다. required validation check가 없거나 실행되지 않으면 fail closed 한다.
- security-review worker는 YAML, 경로 traversal, 입력값 검증, subprocess 경계, 로그의 credential·고객 데이터 노출을 점검한다
- 리뷰 worker는 기본적으로 파일을 수정하거나 커밋하지 않는다. 리뷰 결과의 `changed_files`와 `committed`는 비어 있어야 한다
- 최종 응답으로 `status`, `summary`, `changed_files`, `validation`, 필요 시 `error_message` 또는 `blocked_reason`을 보고한다
- git commit, push, phase metadata 수정은 하지 않는다

Step 실행 순서는 다음과 같다:

```text
implementation
    ↓
code-review + test-review (parallel, read-only)
    ↓
security-review (read-only)
    ↓
main decision
    ├─ finding/failed check → implementation feedback → review again
    └─ all pass → commit → PR CI check → merge
                         └─ CI failure → diagnose → implementation feedback → review again
```

구현·리뷰·보안 결과의 접근 경계와 필수 검증 항목은 `scripts/step_pipeline.py`의 계약을 따른다. 메인 세션은 이 계약을 만족하지 않는 결과를 성공으로 처리하지 않는다.

### Runtime·criteria·profile contract

- Runtime state는 `.harness/runtime/{phase}/step{N}-attempt{pipeline_attempt}.json`에 저장한다. 상태는 `running`, `completed`, `stuck`, `error`, `blocked` 중 하나다.
- `started_at`을 implementation attempt의 timeout 기준으로 사용한다. 마지막 heartbeat인 `updated_at`으로 timeout을 연장하지 않는다.
- Heartbeat payload에는 `started_at`, `updated_at`, `elapsed_seconds`, `progress`, `status_update_interval_seconds=60`, `stuck_after_seconds=1800`, `pipeline_attempt`, `stuck_retry`, `max_stuck_retries=3`을 포함한다.
- `pipeline_attempt`는 review/security/CI 실패 retry이고 `stuck_retry`는 implementation timeout retry다. `stuck_retry` 초과 시 자동 재시도하지 않고 `error`로 종료한다.
- 사용자 확인 전 completion criteria는 pipeline을 실행하지 않으며 Markdown artifact도 쓰지 않는다. 확인 후 criteria artifact가 durable source of truth가 된다. 조건 수는 최소 1개, 최대값은 profile이 정한다.
- `.harness/validation.json`이 project command source다. `reviewChecks.code-review`는 Code Review, `reviewChecks.test-review`는 Test Review가 실행한다. Stop Hook은 `stopChecks`만 실행한다.
- `stepPolicies`는 `feature`, `bugfix`, `refactor`, `docs`, `ci`, `config`, `metadata`별 test-change 요구를 정의한다. docs/CI/config/metadata는 test 파일 변경을 무조건 요구하지 않는다.
- Reviewer mutation은 Git tracked/untracked 상태와 digest를 먼저 비교하고, profile의 `reviewMutationIgnore`에 있는 generated output만 무시한다. `.git` metadata mutation은 별도로 차단한다.

에러 복구:

- `error`: 해당 step의 `status`를 `"pending"`으로 바꾸고 `error_message`를 삭제한 뒤 재실행한다.
- `blocked`: `blocked_reason`을 해결한 뒤 `status`를 `"pending"`으로 바꾸고 `blocked_reason`을 삭제한 뒤 재실행한다.
