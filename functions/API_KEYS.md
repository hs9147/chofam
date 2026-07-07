# 메일 API 키 발급 가이드

`CHO-FAM` Functions(`/api/mail/*`)를 호출하는 각 서비스(게임서버, 매니저 웹페이지 등)는
고유한 API 키를 발급받아 `x-api-key` 헤더로 인증합니다. 키 자체는 Firebase Secret
(`MAIL_API_KEYS`)에 JSON 맵 형태로 저장되며, 코드나 git에는 절대 커밋하지 않습니다.

## 1. 키 생성

랜덤한 고엔트로피 문자열을 생성합니다. 터미널에서:

```bash
openssl rand -hex 32
# 예: 7f3a1c9e4b2d8f6a0c5e9b3d7f1a2c4e6b8d0f2a4c6e8b0d2f4a6c8e0b2d4f6a
```

서비스별로 구분이 쉽도록 접두사를 붙여 관리하는 것을 권장합니다 (접두사는 임의 표기일 뿐,
실제 인증은 키 문자열 전체로 합니다):

```
liv-ay     -> sk_liv_ay_7f3a1c9e4b2d8f6a0c5e9b3d7f1a2c4e
CHO-FAM-admin -> sk_admin_2b6e0a4c8f1d5b9e3a7c1f5b9d3a7e1c
```

## 2. `MAIL_API_KEYS` 시크릿에 등록

`MAIL_API_KEYS`는 **키 → 서비스명(source)** 매핑 JSON입니다.

```bash
firebase functions:secrets:set MAIL_API_KEYS
```

프롬프트가 뜨면 아래와 같은 JSON 한 줄을 입력합니다 (이미 발급된 키는 유지하고 추가만 합니다):

```json
{"sk_liv_ay_7f3a1c9e4b2d8f6a0c5e9b3d7f1a2c4e":"liv-ay","sk_admin_2b6e0a4c8f1d5b9e3a7c1f5b9d3a7e1c":"CHO-FAM-admin"}
```

- `source` 값(`liv-ay`, `CHO-FAM-admin` 등)은 `mail_logs`에 그대로 기록되어, 매니저
  웹페이지(`/admin/mail/`)에서 서비스별 필터로 사용됩니다.
- 관리자(로그 조회/재전송) 권한이 필요한 서비스는 `MAIL_ADMIN_SOURCES`에도 해당
  `source` 이름을 추가해야 합니다 (기본값: `CHO-FAM-admin`).

```bash
firebase functions:secrets:set MAIL_ADMIN_SOURCES
# 입력 예: CHO-FAM-admin,liv-ay-ops
```

## 3. 배포

시크릿을 갱신한 뒤에는 Functions를 다시 배포해야 적용됩니다.

```bash
firebase deploy --only functions
```

## 4. 로컬 개발용 키

로컬 에뮬레이터에서는 `functions/.env`(git에 커밋되지 않음, `.env.example` 참고)에 같은
형식으로 작성합니다.

```bash
cp functions/.env.example functions/.env
# functions/.env 편집 후
firebase emulators:start --only functions
```

## 5. 호출 서비스 측 사용법

발급받은 키를 해당 서비스의 비밀 설정(환경변수, Secret Manager 등)에 저장하고, 메일
발송 시 헤더로 전달합니다.

```bash
curl -X POST https://CHO-FAM.web.app/api/mail/send \
  -H "x-api-key: sk_liv_ay_7f3a1c9e4b2d8f6a0c5e9b3d7f1a2c4e" \
  -H "Content-Type: application/json" \
  -d '{"to":"user@example.com","templateId":"d-xxxxxxxx","dynamicData":{"code":"123456"}}'
```

## 6. 키 폐기/교체

특정 서비스의 키가 유출되었거나 교체가 필요하면:

1. 새 키를 생성해 `MAIL_API_KEYS`에 추가
2. 호출 서비스 측 설정을 새 키로 교체 및 재배포
3. 전환이 끝나면 `MAIL_API_KEYS`에서 기존 키 항목을 제거하고 다시 `firebase deploy --only functions`

키를 즉시 무효화해야 하는 긴급 상황이면, 교체 전이라도 바로 항목을 제거하고 배포하면
해당 키는 즉시 `401 invalid_api_key`로 거부됩니다.
