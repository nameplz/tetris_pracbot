# Step 3: rules-fixtures

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `docs/completion-criteria.md`
- Phase 1 이전 step 산출물

## 작업

Phase 1의 공개·관찰 가능한 규칙 범위를 fixture 중심으로 고정한다. 알려진 board/rotation/spawn/clear/spin/garbage/top-out 사례와 seed replay를 machine-readable fixture로 보존하고, Ruleset 근거 문서와 연결한다. fixture suite가 이후 phase의 regression seam이 되도록 public behavior만 검증한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 검증 절차

1. 지원 규칙마다 최소 한 fixture와 negative case를 둔다.
2. fixture suite 100% 통과를 확인한다.
3. 동일 seed/Ruleset/Preset/player side event log hash를 비교한다.

## 금지사항

- fixture를 통과시키려고 규칙을 약화하지 마라.
- 비공개 동작을 근거 없이 fixture로 만들지 마라.
- phase metadata나 git commit을 수정하지 마라.
