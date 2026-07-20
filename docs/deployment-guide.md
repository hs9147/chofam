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
| `PAAS_GIT_INTERNAL_ONLY` | 선택 | 기본 `true` — 프로젝트 `git_url`이 사내 Gitea(`PAAS_GITEA_URL`, 3.8절) 호스트가 아니면 등록 자체를 거부한다. 아직 사내 Gitea를 안 붙였고 3.3절처럼 GitHub 등 외부 리포로 우선 테스트하려면 `false`로 낮출 것 |

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

아래는 외부 GitHub 리포를 직접 등록하는 가장 단순한 경로다 — `PAAS_GIT_INTERNAL_ONLY`
기본값(`true`)에서는 사내 Gitea 호스트가 아니면 거부되므로, 사내 Gitea를 아직 3.8절대로
붙이지 않았다면 `.env`에 `PAAS_GIT_INTERNAL_ONLY=false`를 먼저 설정해야 이 예시가 통과한다
(사내 Gitea 준비가 끝났다면 이 값은 다시 켜 두는 것을 권장 — 15절 참고).

```bash
# 실행 위치: 아무 곳이나 — 플랫폼 API 호출이므로 curl만 있으면 됨 (콘솔 UI로도 동일 작업 가능)
# API=$BASE/paas/api/v1 — /health·/status는 버전 없이 $BASE/paas/health처럼 쓴다(고정 경로)
BASE=http://127.0.0.1:7000  API=$BASE/paas/api/v1  ADMIN=paas_...

# 1) 프로젝트 등록
curl -X POST $API/projects -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"shop-api","type":"python","git_url":"https://github.com/org/shop-api",
       "branch":"main","health_check_path":"/healthz"}'

# 2) development 배포 → https://shop-api-dev.deploy.example.com
curl -X POST $API/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"development"}'

# 3) 확인 후 release 배포 → https://shop-api.deploy.example.com
curl -X POST $API/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"release"}'

# 로그 / 상태 / 이력
curl -H "x-api-key: $ADMIN" "$API/projects/1/logs?profile=release&tail=200"
curl -H "x-api-key: $ADMIN" "$API/projects/1/status"

# 문제 시 롤백 (재빌드 없이 직전 성공 이미지로)
curl -X POST "$API/projects/1/rollback?profile=release" -H "x-api-key: $ADMIN"
```

### 3.4 push 자동 배포 (GitHub/Gitea 웹훅)

리포 설정 → Webhooks 추가:

- Payload URL: `https://paas.example.com/paas/webhooks/git`
- Content type: `application/json`
- Secret: `.env`의 `PAAS_WEBHOOK_SECRET` 값

이후 등록된 브랜치로 push하면 프로젝트의 `default_profile`로 자동 배포된다
(서명 불일치는 401 거부, 연속 push는 배포 락으로 1건만 실행).

### 3.5 LLM 서버 배포 (GPU 서버)

```bash
curl -X POST $API/projects -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"llm-main","type":"llm","git_url":"https://github.com/org/llm-main"}'
curl -X POST $API/projects/2/deploy -H "x-api-key: $ADMIN" \
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
curl -X POST $API/modules -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"chofam-mail","type":"external_api",
       "config":{"url":"https://cho-fam.web.app/api/mail","api_key":"<발급 키>"}}'
curl -X POST $API/projects/1/modules/1/bind -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"env_prefix":"MAIL"}'
# 다음 배포부터 MAIL_URL, MAIL_API_KEY 자동 주입 → 코드에서 process.env/os.environ으로 사용
```

### 3.8 사내 Git 서버 (기업용 — GitHub 대체)

소스가 사외 SaaS로 나가면 안 되는 기업용 배포는 GitHub 대신 **사내 Gitea**를 쓴다.
배포 산출물(1차 Docker Compose / 2차 K8s manifests)과 웹훅·SSO 연동 절차는
[`platform/infra/gitea/README.md`](../platform/infra/gitea/README.md)에 정리되어 있다.
플랫폼 코드는 GitHub·Gitea 웹훅 서명을 둘 다 자동 인식하므로(3.4절과 동일 절차),
`git_url`만 사내 Gitea 주소로 바꾸면 이후 흐름은 동일하다.

### 3.9 Kubernetes(2차/기업용)로 전환

`PAAS_TIER=small`(Docker)에서 `PAAS_TIER=enterprise`로 바꾸면 `Runtime` 인터페이스가
`DockerRuntime`에서 `K8sRuntime`으로 교체된다(6.3절 규칙 2) — **플랫폼 자체는 그대로 두고**,
플랫폼이 대신 배포 대상 K8s 클러스터에 매니페스트를 적용하는 방식이다. 플랫폼 프로세스를
클러스터 안에서 돌릴 필요는 없다(선택 사항 — 아래 5단계 참고).

#### 0) 사전 준비 (플랫폼이 설치해주지 않는 것들)

