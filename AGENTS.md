# TETR.IO AI Bot — Agent Instructions

이 저장소의 상세 요구사항을 복제하지 말고 아래 문서를 source of truth로 참조한다.

- 목표·단계·규칙 범위: [메인 기획서](<docs/TETR.IO AI Bot 기획서 v1.3.md>)
- 공통 용어: [CONTEXT.md](CONTEXT.md)
- 모듈 경계와 계약: [ARCHITECTURE.md](<docs/ARCHITECTURE.md>)
- 되돌리기 어려운 결정: [ADR.md](<docs/ADR.md>)
- 완료 판단과 초기 수치: [completion-criteria.md](<docs/completion-criteria.md>)
- viewer 범위: [UI_GUIDE.md](<docs/UI_GUIDE.md>)

## 프로젝트 경계

- runtime은 별도 Python 프로젝트로 구현하며 CPU·CLI를 기본 환경으로 삼는다.
- 이 프로젝트에는 TETR.IO network adapter, Bot Account 인증, credential, 온라인 서비스를 추가하지 않는다.
- 호환성은 구현 시작일에 고정한 공개·관찰 가능한 Ruleset 범위만 보장한다.

## 반드시 지킬 규칙

- Simulator가 GameState의 권위자다. AI는 GameState → Move만 수행하고 상태를 직접 변경하지 않는다.
- 상태 전이는 가능한 한 새 값을 반환하며, seed와 Ruleset을 명시해 deterministic 결과를 유지한다.
- Move Generator는 실제 도달 가능한 Candidate만 반환한다. 규칙 변경은 source와 fixture를 먼저 갱신한다.
- Heuristic + Search가 기본이며 Neural은 완료 조건을 통과할 때만 추가한다.
- 구현 변경은 테스트를 먼저 작성하고 pytest로 검증한다. lint/typecheck 명령은 대상 프로젝트 profile을 따른다.
- docs 변경은 관련 문서의 참조와 placeholder/충돌을 검증한다. 상세 요구사항을 AGENTS.md에 다시 쓰지 않는다.

## 작업 순서

1. 위 문서와 CONTEXT를 읽고 용어·범위를 확인한다.
2. 규칙/상태/전이 변경은 fixture와 회귀 테스트를 먼저 추가한다.
3. benchmark는 동일 preset, seed, side-swap 조건으로 실행한다.
4. 완료 전 [완료 조건](<docs/completion-criteria.md>)을 하나씩 검증하고 결과를 기록한다.
