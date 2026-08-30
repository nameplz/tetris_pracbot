# Step 1: heuristic-agent

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `phases/phase-3-heuristic-ai/step0.md`
- Phase 2 Move/Candidate 계약

## 작업

Evaluator와 GreedyAgent를 구현한다. Agent 계약은 `GameState → Move`로 유지하고 Move Generator 결과만 선택한다. death risk를 우선 penalize하고 stable tie-break를 사용한다. seeded RandomAgent를 benchmark baseline으로 제공한다. Agent 호출 전후 GameState serialization이 같아야 한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- Agent가 Simulator state를 직접 바꾸게 하지 마라.
- Greedy를 Search처럼 lookahead하게 만들지 마라.
- phase metadata나 git commit을 수정하지 마라.
