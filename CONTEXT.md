# TETR.IO AI Bot Context

이 파일은 프로젝트의 공통 용어 사전이다. 세부 규칙과 단계는
[메인 기획서](<docs/TETR.IO AI Bot 기획서 v1.3.md>)를, 시스템 경계는
[아키텍처](<docs/ARCHITECTURE.md>)를 따른다.

- **Ruleset**: 특정 시점의 공개·관찰 가능한 TETR.IO 규칙을 버전으로 고정한 기준이다.
- **Bot Standard Preset**: 학습·benchmark·최종 Bot 환경에 공통으로 적용하는 게임 설정이다.
- **GameState**: 한 시점의 양쪽 보드, piece, queue, hold, garbage, 공격·위험 상태를 표현하는 권위 있는 게임 상태다.
- **Move**: 현재 상태에서 봇이 선택한 최종 placement와 실행 경로를 나타낸다.
- **Candidate**: Move Generator가 실제 조작으로 도달 가능하다고 인정한 Move 후보이다.
- **Move Generator**: 현재 GameState에서 유효하고 도달 가능한 Candidate를 생성한다.
- **Evaluator**: 보드·공격·방어·상대 압력을 하나의 비교 가능한 값으로 평가한다.
- **Search**: 여러 Candidate의 미래 상태를 탐색해 Move를 선택한다.
- **Simulator**: Ruleset에 따라 GameState를 전이시키는 headless 1v1 실행 환경이다.
- **Self-play**: 고정 seed와 대전 조건으로 AI끼리 반복 대전하는 과정이다.
- **Benchmark**: 승률·플레이 지표·latency·자원 사용량을 같은 조건에서 비교하는 실행이다.
- **Execution Scheduler**: 선택된 Move의 실행 시점만 target PPS에 맞춰 조절한다.
- **Fixture**: 특정 입력·상태에 대한 규칙 결과를 고정한 검증 사례다.

실제 TETR.IO 연결, Bot Account 승인, 온라인 서비스는 이 프로젝트의 runtime 범위가 아니다.
