# CHO-FAM Mail Functions

공통 메일 발송 인프라. 게임서버(liv-ay)를 포함한 여러 서비스가 이 API를 호출해 메일을 보내고,
`/admin/mail/`(매니저 웹페이지)에서 발송 기록을 조회·재전송합니다.

## 엔드포인트

베이스 URL: `https://cho-fam.web.app/api/mail` (Hosting rewrite를 통해 Functions로 연결)

| Method | Path | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/send` | `x-api-key` | 메일 발송. Body: `{ to, templateId, dynamicData }` |
| GET | `/logs` | `x-api-key` (admin) | 발송 기록 조회. Query: `source`, `status`, `limit` |
| POST | `/logs/:id/resend` | `x-api-key` (admin) | 실패 건 재전송 |

## 설정

1. SendGrid에서 발신 도메인 인증(SPF/DKIM) 및 동적 템플릿 생성
2. 서비스별 API 키 발급 (예: liv-ay 게임서버용, 매니저 웹페이지 admin용) — 자세한 절차는 [API_KEYS.md](./API_KEYS.md) 참고
3. 시크릿 등록:
   ```bash
   firebase functions:secrets:set SENDGRID_API_KEY
   firebase functions:secrets:set MAIL_API_KEYS
   # MAIL_API_KEYS 값 예시: {"<liv-ay-key>":"liv-ay","<admin-key>":"CHO-FAM-admin"}
   ```
4. 로컬 개발 시 `functions/.env` 생성 (`.env.example` 참고, git에는 커밋되지 않음)
5. 배포: `firebase deploy --only functions,firestore,hosting`

## 호출 서비스 추가 방법

1. `MAIL_API_KEYS`에 새 키:서비스명 쌍 추가 후 시크릿 재배포
2. 호출 시 헤더 `x-api-key: <발급받은 키>` 사용
3. 관리자 화면에서 해당 서비스 발송 내역을 보려면 `MAIL_ADMIN_SOURCES`에 서비스명 추가

메일 발송 API를 실제로 호출하는 코드 예시(curl/Node.js/Python)는
[SENDING_GUIDE.md](./SENDING_GUIDE.md)를 참고하세요.
