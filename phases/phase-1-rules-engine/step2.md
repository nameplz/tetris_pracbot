# Step 2: garbage-and-attack

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/ADR.md`
- `phases/phase-1-rules-engine/step0.md`
- `phases/phase-1-rules-engine/step1.md`
- 완료된 이전 step summaries

## 작업

Ruleset의 line clear 결과를 garbage 생성, cancellation, timing/travel, attack, combo, B2B Charging, Surge, Opener Phase, All Clear, Clutch Clear에 연결한다. 공격 결과와 incoming garbage queue를 typed immutable 값으로 반환한다. 이벤트 순서를 명확히 한다: lock → classify/clear → cancel incoming → apply attack → enqueue opponent garbage → update streak/terminal state. 멀티플레이어 연결 없이 순수 전이로 구현한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 검증 절차

1. garbage cancel, combo/B2B, surge/opener, all-clear/clutch, overflow fixture를 먼저 작성한다.
2. event ordering과 deterministic serialization을 검증한다.
3. invalid garbage/attack 입력은 명확한 오류로 거절한다.

## 금지사항

- wall-clock을 Ruleset 전이에 넣지 마라. seed/replay 결정성이 깨진다.
- 실제 네트워크 전달이나 online room을 추가하지 마라.
- phase metadata나 git commit을 수정하지 마라.
