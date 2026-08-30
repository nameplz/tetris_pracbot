# Step 2: benchmark-report

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/completion-criteria.md`
- Phase 5 이전 step 산출물

## 작업

Self-play 결과를 stable machine-readable benchmark report로 집계한다. Win Rate, APM, PPS, APP, garbage, cancel/clear, B2B, stack, top-out, decision latency P50/P95/P99, search nodes/nodes/sec를 기록한다. malformed CLI 입력은 fail fast하고 report schema version과 seed/preset/side-swap metadata를 포함한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- 결과를 유리하게 보이도록 side-swapped 결과를 버리지 마라.
- metric을 이름만 추가하고 실제 집계하지 마라.
- phase metadata나 git commit을 수정하지 마라.
