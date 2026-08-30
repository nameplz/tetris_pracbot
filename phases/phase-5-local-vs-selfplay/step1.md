# Step 1: selfplay-runner

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `phases/phase-5-local-vs-selfplay/step0.md`

## 작업

고정 seed 목록으로 A-vs-B와 side-swapped B-vs-A를 실행하는 self-play runner를 만든다. Match isolation, max turns, deterministic event logs, invalid candidate/move counters, reproducible match result를 보장한다. CLI로 소수 smoke games와 batch games를 구분한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- seed/preset/side를 생략한 비교를 만들지 마라.
- 한 match의 mutable state를 다음 match에 재사용하지 마라.
- phase metadata나 git commit을 수정하지 마라.
