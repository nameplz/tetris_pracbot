# Step 2: path-validation

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- Phase 2 이전 step 산출물

## 작업

반환된 input path를 replay해 Candidate final state가 실제 transition과 일치하는지 검증한다. 외부 Move를 Candidate 집합과 비교해 invalid move를 거절하고 rejection reason을 제공한다. 모든 Candidate path가 collision/rotation/Hold 규칙을 지키는지 회귀 테스트한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- invalid path를 조용히 수정해 valid로 바꾸지 마라. 호출자가 오류를 알아야 한다.
- Search나 Simulator의 책임을 이 step으로 끌어오지 마라.
- phase metadata나 git commit을 수정하지 마라.
