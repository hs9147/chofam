# CHO-FAM Mail Functions

공통 메일 발송 인프라. 게임서버(liv-ay)를 포함한 여러 서비스가 이 API를 호출해 메일을 보내고,
`/admin/mail/`(매니저 웹페이지)에서 발송 기록을 조회·재전송합니다.

같은 `api` 함수가 `/api/payout/*`(토스페이먼츠 지급대행 프록시 — liv-ay 크리에이터 정산
입금)도 서빙합니다. 인증은 동일한 `x-api-key`이며, 지급 API 사용 가능 소스는
`PAYOUT_SOURCES` 시크릿/환경변수(기본 `liv-ay`)로 별도 제한됩니다.

`/api/billing/*`(토스페이먼츠 결제 승인 프록시 — mentor 구독 청구)도 같은 함수가
서빙합니다. 인증은 동일한 `x-api-key`이며, 청구 API 사용 가능 소스는 `BILLING_SOURCES`
시크릿/환경변수(기본 `mentor`)로 별도 제한됩니다.

## 엔드포인트

베이스 URL: `https://cho-fam.web.app/api/mail` (Hosting rewrite를 통해 Functions로 연결)

| Method | Path | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/send` | `x-api-key` | 메일 발송. Body: `{ to, templateKey, location, dynamicData }` |
| GET | `/logs` | `x-api-key` (admin) | 발송 기록 조회. Query: `source`, `status`, `limit` |
| POST | `/logs/:id/resend` | `x-api-key` (admin) | 실패 건 재전송 |
| GET | `/templates` | `x-api-key` (admin) | 템플릿 목록 조회 |
| GET | `/templates/:key` | `x-api-key` (admin) | 템플릿 단건 조회 |
| POST | `/templates` | `x-api-key` (admin) | 템플릿 생성/수정. Body: `{ key, description, templates }` |
| DELETE | `/templates/:key` | `x-api-key` (admin) | 템플릿 삭제 |

### 청구(결제 승인) — `/api/billing`

| Method | Path | 인증 | 설명 |
| --- | --- | --- | --- |
| POST | `/confirm` | `x-api-key` (`BILLING_SOURCES`) | 결제 승인. Body: `{ paymentKey, orderId, amount }` |

프론트엔드 결제위젯이 만든 `paymentKey`/`orderId`/`amount`를 호출 서비스 **백엔드**가
받아 이 API로 넘기면 토스가 청구를 확정합니다(성공 `{ ok, paymentKey, orderId, status,
totalAmount, currency, approvedAt }`). `amount`는 결제 요청 금액과 정확히 일치해야
하며(불일치 시 `502`), 승인 결과는 `billing_logs`에 기록됩니다. 토스 키(`TOSS_SECRET_KEY`)
미설정 시 `503 billing_not_configured`.

## 설정

1. SMTP 릴레이 준비(AWS SES, SMTP2GO, Brevo 등) 및 릴레이에서 발신 도메인 인증(SPF/DKIM)
2. 서비스별 API 키 발급 (예: liv-ay 게임서버용, 매니저 웹페이지 admin용) — 자세한 절차는 [API_KEYS.md](./API_KEYS.md) 참고
3. 시크릿 등록:
   ```bash
   firebase functions:secrets:set SMTP_HOST
   firebase functions:secrets:set SMTP_USER
   firebase functions:secrets:set SMTP_PASS
   firebase functions:secrets:set MAIL_API_KEYS
   # MAIL_API_KEYS 값 예시: {"<liv-ay-key>":"liv-ay","<admin-key>":"cho-fam-admin"}
   # 포트는 기본 587(STARTTLS) — 변경 시 .env의 SMTP_PORT (465=TLS)
   ```
4. 로컬 개발 시 `functions/.env` 생성 (`.env.example` 참고, git에는 커밋되지 않음)
5. 배포: `firebase deploy --only functions,firestore,hosting`

## 호출 서비스 추가 방법

1. `MAIL_API_KEYS`에 새 키:서비스명 쌍 추가 후 시크릿 재배포
2. 호출 시 헤더 `x-api-key: <발급받은 키>` 사용
3. 관리자 화면에서 해당 서비스 발송 내역을 보려면 `MAIL_ADMIN_SOURCES`에 서비스명 추가

메일 발송 API를 실제로 호출하는 코드 예시(curl/Node.js/Python)는
[SENDING_GUIDE.md](./SENDING_GUIDE.md)를 참고하세요.
