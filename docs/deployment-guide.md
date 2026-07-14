# 배포 예시 매뉴얼

> 1차(중소규모) 운영 기준 실전 가이드.
> **단계 0**: 서버 0대 — Firebase/Netlify 관리형으로 운영
> **단계 1**: GPU·상시 프로세스가 필요해진 시점 — 자체 PaaS(`platform/`) 투입
> 설계 배경: [cloud-platform-paas-design-review.md](./cloud-platform-paas-design-review.md)

**⚠️ 실행 위치 주의**: 모든 명령 블록 첫 줄에 `# 실행 위치:`를 표기했다.
`npm run build`의 build 스크립트는 이 리포에서는 `platform/console/`에만 있다 —
리포 루트는 package.json이 없고(`ENOENT`), `functions/`는 빌드 단계가 없어서
(`Missing script: "build"`) 다른 위치에서 실행하면 에러가 난다.

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
# 실행 위치: 배포할 React 앱 리포의 루트 (chofam 리포가 아님!)
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
# 실행 위치: 배포할 React 앱 리포의 루트
npm i -g netlify-cli
netlify init                        # 리포 연결 (이후 git push = 자동 배포)
netlify deploy --prod               # 수동 배포가 필요할 때
```

- PR을 올리면 `deploy-preview-<PR번호>--<사이트>.netlify.app` 프리뷰가 자동 생성된다.
- 롤백: Netlify 대시보드 → Deploys → 이전 배포 선택 → "Publish deploy" (재빌드 없음).

### 2.3 Node API → Firebase Functions

`functions/` 패턴 그대로 (Express 라우터 추가 → 배포):

```bash
# 실행 위치: chofam 리포의 functions/
cd functions && npm test
firebase deploy --only functions
# 주의: functions에는 build 스크립트가 없음 — 빌드 단계 자체가 불필요 (배포가 곧 빌드)
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

### 3.1 서버 준비 — Linux (Ubuntu 22.04+, 운영 권장)

```bash
# 실행 위치: 서버 셸 (아무 위치)
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

> macOS는 Colima(무료) 권장·GPU 불가 — [platform/README.md의 "설치 빌드옵션"](../platform/README.md) 참고.
> **Windows는 3.6절**에 별도 절차가 있다.

### 3.2 플랫폼 설치 (환경설정)

```bash
# 실행 위치: 서버 셸 — 이후 모든 명령은 /opt/paas/platform 기준
git clone https://github.com/hs9147/chofam /opt/paas && cd /opt/paas/platform
pip install -r requirements.txt docker
cp .env.example .env
```

`.env` 환경설정 정리 (전체 목록·기본값은 [platform/.env.example](../platform/.env.example)):

| 키 | 필수 | 설명 |
| --- | --- | --- |
| `PAAS_ADMIN_API_KEY` | ✅ | 관리자 키. 비우면 기동마다 임시 키가 로그에 출력됨 — 운영에서는 고정 |
| `PAAS_FERNET_KEY` | ✅ | 환경변수 암호화 키. **분실 시 저장된 시크릿 복호화 불가** — 백업 필수 |
| `PAAS_WEBHOOK_SECRET` | ✅(웹훅 사용 시) | GitHub/Gitea 웹훅 서명 검증 |
| `PAAS_BASE_DOMAIN` | ✅ | 예: `deploy.example.com` — 프로젝트 도메인의 기준 |
| `PAAS_FEATURES` | 선택 | 기본 전체. 메일·결제를 CHO-FAM Functions가 담당하면 `deploy,workspace` |
| `PAAS_TIER` | 선택 | `small`(기본, Docker) / `enterprise`(K8s) |
| `PAAS_HOST_OS` | 선택 | 기본 `auto` 감지. 컨테이너 안 등 감지가 틀릴 때만 명시 |
| `PAAS_DATABASE_URL` | 선택 | 기본 SQLite. 규모 커지면 PostgreSQL DSN |

필수 키 생성 명령:

```bash
# 실행 위치: /opt/paas/platform (venv 활성 상태)
python3 -c "import secrets; print('paas_' + secrets.token_urlsafe(32))"   # PAAS_ADMIN_API_KEY
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # PAAS_FERNET_KEY
openssl rand -hex 32                                                       # PAAS_WEBHOOK_SECRET
```

기동:

```bash
# 실행 위치: /opt/paas/platform
uvicorn app.main:app --host 127.0.0.1 --port 7000   # 운영은 systemd 서비스로

