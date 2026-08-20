# Architecture Decision Records

## 철학
{프로젝트의 핵심 가치관 (예: MVP 속도 최우선. 외부 의존성 최소화. 작동하는 최소 구현을 선택.)}

---

### ADR-001: {결정 사항 (예: Next.js App Router 선택)}
**결정**: {뭘 선택했는지}
**이유**: {왜 선택했는지}
**트레이드오프**: {뭘 포기했는지}

### ADR-002: {결정 사항}
**결정**: {뭘 선택했는지}
**이유**: {왜 선택했는지}
**트레이드오프**: {뭘 포기했는지}

### ADR-003: {결정 사항}
**결정**: {뭘 선택했는지}
**이유**: {왜 선택했는지}
**트레이드오프**: {뭘 포기했는지}

### ADR-004: Step별 역할 분리형 품질 게이트
**결정**: 구현 worker와 read-only code-review/test/security-review worker를 분리하고, 메인 에이전트가 리뷰·PR CI 결과를 종합한 뒤에만 커밋·병합한다.
**이유**: 구현 변경과 검증 판단을 분리해 누락된 요구사항, 테스트 부족, YAML·경로·입력·로그 보안 문제를 구현 단계에서 반복적으로 수정할 수 있어야 한다.
**트레이드오프**: 한 step마다 리뷰와 CI 대기 시간이 늘어나지만, 실패 원인과 수정 제안이 다음 구현 시도에 남고 리뷰 worker의 우발적 변경을 차단할 수 있다.

### ADR-005: Implementation watchdog lifecycle
**결정**: implementation attempt는 `started_at`부터 1800초로 제한하고, runtime heartbeat와 사용자 status update는 60초 간격으로 유지한다. timeout 재시도(`stuck_retry`)와 review/CI 재시도(`pipeline_attempt`)를 분리한다.
**이유**: heartbeat가 계속 살아 있어도 무한 implementation을 허용하면 main session이 진행을 판단할 수 없다.
**트레이드오프**: 실행 adapter가 deadline을 존중해야 하며, 최대 stuck retry 초과 시 자동 복구 대신 `error`로 멈춘다.

### ADR-006: Project-defined validation profile
**결정**: `.harness/validation.json`의 argv command와 reviewer/stop 역할을 validation source of truth로 사용한다.
**이유**: skeleton core가 Python, Node, Go, Rust 도구를 추측하거나 reviewer마다 같은 suite를 중복 실행하지 않게 한다.
**트레이드오프**: concrete project가 profile을 작성해야 하며, required check 누락은 fail-closed 된다.

### ADR-007: Step validation policy
**결정**: step kind별 `required`, `regression`, `optional`, `none` test-change policy를 사용한다.
**이유**: feature/bugfix 보호는 유지하면서 docs, CI, config, metadata 작업에 불필요한 test-file 변경을 강제하지 않는다.
**트레이드오프**: bugfix는 regression test 경로를 명시해야 하고, optional step은 기존 validation 결과에 더 의존한다.

### ADR-008: Durable completion criteria
**결정**: 사용자 확인 후 criteria를 Markdown artifact로 저장하고 pipeline은 session-local draft state를 source of truth로 사용하지 않는다.
**이유**: 새 세션도 phase metadata, step artifact, confirmed criteria artifact만 읽어 workflow 상태를 복원할 수 있어야 한다.
**트레이드오프**: 사용자 확인은 명시적 입력으로 남고, artifact write/read 검증이 추가된다.

### ADR-009: Git-first reviewer mutation detection
**결정**: reviewer 전후 Git status와 파일 digest를 우선 비교하고, non-Git workspace만 제한된 filesystem snapshot으로 보완한다. generated output은 profile의 `reviewMutationIgnore`로만 예외 처리한다.
**이유**: 대형 repository의 전체 파일 해시 비용과 generated artifact false positive를 줄이면서 tracked/untracked mutation을 잡는다.
**트레이드오프**: ignore 설정이 과도하면 검출 범위가 줄어들므로 `.git` metadata는 별도 검사로 항상 차단한다.
