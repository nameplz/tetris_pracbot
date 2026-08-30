# Step 1: time-budget

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `phases/phase-4-search-ai/step0.md`

## 작업

Search에 positive depth/width와 bounded decision time budget을 검증해 연결한다. 예산이 먼저 끝나면 이미 완성한 최선의 root Move를 반환하고, 아무 branch도 완료되지 않으면 Greedy legal fallback을 사용한다. budget, fallback, node counters, deterministic result를 테스트한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- 예산 초과를 무시하고 무한히 계산하지 마라.
- invalid fallback을 반환하지 마라.
- phase metadata나 git commit을 수정하지 마라.
