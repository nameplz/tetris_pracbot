# Step 0: beam-search

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- Phase 2/3 완료 summaries

## 작업

Move Generator와 Heuristic Evaluator를 사용해 depth/beam width가 bounded인 Beam Search를 구현한다. 각 ply의 NEXT/Hold branch를 확장하고 terminal branch를 prune한다. root Move, leaf score, nodes searched, nodes/sec를 SearchResult로 반환한다. iteration order와 tie-break는 deterministic이어야 한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- unbounded minimax나 global mutable cache를 추가하지 마라.
- Search가 Simulator state를 직접 변경하지 마라.
- phase metadata나 git commit을 수정하지 마라.
