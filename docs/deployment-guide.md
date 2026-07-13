# 배포 예시 매뉴얼

> 1차(중소규모) 운영 기준 실전 가이드.
> **단계 0**: 서버 0대 — Firebase/Netlify 관리형으로 운영
> **단계 1**: GPU·상시 프로세스가 필요해진 시점 — 자체 PaaS(`platform/`) 투입
> 설계 배경: [cloud-platform-paas-design-review.md](./cloud-platform-paas-design-review.md)

---

## 1. 어느 경로로 배포할지 결정

| 워크로드 | 배포 경로 |
| --- | --- |
| React 정적 앱 | 단계 0 — Firebase Hosting 또는 Netlify |
| Node API (가벼운 요청/응답) | 단계 0 — Firebase Functions |
| 메일 발송·토스 결제/지급 | 단계 0 — CHO-FAM Functions API (이미 운영 중) |
| Python(FastAPI) 상시 서버 | 단계 1 — 자체 PaaS |
| LLM (vLLM/Ollama, GPU) | 단계 1 — 자체 PaaS |
| 게임서버 등 상시 프로세스·WebSocket | 단계 1 — 자체 PaaS |

---

## 2. 단계 0 — 관리형 배포

### 2.1 React 앱 → Firebase Hosting (현재 CHO-FAM 방식)

```bash
npm run build                          # 산출물: dist/ 또는 build/
firebase deploy --only hosting         # 운영 배포

# 검토용 프리뷰 채널 (7일 뒤 자동 만료)
firebase hosting:channel:deploy pr-42 --expires 7d
# → https://cho-fam--pr-42-xxxx.web.app
```

`firebase.json`의 rewrite로 `/api/**`는 Functions로 연결된다(현행 유지).

### 2.2 React 앱 → Netlify

리포 루트에 `netlify.toml`:

```toml
[build]
  command = "npm run build"
  publish = "dist"

[context.deploy-preview]            # PR마다 자동 프리뷰 URL
  command = "npm run build"
```

```bash
npm i -g netlify-cli
netlify init                        # 리포 연결 (이후 git push = 자동 배포)
netlify deploy --prod               # 수동 배포가 필요할 때
```

- PR을 올리면 `deploy-preview-<PR번호>--<사이트>.netlify.app` 프리뷰가 자동 생성된다.
- 롤백: Netlify 대시보드 → Deploys → 이전 배포 선택 → "Publish deploy" (재빌드 없음).

### 2.3 Node API → Firebase Functions

`functions/` 패턴 그대로 (Express 라우터 추가 → 배포):

```bash
cd functions && npm test
firebase deploy --only functions
```

### 2.4 메일·결제 — CHO-FAM API 호출 (재구현 금지)

```bash
# 메일 발송
curl -X POST https://cho-fam.web.app/api/mail/send \
  -H "x-api-key: $SERVICE_KEY" -H "content-type: application/json" \
  -d '{"to":"user@example.com","templateId":"d-xxx","dynamicData":{...}}'

# 토스 지급대행 (셀러 등록 → 지급 요청)
curl -X POST https://cho-fam.web.app/api/payout/request \
  -H "x-api-key: $SERVICE_KEY" -H "content-type: application/json" \
  -d '{"refPayoutId":"p-1","sellerId":"...","amount":10000}'
```

새 호출 서비스 추가 절차는 [functions/README.md](../functions/README.md) 참고
(`MAIL_API_KEYS`에 키 추가 → 시크릿 재배포).

---

## 3. 단계 1 — 자체 PaaS 배포

### 3.1 서버 준비 (Ubuntu 22.04+ 기준)

```bash
# Docker Engine
curl -fsSL https://get.docker.com | sh

# Caddy (도메인·SSL 자동)
sudo apt install -y caddy
# /etc/caddy/Caddyfile 에 한 줄 추가:
#   import /opt/paas/platform/data/caddy-sites/*.caddy

# GPU 서버라면 (llm 프로젝트용)
# NVIDIA 드라이버 + nvidia-container-toolkit 설치
```

DNS: 와일드카드 A 레코드 `*.deploy.example.com → 서버 IP` 하나면 프로젝트별 도메인이 자동 해결된다.

> macOS/Windows에서 돌릴 때의 차이(GPU 불가, Colima/WSL2 권장)는
> [platform/README.md의 "설치 빌드옵션"](../platform/README.md) 참고.

### 3.2 플랫폼 설치

```bash
git clone https://github.com/hs9147/chofam /opt/paas && cd /opt/paas/platform
pip install -r requirements.txt docker
cp .env.example .env
```

`.env` 필수값 생성:

```bash
# 관리자 키 / Fernet 키 / 웹훅 시크릿
python3 -c "import secrets; print('paas_' + secrets.token_urlsafe(32))"   # PAAS_ADMIN_API_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # PAAS_FERNET_KEY
openssl rand -hex 32                                                       # PAAS_WEBHOOK_SECRET
```

