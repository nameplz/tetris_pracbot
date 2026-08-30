# Step 1: soak-and-evidence

## 읽어야 할 파일

- `AGENTS.md`
- `CONTEXT.md`
- `docs/completion-criteria.md`
- `phases/phase-9-final-local-validation/step0.md`

## 작업

반복 seeded self-play와 configurable duration soak를 실행해 invalid move, crash, state corruption, CPU/memory 사용량을 증거로 남긴다. 동일 입력의 event-log hash와 final report hash를 비교한다. 기본 full mode는 1시간을 지원하고 CI에는 짧은 smoke duration을 사용한다. 실패 시 seed, turn, phase, state summary를 안전하게 출력한다.

## Acceptance Criteria

```bash
python3 -m unittest discover -s tests
python3 scripts/validate_project.py --root . --strict --config .harness/validation.json
```

## 금지사항

- soak 결과를 숨기거나 실패한 run을 성공으로 표시하지 마라.
- 고객 데이터, credential, network input을 수집하지 마라.
- phase metadata나 git commit을 수정하지 마라.
