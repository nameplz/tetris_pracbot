# Step 0: feature-extractor

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- Phase 1/2 완료 summaries

## 작업

Candidate 결과를 외부 behavior 중심의 typed feature vector로 변환한다. holes, covered holes, stack height, bumpiness, wells, top-out risk, attack, cancel, combo, B2B, incoming garbage, opponent pressure를 포함하고 feature breakdown을 안정적으로 serialize한다. Weight set은 immutable typed config로 두고 Bot Standard Preset 기본값을 제공한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- GameState나 Board를 mutation하지 마라.
- Neural dependency나 Search를 추가하지 마라.
- phase metadata나 git commit을 수정하지 마라.
