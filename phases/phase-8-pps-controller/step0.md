# Step 0: execution-scheduler

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `docs/UI_GUIDE.md`
- Phase 5 simulator and Phase 6 metrics summaries

## 작업

선택된 Move를 변경하지 않고 target PPS에 맞춰 실행 시점만 조절하는 Execution Scheduler를 구현한다. 최소 0.6 PPS, monotonic clock, start/pause/resume/step/quit, overdue policy, target/actual PPS와 timing error를 typed immutable snapshot/event로 제공한다. Ruleset 전이는 clock을 보지 않는다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- Scheduler가 Move를 재선택하거나 수정하지 마라.
- zero/negative PPS를 허용하지 마라.
- phase metadata나 git commit을 수정하지 마라.
