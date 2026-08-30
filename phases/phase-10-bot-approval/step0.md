# Step 0: manual-handoff

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `docs/completion-criteria.md`
- Phase 9 final evidence

## 작업

Phase 9가 완료된 경우에만 사용할 수 있는 manual handoff checklist를 문서로 정리한다. 목적, 로컬 Ruleset/Preset, 지원 PPS, AI 구조, abuse-prevention, benchmark evidence와 project boundary를 포함한다. 저장소에는 승인 신청을 실행하는 코드나 credential을 두지 않는다. Phase 9 미완료 시 handoff 상태는 blocked/not ready로 표시한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- Bot Account 인증, 토큰, 쿠키, network adapter, online submission을 추가하지 마라.
- Phase 9 evidence 없이 approval ready라고 표시하지 마라.
- phase metadata나 git commit을 수정하지 마라.
