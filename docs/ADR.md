# Architecture Decision Records

용어는 [CONTEXT.md](../CONTEXT.md), 전체 설계는
[메인 기획서](<./TETR.IO AI Bot 기획서 v1.3.md>)를 참조한다.

## ADR-001: 로컬 simulator 우선

**상태**: Accepted

**결정**: 실제 TETR.IO 연결보다 Rules Engine, headless 1v1, self-play를 먼저 완성한다.

**이유**: 외부 승인과 네트워크 변수를 제거해 AI의 정확성·성능·재현성을 독립적으로 검증한다.

**트레이드오프**: 실제 환경과의 차이는 후속 adapter 프로젝트에서 다시 검증해야 한다.

## ADR-002: 구현 시작일 ruleset과 고정 preset

**상태**: Accepted

**결정**: 구현 시작일의 공개·관찰 가능한 규칙을 versioned snapshot으로 고정하고,
학습·benchmark·최종 Bot 환경에는 하나의 Bot Standard Preset만 사용한다.

**이유**: TETR.IO 변경으로 과거 결과가 흔들리는 것을 막고 비교 조건을 통제한다.

**트레이드오프**: 규칙 변경 때마다 snapshot, fixture, 관련 테스트를 함께 갱신해야 한다.

## ADR-003: GameState와 Agent를 외부 연결 경계로 사용

**상태**: Accepted

**결정**: AI는 GameState만 입력받아 Move를 반환하는 Agent 계약을 따른다.

**이유**: Simulator와 향후 adapter를 분리하면서 Search·Evaluator를 재사용할 수 있다.

**트레이드오프**: 상태 모델과 전이 순서를 초기에 정밀하게 정의해야 한다.

## ADR-004: Heuristic + Beam Search를 기본으로 하고 Neural은 선택 사항으로 둠

**상태**: Accepted

**결정**: Greedy/Heuristic을 baseline으로 만들고 Beam Search를 주력으로 한다. Neural evaluator는
기존 Search 대비 실제 VS 성능 향상이 benchmark로 확인될 때만 채택한다.

**이유**: 로컬 CPU 실행과 빠른 반복을 우선하고 불필요한 모델 복잡도를 피한다.

**트레이드오프**: Neural 도입을 미루는 대신 복잡한 포지션의 성능 개선을 heuristic/search에 의존한다.

## ADR-005: AI 판단과 실행 속도 분리

**상태**: Accepted

**결정**: AI는 최선의 Move를 계산하고 Execution Scheduler가 target PPS에 맞춰 실행한다.

**이유**: 같은 AI를 여러 속도로 평가하고 strength와 PPS를 독립적으로 조절하기 위해서다.

**트레이드오프**: 계산 지연이나 늦은 path가 target PPS를 못 맞추는 경우의 정책을 별도로 테스트해야 한다.
