# Step 0: measurement

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ADR.md`
- `docs/completion-criteria.md`
- Phase 5 benchmark contract와 summaries

## 작업

동일 preset/seed/side-swap 조건에서 Greedy, Search, optimized Search의 strength/latency/resource를 비교할 수 있는 measured optimization profile을 추가한다. 설정과 결과를 stable report로 남기고 fixed smoke profile을 제공한다. percentile 계산과 resource sampling은 표준 라이브러리로 충분한 최소 구현을 사용한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- seed/side/preset이 다른 결과를 비교하지 마라.
- 측정값을 하드코딩하지 마라.
- phase metadata나 git commit을 수정하지 마라.