- **K8s 클러스터**: k3s부터 가능(단일 노드로 시작해도 됨), 관리형(EKS/GKE/AKS)도 무방
- **Ingress 컨트롤러**: 기본값은 Traefik(`PAAS_K8S_INGRESS_CLASS=traefik`), ingress-nginx로 바꾸려면
  이 값도 함께 바꿀 것
- **cert-manager + ClusterIssuer**: 기본값은 `letsencrypt`(`PAAS_K8S_CLUSTER_ISSUER`) — 자동 TLS 발급용
- **이미지 레지스트리(중요)**: 플랫폼의 빌드 단계(`services/build.py`)는 배포 서버에서
  `docker build`까지만 하고 **레지스트리로 push하지 않는다**. `PAAS_K8S_REGISTRY`를 설정하면
  매니페스트의 이미지 이름 앞에 그 레지스트리 주소를 붙일 뿐이므로, 클러스터 노드가 실제로
  그 이미지를 pull할 수 있으려면 별도 push 파이프라인(CI에서 build&push, 또는 Harbor 등)을
  직접 연결해야 한다. 단일 노드 k3s로 시작한다면 플랫폼이 빌드하는 호스트를 그 노드와
  동일하게 두고 `PAAS_K8S_REGISTRY`를 비워 로컬 이미지명을 그대로 쓰는 방법이 가장 간단하다.

#### 1) kubernetes 파이썬 패키지 + 클러스터 접근

```bash
# 실행 위치: 플랫폼이 도는 서버 (venv 활성 상태)
pip install kubernetes
```

클러스터 접근은 표준 kubeconfig 탐색 순서를 그대로 따른다(`services/runtime/k8s_runtime.py`):
1. in-cluster 설정(플랫폼을 파드로 돌릴 때 — 서비스어카운트 토큰 자동 사용)
2. 위가 안 되면 `~/.kube/config`(또는 `KUBECONFIG` 환경변수)

플랫폼을 클러스터 밖(기존 1차 서버 등)에서 그대로 돌린다면 그 서버에 kubeconfig 파일만
놓으면 된다 — 가장 간단한 시작 방법.

#### 2) 네임스페이스 준비 (direct-apply 모드는 자동 생성되지 않음)

```bash
kubectl create namespace paas-apps   # PAAS_K8S_NAMESPACE 기본값과 동일하게
```

주의: `namespace_manifests()`(Namespace + 선택적 ResourceQuota/LimitRange)는 **GitOps 모드**
(`PAAS_K8S_GITOPS_REPO` 설정 시)에서만 `_namespace.yaml`로 자동 커밋된다. 클러스터에 직접
apply하는 기본 경로는 네임스페이스가 이미 있다고 가정하므로, 최초 배포 전에 위처럼 수동으로
만들어둬야 한다(안 만들면 첫 배포에서 apply 실패 → 매니페스트 파일 폴백으로 떨어진다).

#### 3) `.env` 설정

```bash
PAAS_TIER=enterprise
PAAS_K8S_NAMESPACE=paas-apps
PAAS_K8S_REGISTRY=                 # 비우면 로컬 이미지명 그대로 사용 (위 0단계 참고)
PAAS_K8S_INGRESS_CLASS=traefik
PAAS_K8S_CLUSTER_ISSUER=letsencrypt
# 선택 — 멀티테넌시 격리(유닛별 NetworkPolicy, 갭6)
PAAS_K8S_ISOLATION=false
PAAS_K8S_INGRESS_NAMESPACE=traefik
# 선택 — 네임스페이스 ResourceQuota/LimitRange (GitOps 모드에서만 자동 적용됨, 위 참고)
PAAS_K8S_QUOTA_CPU=
PAAS_K8S_QUOTA_MEMORY=
# 선택 — GitOps(ArgoCD) 연계: 설정하면 클러스터에 직접 apply하지 않고 이 리포에 매니페스트 커밋·푸시
PAAS_K8S_GITOPS_REPO=
PAAS_K8S_GITOPS_BRANCH=main
PAAS_K8S_GITOPS_PATH=apps
```

재기동 후 확인:

```bash
curl -s $BASE/paas/health -H "x-api-key: $ADMIN"   # "tier":"enterprise" 확인
```

#### 4) 첫 배포로 검증

```bash
curl -X POST $API/projects -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"shop-api","type":"python","git_url":"https://github.com/org/shop-api"}'
curl -X POST $API/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"release"}'

# 확인
kubectl -n paas-apps get deploy,svc,ingress
curl -s $API/projects/1/status -H "x-api-key: $ADMIN"
```