# 콘솔 UI 빌드 — 반드시 platform/console 에서! (build 스크립트는 여기에만 있음)
cd /opt/paas/platform/console && npm install && npm run build
# 이후 https://paas.example.com/console/ 접속
```

### 3.3 프로젝트 등록 → 배포 → 확인 (FastAPI 앱 예시)

```bash
# 실행 위치: 아무 곳이나 — 플랫폼 API 호출이므로 curl만 있으면 됨 (콘솔 UI로도 동일 작업 가능)
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

### 3.6 Windows에서 PaaS 실행

두 가지 방법이 있고, **A(WSL2)를 권장**한다 — GPU 지원·Docker 무료 구성·Linux와 동일 절차라는 세 가지 이점 때문.

#### A. WSL2 안에서 실행 (권장)

```powershell
# 실행 위치: PowerShell (관리자)
wsl --install -d Ubuntu     # 최초 1회, 재부팅 필요
```

이후 **WSL Ubuntu 터미널에서 3.1~3.2절의 Linux 절차를 그대로** 따른다.
Docker는 둘 중 하나:
- Docker Desktop 설치 후 Settings → Resources → WSL Integration에서 Ubuntu 켜기 (기업 규모에 따라 유료)
- 또는 WSL Ubuntu 안에 Docker Engine 직접 설치 (`curl -fsSL https://get.docker.com | sh`, 무료)

GPU: 호스트에 NVIDIA 드라이버만 설치하면 WSL2가 자동 노출한다(별도 드라이버 불필요).
WSL 안에서는 `PAAS_HOST_OS`가 `linux`로 감지되며 GPU 배포가 그대로 동작한다.

#### B. 네이티브 Windows (PowerShell)

Docker Desktop(WSL2 백엔드) 설치가 선행되어야 한다.

```powershell
# 실행 위치: PowerShell
git clone https://github.com/hs9147/chofam C:\paas
cd C:\paas\platform
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt docker
Copy-Item .env.example .env

# 필수 키 생성 (openssl 대신 파이썬으로 통일)
python -c "import secrets; print('paas_' + secrets.token_urlsafe(32))"                      # PAAS_ADMIN_API_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # PAAS_FERNET_KEY
python -c "import secrets; print(secrets.token_hex(32))"                                    # PAAS_WEBHOOK_SECRET

# 기동 (.env 편집 후)
uvicorn app.main:app --host 127.0.0.1 --port 7000
```

```powershell
# 콘솔 UI 빌드 — 반드시 platform\console 에서!
cd C:\paas\platform\console
npm install
npm run build
```

네이티브 실행 시 알아둘 것:

- `PAAS_HOST_OS`는 `windows`로 자동 감지된다. GPU는 Docker Desktop의 WSL2 백엔드를 경유해 지원.
- Caddy: `winget install CaddyServer.Caddy` (또는 scoop/choco) 후 Caddyfile에
  `import C:\paas\platform\data\caddy-sites\*.caddy` 추가. `caddy run --config <Caddyfile>`.
- 서비스 등록(부팅 시 자동 시작): [NSSM](https://nssm.cc)으로 uvicorn·caddy를 Windows 서비스로 등록.
- 한글 등 파일 인코딩은 플랫폼 코드가 UTF-8을 명시해 처리한다 — Windows CI에서 전 테스트 통과 확인됨.
- 팀 규모가 크면 Docker Desktop 라이선스(기업 유료)를 확인할 것 — 부담되면 A(WSL2 + Docker Engine) 방식이 무료.

### 3.7 관리형 자산과 연결 (모듈 바인딩)

자체 PaaS의 앱이 CHO-FAM 메일 API를 쓰게 하려면:

```bash
curl -X POST $BASE/modules -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"chofam-mail","type":"external_api",
       "config":{"url":"https://cho-fam.web.app/api/mail","api_key":"<발급 키>"}}'
curl -X POST $BASE/projects/1/modules/1/bind -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"env_prefix":"MAIL"}'
# 다음 배포부터 MAIL_URL, MAIL_API_KEY 자동 주입 → 코드에서 process.env/os.environ으로 사용
```

### 3.8 사내 Git 서버 (기업용 — GitHub 대체)

소스가 사외 SaaS로 나가면 안 되는 기업용 배포는 GitHub 대신 **사내 Gitea**를 쓴다.
배포 산출물(1차 Docker Compose / 2차 K8s manifests)과 웹훅·SSO 연동 절차는
[`platform/infra/gitea/README.md`](../platform/infra/gitea/README.md)에 정리되어 있다.
플랫폼 코드는 GitHub·Gitea 웹훅 서명을 둘 다 자동 인식하므로(3.4절과 동일 절차),
`git_url`만 사내 Gitea 주소로 바꾸면 이후 흐름은 동일하다.

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
