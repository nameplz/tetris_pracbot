---
name: harness-review
description: Use this skill when reviewing changes in this Harness framework project for architecture compliance, ADR alignment, test coverage, AGENTS.md critical rules, and buildability.
origin: harness_framework
---

# Harness Review

이 프로젝트의 변경 사항을 리뷰할 때 사용한다. 리뷰는 버그, 위험, 회귀, 누락된 테스트를 우선한다. 리뷰·테스트·보안 worker는 기본적으로 읽기 전용이며, 결과를 작성하고 수정은 구현 worker와 메인 세션에 맡긴다.

## Required Reading

먼저 다음 문서들을 읽는다:

- `/AGENTS.md`
- `/docs/ARCHITECTURE.md`
- `/docs/ADR.md`

그런 다음 변경된 파일을 확인하고 체크리스트로 검증한다.

## Checklist

1. **아키텍처 준수**: `ARCHITECTURE.md`에 정의된 디렉토리 구조를 따르는가?
2. **기술 스택 준수**: `ADR.md`에 정의된 기술 선택을 벗어나지 않았는가?
3. **테스트 존재**: 새로운 기능 또는 변경된 동작에 대한 테스트가 작성되어 있는가?
4. **CRITICAL 규칙**: `AGENTS.md`의 CRITICAL 규칙을 위반하지 않았는가?
5. **빌드 가능**: 빌드/테스트 명령어가 에러 없이 통과하는가?
6. **리뷰 계약**: `.harness/validation.json`의 reviewer별 check를 직접 실행했고 외부 동작을 검증하는가? Code Review와 Test Review가 같은 전체 suite를 중복 실행하지 않았는가? 리뷰 worker가 파일을 수정하거나 커밋하지 않았는가?
7. **보안 범위**: YAML, 경로 traversal, 입력값 경계, subprocess, 로그의 credential·고객 데이터 노출을 점검했는가?
8. **CI 게이트**: PR 이후 CI 결과가 성공했는가? 실패 시 원인과 구현 worker용 수정 제안이 기록되었는가?
9. **Watchdog**: implementation `started_at`, 60초 heartbeat/status update, 1800초 stuck 판정, `pipeline_attempt`/`stuck_retry` 분리가 contract와 일치하는가?
10. **Criteria**: 1..N completion criteria가 durable artifact에서 동일하게 전달되고, Code Review가 각 항목을 한 번씩 `pass/fail`·`path:line`으로 평가하는가?
11. **Mutation**: Git tracked/untracked 변경, configured generated ignore, `.git` metadata 변경을 각각 검증하는가?

## Output Format

```markdown
| 항목 | 결과 | 비고 |
|------|------|------|
| 아키텍처 준수 | ✅/❌ | {상세} |
| 기술 스택 준수 | ✅/❌ | {상세} |
| 테스트 존재 | ✅/❌ | {상세} |
| CRITICAL 규칙 | ✅/❌ | {상세} |
| 빌드 가능 | ✅/❌ | {상세} |
| 리뷰 계약 | ✅/❌ | {profile이 배정한 check·정적 분석과 read-only 확인} |
| 보안 범위 | ✅/❌ | {YAML·경로·입력·로그 결과} |
| PR CI 게이트 | ✅/❌ | {CI 결과 또는 실패 원인} |
```

위반 사항이 있으면 파일/라인 근거와 수정 방안을 구체적으로 제시한다. 심각한 문제를 먼저 나열하고, 요약은 뒤에 짧게 둔다.
