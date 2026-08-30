# Step 1: reachable-search

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `phases/phase-2-move-generator/step0.md`
- Phase 1 transition/fixture 산출물

## 작업

현재 GameState에서 legal left/right/rotate/drop action graph를 탐색해 실제 도달 가능한 Candidate만 반환한다. SRS+ kick, collision, Hold 초기 branch, one-Hold-per-piece, hard-drop landing, terminal rejection을 Phase 1 transition과 공유한다. Candidate를 final placement metadata로 deduplicate하고 stable order를 유지한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- `(rotation, x)`를 직접 열거해 reachable이라고 주장하지 마라.
- wall-clock/random iteration order에 의존하지 마라.
- phase metadata나 git commit을 수정하지 마라.