메일·결제는 CHO-FAM Functions가 담당하므로 **모듈을 끄고** 기동:

```bash
# .env: PAAS_FEATURES=deploy,workspace  /  PAAS_BASE_DOMAIN=deploy.example.com
uvicorn app.main:app --host 127.0.0.1 --port 7000   # 운영은 systemd 서비스로

# 콘솔 UI까지 쓰려면
cd console && npm install && npm run build   # 이후 https://.../console/ 접속
```

### 3.3 프로젝트 등록 → 배포 → 확인 (FastAPI 앱 예시)

```bash
BASE=http://127.0.0.1:7000  ADMIN=paas_...

# 1) 프로젝트 등록
curl -X POST $BASE/projects -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"shop-api","type":"python","git_url":"https://github.com/org/shop-api",
       "branch":"main","health_check_path":"/healthz"}'

# 2) development 배포 → https://shop-api-dev.deploy.example.com
curl -X POST $BASE/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"development"}'

# 3) 확인 후 release 배포 → https://shop-api.deploy.example.com
curl -X POST $BASE/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"release"}'

# 로그 / 상태 / 이력
curl -H "x-api-key: $ADMIN" "$BASE/projects/1/logs?profile=release&tail=200"
curl -H "x-api-key: $ADMIN" "$BASE/projects/1/status"

# 문제 시 롤백 (재빌드 없이 직전 성공 이미지로)
curl -X POST "$BASE/projects/1/rollback?profile=release" -H "x-api-key: $ADMIN"
```

### 3.4 push 자동 배포 (GitHub/Gitea 웹훅)

리포 설정 → Webhooks 추가:

- Payload URL: `https://paas.example.com/webhooks/git`
- Content type: `application/json`
- Secret: `.env`의 `PAAS_WEBHOOK_SECRET` 값

이후 등록된 브랜치로 push하면 프로젝트의 `default_profile`로 자동 배포된다
(서명 불일치는 401 거부, 연속 push는 배포 락으로 1건만 실행).

### 3.5 LLM 서버 배포 (GPU 서버)

```bash
curl -X POST $BASE/projects -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"llm-main","type":"llm","git_url":"https://github.com/org/llm-main"}'
curl -X POST $BASE/projects/2/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"release"}'
# development 프로필은 --enforce-eager·VRAM 50%로 기동이 빨라 모델 검증용으로 적합
```

배포된 LLM은 OpenAI 호환 엔드포인트가 되며, 콘솔 → LLM 프로바이더에
`base_url: project://llm-main`으로 등록하면 코드 워크스페이스(채팅·리뷰)가 내부 LLM으로 동작한다.

### 3.6 관리형 자산과 연결 (모듈 바인딩)

자체 PaaS의 앱이 CHO-FAM 메일 API를 쓰게 하려면:

```bash
curl -X POST $BASE/modules -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"chofam-mail","type":"external_api",
       "config":{"url":"https://cho-fam.web.app/api/mail","api_key":"<발급 키>"}}'
curl -X POST $BASE/projects/1/modules/1/bind -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"env_prefix":"MAIL"}'
# 다음 배포부터 MAIL_URL, MAIL_API_KEY 자동 주입 → 코드에서 process.env/os.environ으로 사용
```

---

## 4. 종합 예시 — 하이브리드 구성 한 장

```
shop-front (React)  → Netlify            (git push → 자동 배포 + PR 프리뷰)
shop-api  (FastAPI) → 자체 PaaS release  → https://shop-api.deploy.example.com
llm-main  (vLLM)    → 자체 PaaS GPU      → project://llm-main (내부 전용)
메일/결제            → CHO-FAM Functions  (shop-api에는 MAIL_* 모듈 주입)
```

- shop-front의 API 주소는 Netlify 환경변수로 `https://shop-api.deploy.example.com` 지정
- 자체 서버는 GPU·상시 프로세스만 담당 → 서버 1대로 시작 가능

---

## 5. 트러블슈팅

| 증상 | 원인/조치 |
| --- | --- |
| 배포 API가 409 | 같은 프로젝트 배포가 진행 중 — 완료 후 재시도 (웹훅 연속 push는 자동 스킵) |
| `GPU 컨테이너를 지원하지 않습니다` | macOS 등 GPU 미지원 OS — GPU 서버에서 배포하거나 `PAAS_FORCE_GPU=true` |
| `health check failed` 후 배포 실패 | 앱이 `health_check_path`(기본 `/`)에 60초 내 응답해야 함 — 경로/포트 확인, 배포 이력의 build_log 확인 |
| 도메인 접속 불가 | 와일드카드 DNS 전파 확인 → Caddyfile `import` 라인 확인 → `caddy reload` |
| 웹훅이 401 | 리포 웹훅 Secret과 `PAAS_WEBHOOK_SECRET` 불일치 |
| 콘솔 로그인 실패 | admin 키는 200, 일반 키는 403이 정상 프로브 — 401이면 키 자체가 잘못됨 |
