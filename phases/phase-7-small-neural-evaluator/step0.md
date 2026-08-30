# Step 0: adoption-gate

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ADR.md`
- `docs/completion-criteria.md`
- Phase 6 optimization report

## 작업

Phase 6 결과가 heuristic Search 완료 조건을 통과하면 이 step은 `not planned`로 기록하고 neural code를 만들지 않는다. 완료 조건을 통과하지 못하고 실제 gap이 증명된 경우에만 200K–1.5M parameter CPU evaluator 실험을 설계한다. 어떠한 경우에도 기존 Evaluator/Search contract, deterministic local data, credential-free scope를 유지한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 검증 절차

1. Phase 6 paired benchmark evidence를 확인한다.
2. heuristic Search가 충분하면 status를 completed, summary에 `not planned: heuristic Search sufficient`를 기록한다.
3. gap이 있을 때만 별도 implementation plan을 만들고 parameter/latency/VS gate를 추가한다.

## 금지사항

- benchmark evidence 없이 neural dependency를 추가하지 마라.
- LLM, cloud training, network data, credentials를 추가하지 마라.
- phase metadata나 git commit을 수정하지 마라.
