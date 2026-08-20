# Completion Criteria

이 파일은 사용자 확인 후 Harness pipeline이 durable artifact로 생성한다.

정책:

- 조건은 최소 1개다.
- 3~10개를 권장한다.
- 최대 개수는 `.harness/validation.json`의 `maxCompletionConditions`로 설정한다.
- 확인 전에는 pipeline을 실행하거나 이 Markdown artifact를 생성·수정하지 않는다.
- 확인 후 구현 worker와 Code Review worker는 같은 조건 목록을 사용한다.
- Code Review는 조건 1..N을 정확히 한 번씩 `pass/fail` 및 `path:line` 근거로 평가한다.
