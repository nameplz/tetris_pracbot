# 아키텍처

## 디렉토리 구조
```
src/
├── app/               # 페이지 + API 라우트
├── components/        # UI 컴포넌트
├── types/             # TypeScript 타입 정의
├── lib/               # 유틸리티 + 헬퍼
└── services/          # 외부 API 래퍼
```

## 패턴
{사용하는 디자인 패턴 (예: Server Components 기본, 인터랙션이 필요한 곳만 Client Component)}

## 데이터 흐름
```
{데이터가 어떻게 흐르는지 (예:
사용자 입력 → Client Component → API Route → 외부 API → 응답 → UI 업데이트
)}
```

## 상태 관리
{상태 관리 방식 (예: 서버 상태는 Server Components, 클라이언트 상태는 useState/useReducer)}

## Harness 실행 계층

Step 실행은 메인 에이전트가 오케스트레이션하고, 역할별 worker의 결과는 명시적인 계약으로 검증한다.

- `scripts/step_contracts.py`: phase/step, 상대 경로, worker payload, 리뷰 명령, 보안 점검, 로그의 경계 검증
- `scripts/step_prompts.py`: 구현·코드 리뷰·테스트·보안 리뷰 worker의 역할과 금지사항
- `scripts/step_pipeline.py`: 구현 → code-review/test 병렬 실행 → security-review → 메인 커밋 → PR CI → 병합 순서와 재시도
- `tests/test_step_pipeline.py`: 실패 피드백, read-only 위반, 경로 traversal, 로그 정제, CI 실패 재작업 계약 테스트

리뷰 worker는 파일을 수정하거나 커밋하지 않으며, 모든 blocking finding은 구현 worker의 다음 시도에 전달한다. 메인 에이전트는 코드·메타데이터 커밋과 PR 병합만 담당한다.
