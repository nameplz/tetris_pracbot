# Viewer 디자인 가이드

MVP UI는 제품 홍보 화면이 아니라 AI 대전을 확인하는 CPU·CLI 우선 관찰 도구다.
viewer는 [아키텍처](<./ARCHITECTURE.md>)의 Simulator 상태와 replay 결과만 표시한다.

## 원칙

1. **Board first**: 두 보드와 현재 piece/garbage 상황이 가장 먼저 보여야 한다.
2. **Debuggable**: seed, ruleset, preset, 상태와 핵심 지표를 숨기지 않는다.
3. **Deterministic**: 자동 animation보다 pause·step·replay를 우선한다.
4. **Color independent**: 색상만으로 piece, garbage, danger를 구분하지 않는다.

## MVP 화면

- Header: seed, ruleset snapshot, preset, match status
- Main: self/opponent board와 visible 10×20 영역
- Metrics: W/L, PPS, APM, APP, garbage cancel/clear, B2B, stack height, latency P50/P95/P99
- Controls: start, pause, step, replay, speed/PPS, quit
- Optional debug view: 현재 GameState, 선택 Move, 평가값, input path

터미널 폭이 충분하면 두 보드를 나란히 놓고, 그렇지 않으면 세로로 쌓는다. hidden/buffer
row는 기본 화면에 숨기고 debug 옵션에서만 표시한다.

## 표시 규칙

| 대상 | 기본 표시 | 보조 정보 |
|---|---|---|
| 빈 칸 | `.` | grid 위치 |
| 블록 | piece 문자 또는 색상 | piece 이름 |
| garbage | `X` | 줄 수·도착 timing |
| 위험 상태 | `!`와 텍스트 | stack height / top-out risk |
| 일시정지 | 고정 상태 banner | 현재 seed와 tick |

색상은 보조 수단으로만 사용하며, 대비가 낮은 회색·장식용 gradient·glow를 사용하지 않는다.
기본 font는 terminal monospace이고, 보드 비율과 10×20 격자를 깨지 않는다.

## 동작과 접근성

- 기본 모드는 정지·step 가능한 replay이며 자동 진행은 명시적으로 시작한다.
- pause, step, quit는 마우스 없이 사용할 수 있어야 한다.
- 로그에는 사람이 읽을 수 있는 상태명과 seed를 함께 출력한다.
- 불필요한 애니메이션과 깜박임을 사용하지 않는다.
