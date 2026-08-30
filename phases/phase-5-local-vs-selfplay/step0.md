# Step 0: local-simulator

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `docs/completion-criteria.md`
- Phase 1–4 완료 summaries

## 작업

두 Agent를 authoritative Local 1v1 Simulator로 실행한다. GameState transition, Move validation, garbage exchange, top-out, terminal result, event log를 headless deterministic loop로 제공한다. Agent는 snapshot만 읽고 Move를 반환한다. event log에는 seed, Ruleset, Preset, side, tick, Move, outcome을 남긴다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- AI가 보드를 직접 수정하게 하지 마라.
- viewer나 wall-clock scheduler를 simulator core에 넣지 마라.
- phase metadata나 git commit을 수정하지 마라.
