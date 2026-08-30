# Step 0: completion-validator

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/completion-criteria.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- Phase 1–8 summaries and reports

## 작업

문서의 completion criteria 1..10을 각각 정확히 한 번 pass/fail과 measured evidence로 보고하는 CPU/CLI validator를 만든다. Ruleset/Preset/seed/side-swap consistency, fixture, invalid moves, benchmark strength, latency, PPS/replay, stability evidence를 기존 seams에서 읽는다. CI용 bounded smoke와 로컬 full mode를 분리하고 missing/mismatched evidence는 fail closed한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- 기준을 통과시키려고 threshold나 evidence를 낮추지 마라.
- 네트워크/승인 요청을 validator에 넣지 마라.
- phase metadata나 git commit을 수정하지 마라.
