# Step 0: move-model

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- Phase 1 완료 summaries

## 작업

Move, Candidate, input action/path, reachability diagnostics를 immutable typed 값으로 정의한다. Move는 Hold 사용 여부, piece, rotation, x/y, spin, input path를 담고 Candidate는 결과 snapshot과 비용/metadata를 담는다. Stable serialization, deterministic ordering key, Move validation 계약을 제공한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- Phase 1 GameState를 복제해 별도 권위 상태를 만들지 마라.
- 미래 AI evaluator나 scheduler를 구현하지 마라.
- phase metadata나 git commit을 수정하지 마라.
