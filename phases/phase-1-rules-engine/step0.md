# Step 0: ruleset-and-state

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `docs/completion-criteria.md`
- `docs/TETR.IO AI Bot 기획서 v1.3.md`
- `phases/phase-1-rules-engine/index.json`

## 작업

Ruleset과 Bot Standard Preset을 typed immutable Python 값으로 정의한다. Ruleset 버전, 공개·관찰 가능한 지원 범위, fixture provenance, visible width/height, hidden/buffer 정책, 7-bag, NEXT 5, Hold, 0G, lock delay 500ms, SRS+, garbage/attack toggles를 명시한다. GameState, PlayerState, Board, Piece, queue, hold, garbage queue, combo/B2B/Surge 상태와 deterministic seed를 정의한다. Simulator 권위 원칙에 맞게 snapshot은 외부에서 바꿀 수 없어야 한다.

규칙을 추측해 외부 호환성을 과장하지 말고 현재 문서가 명시한 관찰 가능한 범위만 지원한다. 안정된 serialization과 입력 검증을 제공한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 검증 절차

1. Ruleset/Preset/GameState 생성·serialization·invalid input 테스트를 먼저 작성하고 실패를 확인한다.
2. 최소 구현 후 두 명령을 실행한다.
3. immutable snapshot과 seed 재현성을 확인한다.

## 금지사항

- TETR.IO network adapter, credential, online service를 추가하지 마라. 저장소 경계 위반이다.
- Simulator 전이 로직이나 AI를 이 step에 넣지 마라. 이후 step의 계약이 흔들린다.
- phase metadata나 git commit을 수정하지 마라.
