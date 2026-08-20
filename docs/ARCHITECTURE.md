# 아키텍처

## 디렉토리 구조
```
src/
├── app/               # 페이지 + API 라우트
├── components/        # UI 컴포넌트
├── types/             # TypeScript 타입 정의
├── lib/               # 유틸리티 + 헬퍼
└── services/          # 외부 API 래퍼
```

## 패턴
{사용하는 디자인 패턴 (예: Server Components 기본, 인터랙션이 필요한 곳만 Client Component)}

## 데이터 흐름
```
{데이터가 어떻게 흐르는지 (예:
사용자 입력 → Client Component → API Route → 외부 API → 응답 → UI 업데이트
)}
```

## 상태 관리
{상태 관리 방식 (예: 서버 상태는 Server Components, 클라이언트 상태는 useState/useReducer)}

## Harness 실행 계층

Step 실행은 메인 에이전트가 오케스트레이션하고, 역할별 worker의 결과는 명시적인 계약으로 검증한다.

- `scripts/step_contracts.py`: phase/step, 상대 경로, worker payload, 리뷰 명령, 보안 점검, 로그의 경계 검증
- `scripts/step_prompts.py`: 구현·코드 리뷰·테스트·보안 리뷰 worker의 역할과 금지사항
- `scripts/step_pipeline.py`: heartbeat 초기화·status update·stuck watchdog → 구현 → code-review/test 병렬 실행 → security-review → 메인 커밋 → trusted PR CI → 병합 순서와 재시도
- `scripts/phase_worktree.py`: `started_at` 기준 30분 timeout, 60초 runtime heartbeat, `stuck_retry` lifecycle
- `scripts/harness_validation.py`: project-defined validation profile, reviewer별 check, stop check, step test policy, mutation ignore
- `tests/`: profile이 지정한 명령과 외부 동작을 검증하는 regression contract

### Implementation lifecycle

Runtime artifact는 `.harness/runtime/{phase}/step{N}-attempt{pipeline_attempt}.json`에 저장한다.

```text
implementation start → running heartbeat/status update (60s)
    ├─ completed within 1800s → code/test review
    └─ started_at + 1800s 초과 → stuck → 새 worker (최대 3 stuck retry)
                                      └─ 초과 → error
```

`started_at`은 마지막 heartbeat와 독립된 timeout 기준이다. `pipeline_attempt`는 review,
security, CI 실패 재작업 횟수이고 `stuck_retry`는 구현 timeout 재시도 횟수다.
Main session은 약 60초마다 phase, step, attempt, elapsed, progress를 사용자에게 전달한다.
구체적인 플랫폼 전송 구현은 `MainActions`/`AgentRunner` extension point로 남긴다.

### Project validation profile

`.harness/validation.json`이 유일한 project validation command source다.
`commands`에 argv 배열과 역할을 정의하고, `stopChecks`, `reviewChecks`, `stepPolicies`,
`reviewMutationIgnore`, `maxCompletionConditions`가 같은 profile을 참조한다.
Harness core는 명령 이름이나 언어를 추측하지 않는다. 예: Python은 pytest/ruff/mypy,
Node/TypeScript는 vitest/eslint/tsc, Go는 go test/go vet을 프로젝트가 직접 정의한다.

Code Review는 spec, architecture, ADR, completion criteria, logic, contract, scope와
자신에게 배정된 lint/typecheck check를 담당한다. Test Review는 unit/integration/e2e,
regression, coverage와 자신에게 배정된 test check를 담당한다. 두 reviewer가 같은 전체
suite를 반복 실행하지 않는다. Security Review는 별도 read-only 역할이다.

Step test policy는 `feature=required`, `bugfix=regression`, `refactor=optional`,
`docs/ci/config/metadata=none`을 기본으로 하며 profile에서 조정할 수 있다.

Completion criteria는 최소 1개, 권장 3~10개, 최대값은 profile에서 설정한다. 사용자 확인
전에는 pipeline과 Markdown artifact를 만들지 않는다. 확인 후 `docs/completion-criteria.md`
를 durable source로 저장하고, 구현·Code Review에 같은 artifact와 조건을 전달한다.
Code Review는 조건 1..N을 정확히 한 번씩 `pass/fail` 및 `path:line` 근거로 평가한다.

Reviewer mutation 검사는 Git status/diff 기반으로 먼저 수행하고 untracked file도 포함한다.
Git 외 workspace에서는 제한된 filesystem snapshot을 사용한다. `reviewMutationIgnore`에
명시한 generated artifact만 무시하며 `.git` metadata mutation은 별도로 항상 차단한다.

리뷰 worker는 파일을 수정하거나 커밋하지 않으며, 모든 blocking finding은 구현 worker의 다음 시도에 전달된다. 메인 에이전트는 코드·메타데이터 커밋과 PR 병합만 담당한다.
