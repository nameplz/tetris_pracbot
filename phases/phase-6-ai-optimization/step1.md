# Step 1: pruning-and-cache

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ADR.md`
- `phases/phase-6-ai-optimization/step0.md`

## 작업

Search boundary 안에만 deterministic pruning과 per-decision/per-match cache를 추가한다. cache key는 immutable state와 search config를 포함해야 하며 match 간 오염이 없어야 한다. optimized result가 기존 legal Move와 deterministic output contract를 유지하는지 검증한다. 측정상 이득이 없는 복잡성은 추가하지 않는다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- global mutable cache를 만들지 마라.
- strength/latency 측정 없이 최적화가 성공했다고 하지 마라.
- phase metadata나 git commit을 수정하지 마라.