클러스터 접근이 안 되거나 `kubernetes` 패키지가 없으면 조용히 실패하지 않고
`PAAS_K8S_MANIFEST_DIR`(기본 `./data/k8s-manifests`)에 매니페스트 YAML을 대신 써서
`kubectl apply -f`로 수동 적용하거나 GitOps로 연계할 수 있게 한다. 반대로 **클러스터에
연결된 상태에서 apply 자체가 실패**하면(RBAC 부족, 리소스 충돌 등) 조용히 넘어가지 않고
3회 재시도 후 `K8sApplyError`로 표면화된다(갭4) — 배포가 "성공"으로 오인되지 않도록.

#### 5) (선택) 플랫폼을 클러스터 안에서 파드로 돌릴 때 — RBAC

플랫폼을 클러스터 밖 서버에서 kubeconfig로 접근하는 대신 클러스터 안 파드로 돌리고
싶다면, 아래처럼 네임스페이스 범위의 최소 권한 ServiceAccount를 만든다
(`k8s_runtime.py`가 실제로 건드리는 리소스만 포함):

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: paas-controller
  namespace: paas-apps
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: paas-controller
  namespace: paas-apps
rules:
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/scale"]
    verbs: ["get", "list", "create", "update", "patch"]
  - apiGroups: [""]
    resources: ["services", "secrets"]
    verbs: ["get", "list", "create", "update", "patch"]
  - apiGroups: [""]
    resources: ["pods", "pods/log"]
    verbs: ["get", "list"]
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: paas-controller
  namespace: paas-apps
subjects:
  - kind: ServiceAccount
    name: paas-controller
    namespace: paas-apps
roleRef:
  kind: Role
  name: paas-controller
  apiGroup: rbac.authorization.k8s.io
```

이 ServiceAccount를 플랫폼 파드의 `spec.serviceAccountName`에 지정하면
`config.load_incluster_config()`가 자동으로 이 권한을 사용한다. 이 리포에는 플랫폼
자체의 K8s 배포 매니페스트가 포함돼 있지 않다 — 위 RBAC 예시와 함께 운영 리포에
Deployment/Service를 직접 작성해 관리할 것(사내 Gitea 인프라와 동일한 패턴,
`platform/infra/gitea/k8s/` 참고).

### 3.10 복합(백엔드+프론트엔드) 프로젝트 배포

한 리포에 백엔드 API와 프론트엔드가 함께 있는 모노레포는 `type: composite`로 등록하면
플랫폼이 두 컴포넌트를 자동 감지해 따로 빌드·배포하고 한 도메인으로 묶어준다.

**리포 구조 요구사항**: 루트에 `backend/`, `frontend/` 서브폴더가 반드시 둘 다 있어야
한다(하나만 있으면 일반 프로젝트로 취급돼 잘못된 결과가 난다). 각 서브폴더의 타입은
시그니처 파일로 자동 추론한다 — `requirements.txt`/`pyproject.toml` → python,
`package.json`에 `react` 의존성 → react, `package.json`만 있으면 → node, `index.html`만
있으면 → html. 둘 중 아무것도 없으면 배포가 명확한 에러로 실패한다(추측 배포 금지).
서브폴더 안에 자체 `Dockerfile`이 있으면 그걸 우선 쓴다(루트 Dockerfile 우선 규칙과 동일).

```bash
BASE=http://127.0.0.1:7000  API=$BASE/paas/api/v1  ADMIN=paas_...

# 조직 소속으로 등록(레거시 git_url 직접 지정 경로도 가능 — 3.3절과 동일)
curl -X POST $API/projects -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"shop-app","type":"composite","organization_id":1}'

curl -X POST $API/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"release"}'
```

배포되면 `https://shop-app.deploy.example.com/api/*`는 backend로, 나머지 전체
(`/*`)는 frontend로 자동 라우팅된다(Caddy `handle_path` / IIS URL Rewrite 조건부 규칙 /
Apache `ProxyPass` 접두사 — 3.1절에서 고른 프록시 백엔드와 무관하게 동일하게 동작).
매칭된 접두사(`/api`)는 백엔드로 전달되기 전에 제거된다 — 백엔드는 `/api/users`가 아니라
`/users`로 라우트를 짜면 된다.

**원자적 배포**: backend/frontend 둘 중 하나만 빌드·기동에 실패하면, 실패한 컴포넌트만
재빌드 없이 직전 정상 이미지로 복구한 뒤에야 프록시를 갱신한다 — 성공한 쪽만 새 버전이
되고 실패한 쪽은 이전 버전 그대로 남아, 부분 실패가 다운타임으로 이어지지 않는다. 되돌릴
이전 버전이 아예 없는 첫 배포에서 실패하면(예: 신규 프로젝트) 전체가 실패로 기록되고
프록시는 아예 건드리지 않는다. `GET /paas/api/v1/server-config`·콘솔 "서버구성" 토폴로지
다이어그램에서 컴포넌트별 상태를 개별 확인할 수 있다.

`POST /paas/api/v1/projects/1/rollback`도 컴포넌트 단위가 아니라 backend/frontend가 **한 쌍으로
갖춰진** 직전 배포로 함께 되돌아간다(재빌드 없음).

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
