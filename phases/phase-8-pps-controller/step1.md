# Step 1: replay-controls

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/UI_GUIDE.md`
- `docs/ARCHITECTURE.md`
- `phases/phase-8-pps-controller/step0.md`

## 작업

headless replay/event stream에 pause, step, replay, quit와 speed/PPS control을 연결한다. 기본은 정지·step 가능한 상태로 두고 자동 진행은 명시적 start가 필요하다. seed, Ruleset, Preset, tick, current Move, metrics를 CLI에서 읽을 수 있게 한다. viewer가 있어도 GameState 권위는 Simulator에 둔다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- 색상이나 animation만으로 상태를 전달하지 마라.
- viewer가 Simulator state를 직접 mutation하지 마라.
- phase metadata나 git commit을 수정하지 마라.
