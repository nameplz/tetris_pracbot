# 아키텍처

이 문서는 [메인 기획서](<./TETR.IO AI Bot 기획서 v1.3.md>)의 구조를 구현 가능한 경계로
압축한 것이다. Bot runtime은 별도 Python 프로젝트로 두며, 이 저장소의 Harness 도구와
TETR.IO 외부 연결을 runtime 의존성으로 만들지 않는다.

## 원칙

- Ruleset과 seed를 명시해 같은 입력이 같은 결과를 만들게 한다.
- Simulator가 GameState의 유일한 권위자이며 AI는 상태를 읽고 Move를 반환한다.
- 상태 전이는 새 상태를 반환하고, viewer는 상태를 변경하지 않는다.
- 규칙 호환성은 구현 시작일에 고정한 공개·관찰 가능한 범위와 fixture로 판단한다.
- Headless 실행을 기준으로 삼고 viewer는 관찰·재생 계층으로 둔다.

## 디렉터리 구조

~~~text
tetrio-bot/
├── rules/              # versioned public/observable ruleset snapshots
├── configs/            # bot_standard, AI/search 설정
├── engine/             # board, pieces, rotation, garbage, attack, rules, movegen, simulator
├── ai/                 # heuristic, search, optional neural, pathfinder
├── arena/              # versus, selfplay
├── training/           # optional dataset/train
├── benchmark/          # benchmark runner and reports
├── visual/             # observation/replay viewer
└── tests/              # unit, integration, fixture, determinism tests
~~~

## 핵심 흐름

~~~text
Ruleset + Preset + Seed
          ↓
      Simulator → GameState snapshot
          ↓
    Move Generator → Candidate States
          ↓
    Evaluator + Search → Move
          ↓
 Pathfinder → Execution Scheduler → 다음 GameState
~~~

상대의 line clear·garbage·pressure도 Simulator가 같은 규칙으로 처리한다. AI는 TETR.IO
API나 화면을 직접 읽지 않는다.

## 계약

~~~python
class Agent:
    def choose_move(self, state: GameState) -> Move:
        ...
~~~

- **GameState**: AI와 Simulator 사이의 공통 상태 표현이다.
- **Move**: Hold, piece, rotation, position, spin, input path를 포함할 수 있으며 도달 가능해야 한다.
- **Ruleset**: 규칙 버전과 fixture의 근거를 함께 가진다.
- **Execution Scheduler**: AI의 선택을 바꾸지 않고 placement timing만 조절한다.
- **Viewer**: replay/event 결과를 표시하며 Simulator의 권위 상태를 변경하지 않는다.

Neural evaluator를 도입하더라도 동일한 Evaluator/Search 경계 안에서 선택 사항으로 남긴다.
