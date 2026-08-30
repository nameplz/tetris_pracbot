# Step 1: piece-and-board-transitions

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `phases/phase-1-rules-engine/step0.md`
- 완료된 Step 0 산출물과 summary

## 작업

Step 0의 Board/Piece/GameState 계약 위에 표준 piece geometry, spawn, collision, SRS+ rotation/kick, Hold/NEXT, 7-bag, hard drop, lock, line clear, spin classification, top-out 전이를 추가한다. 각 전이는 새 snapshot을 반환한다. Hold는 piece lock 전 한 번만 허용한다. hidden/buffer row는 visible 10×20 projection과 분리한다. transition 결과는 다음 phase가 Candidate legality를 검증할 수 있게 충분한 metadata를 포함한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 검증 절차

1. spawn, bag, Hold/NEXT, kick, drop, clear, spin, top-out fixture를 먼저 작성한다.
2. fixture 실패를 확인한 뒤 최소 전이를 구현한다.
3. 동일 seed에서 queue와 serialized state가 동일한지 확인한다.

## 금지사항

- 좌표 조합만 나열해 reachable 판정을 대신하지 마라. Phase 2 책임이다.
- 상태를 in-place mutation하지 마라. Simulator 권위와 replay가 깨진다.
- phase metadata나 git commit을 수정하지 마라.
