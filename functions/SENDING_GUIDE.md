# 메일 전송 호출 가이드

다른 서비스(게임서버 등)에서 CHOFAM 공용 메일 API를 통해 메일을 보내는 방법입니다.
API 키 발급 절차는 [API_KEYS.md](./API_KEYS.md)를 먼저 참고하세요.

> ⚠️ **반드시 서버(백엔드)에서만 호출하세요.** API 키를 모바일 앱/웹 프론트엔드 코드에
> 직접 넣으면 누구나 키를 추출해 임의로 메일을 보낼 수 있습니다. 클라이언트 앱은 자체
> 백엔드를 거쳐서 메일을 트리거해야 합니다.

## 엔드포인트

```
POST https://chofam-home.web.app/api/mail/send
```

| 헤더 | 값 | 필수 |
| --- | --- | --- |
| `Content-Type` | `application/json` | O |
| `x-api-key` | 발급받은 서비스별 API 키 | O |

### Request Body

```json
{
  "to": "user@example.com",
  "templateId": "d-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "dynamicData": {
    "code": "123456",
    "nickname": "홍길동"
  }
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `to` | string | O | 수신자 이메일 주소 |
| `templateId` | string | O | SendGrid 동적 템플릿 ID (`d-`로 시작) |
| `dynamicData` | object | X | 템플릿에 채워 넣을 변수 (코드, 이름 등) |

### Response

성공 (`200`):
```json
{ "ok": true, "id": "Jk3x...mailLogId", "status": "sent" }
```

실패 (`400` 잘못된 요청 / `401` 키 오류 / `502` SMTP 발송 실패):
```json
{ "ok": false, "error": "to_and_templateId_required" }
```

요청은 성공/실패 여부와 무관하게 `mail_logs`에 기록되며, 실패 건은
`/admin/mail/`(매니저 웹페이지)에서 재전송할 수 있습니다.

## 호출 예시

### curl
```bash
curl -X POST https://chofam-home.web.app/api/mail/send \
  -H "Content-Type: application/json" \
  -H "x-api-key: $MAIL_API_KEY" \
  -d '{
    "to": "user@example.com",
    "templateId": "d-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "dynamicData": { "code": "123456" }
  }'
```

### Node.js (fetch)
```js
async function sendVerificationEmail(to, code) {
  const res = await fetch('https://chofam-home.web.app/api/mail/send', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': process.env.MAIL_API_KEY,
    },
    body: JSON.stringify({
      to,
      templateId: 'd-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx',
      dynamicData: { code },
    }),
  });
  const data = await res.json();
  if (!res.ok || !data.ok) throw new Error(data.error || `mail_send_failed_${res.status}`);
  return data;
}
```

### Python (requests)
```python
import os
import requests

def send_verification_email(to: str, code: str):
    res = requests.post(
        "https://chofam-home.web.app/api/mail/send",
        headers={"x-api-key": os.environ["MAIL_API_KEY"]},
        json={
            "to": to,
            "templateId": "d-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
            "dynamicData": {"code": code},
        },
        timeout=10,
    )
    data = res.json()
    if not res.ok or not data.get("ok"):
        raise RuntimeError(data.get("error", f"mail_send_failed_{res.status_code}"))
    return data
```

## 트리거 위치 예시 (liv-ay)

liv-ay 백엔드의 `/auth/email-verify/send` 처리 흐름에 연결하는 예:

1. 백엔드가 인증 코드를 생성해 자체 DB(또는 Firestore)에 저장
2. 위 예시처럼 `POST /api/mail/send`를 호출해 코드 포함 메일 발송
3. 사용자가 코드 입력 시 백엔드가 저장된 코드와 대조해 검증 완료 처리

정산/성과금 알림처럼 비동기 트리거(Firestore `onWrite`, cron 등)에서도 동일한 호출
방식을 그대로 사용하면 됩니다.

## 주의사항

- **재시도**: 네트워크 오류로 호출 자체가 실패하면 호출 측에서 재시도하세요. SMTP
  발송 실패(`502`)는 이미 `mail_logs`에 `failed`로 기록되므로, 매니저 웹페이지에서
  재전송하거나 `POST /api/mail/logs/:id/resend`(admin 키)로 재시도할 수 있습니다.
- **속도 제한**: 현재 API 자체에는 rate limit이 없습니다. 대량 발송(마케팅성 메일 등)이
  필요하면 사전에 공유해 주세요 — 발신 도메인/릴레이 평판 보호를 위해 큐잉/제한 로직
  추가가 필요할 수 있습니다.
- **템플릿 관리**: `templateId`는 SendGrid 대시보드에서 직접 만들고 ID를 호출 측 코드에
  반영합니다. 템플릿 자체는 이 저장소에서 관리하지 않습니다.
