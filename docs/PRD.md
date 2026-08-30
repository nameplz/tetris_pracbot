# PRD: TETR.IO AI Bot

상세 목표와 단계는 [메인 기획서](<./TETR.IO AI Bot 기획서 v1.3.md>)를 기준으로 한다.
이 문서는 제품 범위와 MVP 판단에 필요한 내용만 요약한다.

## 목표

구현 시작일에 고정한 공개·관찰 가능한 TETR.IO multiplayer 규칙을 로컬에서 재현하고,
실제 플레이어와 대전할 수 있는 저지연 AI의 핵심을 TETR.IO 연결 없이 검증한다.

## 사용자

- **AI 개발자**: ruleset, move generation, evaluator, search를 개선하고 benchmark로 비교한다.
- **검증자/관찰자**: seeded 1v1과 viewer로 AI의 플레이·지연·안정성을 확인한다.

## MVP 범위

1. versioned Ruleset과 Bot Standard Preset
2. 10×20 visible board와 필요한 hidden/buffer를 포함한 Rules Engine
3. reachable Move Generator와 path generation
4. Heuristic Evaluator와 Beam Search
5. headless Local 1v1 Simulator, seeded Self-play, Benchmark
6. 최소 0.6 PPS를 지원하는 Execution Scheduler와 관찰·재생 중심 viewer

## 제외 범위

- TETR.IO network adapter, Bot Account 연결, 승인 신청 자동화
- LLM, 온라인 서비스, 복잡한 GUI
- Neural evaluator의 필수 도입

Neural evaluator는 Heuristic + Search가 충분하지 않을 때만 별도 benchmark로 판단한다.

## 성공 판단

구체적인 fixture, 승률, latency, 재현성, PPS, 장시간 안정성 기준은
[완료 조건](<./completion-criteria.md>)에 고정한다. MVP의 결과는 같은 seed와 preset에서
재현 가능해야 하며, Search는 Greedy baseline보다 강해야 한다.
