# Completion Criteria

이 기준은 [메인 기획서](<./TETR.IO AI Bot 기획서 v1.3.md>)와 인터뷰에서 확정한 범위를
구현 완료 판단으로 바꾼 것이다. 초기 수치는 첫 benchmark 실행 전에 고정하며, 변경할 때는
[ADR](<./ADR.md>)에 이유를 남긴다.

1. **Ruleset 고정**: 구현 시작일의 공개·관찰 가능한 규칙 범위가 versioned snapshot으로
   저장되고, 각 지원 규칙의 근거와 fixture가 있다. 비공개 동작은 보장 범위에서 제외한다.
2. **규칙 정확성**: 유지 중인 fixture suite가 100% 통과하고, 7-bag, Hold/NEXT, SRS+, Spin,
   line clear, garbage, attack, Combo/B2B/Surge, top-out 등 지원 규칙의 전이 순서가 재현된다.
3. **재현성**: 같은 Ruleset, Preset, seed, player side에서 event log와 승패가 동일하다.
   비교 benchmark는 같은 seed의 양쪽 side 교환을 포함한다.
4. **Move Generator**: 생성된 Candidate는 모두 실제 도달 가능하며, seeded 1v1 실행에서
   invalid candidate와 invalid move가 0건이다.
5. **AI 강도**: 1,000 paired games 기준으로 Greedy가 Random보다, Search가 Greedy보다
   높은 승률을 기록하고 각 비교의 승률이 55% 이상이다.
6. **Simulator/Benchmark**: TETR.IO 없이 headless 1v1과 대량 self-play가 가능하며,
   Win Rate, APM, PPS, APP, garbage, B2B, stack, top-out, search nodes를 기록한다.
7. **Latency**: 개발 머신 기준 decision latency가 P95 100ms 이하, P99 250ms 이하이며
   search nodes와 nodes/sec를 함께 기록한다.
8. **PPS/Viewer**: 동일 AI가 최소 0.6 PPS에서 동작하고, 측정 구간의 평균 PPS 오차가 ±5% 이내다.
   viewer에서 seed match를 pause·step·replay하고 핵심 지표를 확인할 수 있다.
9. **안정성**: 최소 1시간 headless soak test에서 invalid move, crash, state corruption이
   0건이고 CPU·메모리 사용량을 기록한다.
10. **범위 준수**: Neural evaluator는 20만~150만 parameter 범위에서 기존 Search보다 실제
    VS 성능이 향상될 때만 채택한다. TETR.IO adapter와 Bot 승인 신청은 로컬 검증 이후의
    별도 외부 단계이며, 승인 신청이 이 프로젝트의 마지막 작업이다.
