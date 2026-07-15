# chofam cloud platform (내부 PaaS)

React · Python · Node · LLM 앱을 배포·운영하는 자체 Deploy Server.
설계 배경과 검토 내용은 [docs/cloud-platform-paas-design-review.md](../docs/cloud-platform-paas-design-review.md) 참고.

## 두 가지 티어 (동일 컨트롤 플레인, 실행 계층만 교체)

| | 1차 — 중소규모 (`PAAS_TIER=small`) | 2차 — 대기업 규모 (`PAAS_TIER=enterprise`) |
| --- | --- | --- |
| 런타임 | Docker Engine (블루-그린 교체 + 헬스체크) | Kubernetes (Deployment/Service/Ingress 생성) |
| 도메인·SSL | Caddy 사이트 파일 + 무중단 reload | Ingress + cert-manager |
| 무중단 배포 | 새 컨테이너 기동 → 헬스체크 → Caddy 전환 → 구 컨테이너 제거 | RollingUpdate(maxUnavailable 0) |
| replicas | 항상 1 | release 2 / development 1 |
| 클러스터 미접근 시 | — | 매니페스트를 `data/k8s-manifests/`에 출력 (kubectl apply / GitOps 연계) |

런타임은 `Runtime` 인터페이스(`app/services/runtime/base.py`)로 추상화되어 있어
`DockerRuntime` ↔ `K8sRuntime` 교체가 설정 한 줄입니다.

## 빌드 옵션: development / release

배포 시 `profile`로 지정합니다. 생략하면 프로젝트의 `default_profile`(기본 release).

| 효과 | development | release |
| --- | --- | --- |
| 실행 방식 | dev 서버 (Vite HMR, uvicorn `--reload`) | 프로덕션 빌드 (minify, 멀티스테이지, non-root) |
| 이미지 태그 | `{name}:{sha}-dev` | `{name}:{sha}` |
| 환경변수 | `APP_ENV/NODE_ENV=development` | `production` |
| 도메인 | `{name}-dev.{base_domain}` | 지정 도메인 또는 `{name}.{base_domain}` |
| 리소스 | release의 50% | 100% |
| replicas (k8s) | 1, Recreate | 2, RollingUpdate |
| LLM(vLLM) | `--enforce-eager`, VRAM 50% | VRAM 90% |

dev와 release는 별도 유닛(`paas-{name}-dev` / `paas-{name}`)으로 **동시 기동**되므로
개발 확인용 배포가 운영 트래픽에 영향을 주지 않습니다.

Dockerfile 결정 규칙: 리포에 `Dockerfile`이 있으면 우선 사용(`--build-arg APP_PROFILE` 전달),
없으면 `templates/dockerfiles/{type}.{profile}.Dockerfile` 템플릿 사용.

## 설치 빌드옵션

설치본마다 **기능 모듈**과 **운영환경(OS)** 두 축을 조합해 구성합니다.

### 기능 모듈 (`PAAS_FEATURES`, 기본 전체)

| 모듈 | 내용 | 필요 설정 |
| --- | --- | --- |
| core (항상) | 프로젝트·환경변수·API 키·감사 로그·Module 레지스트리·/status | — |
| `deploy` | 배포·롤백·로그·웹훅 자동 배포·프리뷰 | Docker 또는 K8s |
| `workspace` | LLM 코드 워크스페이스 (프로바이더·채팅·diff 승인·리뷰) | LLM 프로바이더 |
| `mail` | 관리자 알림 — CHO-FAM 메일 API 연동 (배포 실패 시 발송) | `PAAS_MAIL_API_URL`, `PAAS_MAIL_API_KEY`, `PAAS_MAIL_ALERT_TO`, `PAAS_MAIL_TEMPLATE_ID` |
| `payment` | 토스페이먼츠 **결제 수납**(승인·취소·조회 + 기록). 지급대행(payout)은 CHO-FAM functions(`/api/payout`)에 별도 존재 | `PAAS_TOSS_SECRET_KEY` |

```bash
PAAS_FEATURES=deploy                          # 배포 전용 서버
PAAS_FEATURES=deploy,mail                     # 배포 + 장애 메일 알림
PAAS_FEATURES=deploy,workspace,mail,payment   # 전체 (기본)
```

비활성 모듈의 엔드포인트는 404로 감춰지고, 콘솔 메뉴도 `/health`의 features에 맞춰 숨겨집니다.

### 운영환경 OS (`PAAS_HOST_OS=auto`, 자동 감지)

| OS | 컨테이너 런타임 | GPU | 비고 |
| --- | --- | --- | --- |
| **Linux (운영 권장)** | Docker Engine (Apache 2.0, 무료) | NVIDIA Container Toolkit | 전 기능 |
| macOS | Colima(무료) 권장, Docker Desktop은 기업 유료 주의 | ❌ 미지원 — LLM은 CPU(Ollama) 또는 원격 GPU | 개발·데모용 |
| Windows | Docker Desktop + WSL2 | WSL2 백엔드 경유 | **가능하면 WSL2 안에서 Linux 모드 운영 권장** |

- GPU 미지원 OS에서 llm 프로젝트를 배포하면 GPU 없이 기동하고, GPU를 명시 요구하면
  한국어 에러로 조기 실패합니다 (`PAAS_FORCE_GPU=true`로 강제 가능).
- 감지가 틀리는 환경(컨테이너 등)은 `PAAS_HOST_OS=linux`처럼 명시하세요.
- CI가 3-OS 매트릭스(ubuntu·macos·windows)로 전체 테스트를 돌립니다
  (`.github/workflows/platform-ci.yml`).

## 실행

```bash
cd platform
pip install -r requirements.txt
pip install docker            # 1차(small) 런타임
# pip install kubernetes      # 2차(enterprise)에서 직접 apply할 때
cp .env.example .env          # 값 채우기
uvicorn app.main:app --port 7000
```

Caddy는 메인 Caddyfile에 `import ./data/caddy-sites/*.caddy` 한 줄만 추가하면 됩니다.

## API 요약 (인증: `x-api-key` 헤더)

```
GET  /health                          # 인증 불필요
GET  /status                          # CPU/메모리/디스크/GPU (admin)
POST /keys                            # API 키 발급 (admin)
GET  /audit                           # 감사 로그 (admin)

POST /orgs                            # {name} → 사내 Gitea에 동명 Organization 생성 (admin)
GET  /orgs                            # 조직 목록 + 프로젝트 수

GET  /projects                        # git_url은 organization_id 소속이면 비관리자에게 마스킹
POST /projects                        # {name, type, branch, domain?, ...}
                                      #   + organization_id(내부 리포 자동 생성) 또는 git_url(직접 지정) 중 하나
POST /projects/{id}/deploy            # {profile?: development|release, git_sha?}
POST /projects/{id}/rollback?profile=release
POST /projects/{id}/stop?profile=development
GET  /projects/{id}/deployments
GET  /projects/{id}/logs?profile=release&tail=200
GET  /projects/{id}/status
PUT  /projects/{id}/env               # {key, value, is_secret} — Fernet 암호화 저장
GET  /projects/{id}/env               # 시크릿 값은 마스킹

POST /webhooks/git                    # GitHub/Gitea push → default_profile로 자동 배포
                                      # HMAC 서명(X-Hub-Signature-256 / X-Gitea-Signature) 필수
```

## 배포 흐름 예시

```bash
ADMIN=... BASE=http://localhost:7000

# 프로젝트 등록
curl -X POST $BASE/projects -H "x-api-key: $ADMIN" -H 'content-type: application/json' \
  -d '{"name":"shop-front","type":"react","git_url":"https://git.example.com/org/shop-front"}'

# development 배포 → shop-front-dev.{base_domain}
curl -X POST $BASE/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"development"}'

# release 배포 → shop-front.{base_domain}
curl -X POST $BASE/projects/1/deploy -H "x-api-key: $ADMIN" \
  -H 'content-type: application/json' -d '{"profile":"release"}'

# 롤백 (재빌드 없이 직전 성공 이미지로)
curl -X POST "$BASE/projects/1/rollback?profile=release" -H "x-api-key: $ADMIN"
```

## 코드 워크스페이스 (설계 문서 12절)

```
POST /llm/providers                     # 외부(Claude/OpenAI) 또는 내부(project://<llm 프로젝트>) 등록 (admin)
GET  /llm/providers                     # api_key는 has_api_key로만 노출
POST /chat/sessions                     # {project_id, provider_id, branch?} — 기본 브랜치 paas/chat-{id}
POST /chat/sessions/{id}/messages       # 파일 트리·모듈 규약·요청 파일을 컨텍스트로 LLM 호출
                                        # 응답에 diff가 있으면 ProposedChange 자동 생성
POST /changes/{id}/apply                # 승인 → 작업 브랜치에 git apply + commit (LLM 직접 쓰기 없음)
POST /changes/{id}/reject
POST /projects/{id}/review              # {provider_id, diff? , base_ref?} → 심각도 분류 findings

POST /modules                           # external_api | internal_api | database | file_storage
                                        # config의 api_key/dsn/secret 등은 Fernet 암호화 저장
POST /projects/{id}/modules/{mid}/bind  # {env_prefix: "PAY"} → 배포 시 PAY_URL 등 자동 주입
GET  /projects/{id}/modules             # LLM 컨텍스트용 요약 (비밀값 제외)

POST /projects/{id}/preview             # {branch?, ttl_minutes=60} → {name}-pv{n}.{base_domain}
GET  /projects/{id}/previews            # 조회 시 만료 프리뷰 자동 회수
DELETE /previews/{id}
```

- 내부 LLM 프로바이더(`project://llm-main`)를 쓰면 소스가 사내망을 벗어나지 않습니다.
- internal_api 모듈의 URL은 티어에 따라 자동 해석됩니다
  (small: `https://{target}.{base_domain}`, enterprise: `http://paas-{target}.{ns}.svc`).
- 프리뷰는 development 프로필 빌드를 재사용하되 CPU 50%·GPU 금지·동시 5개 제한·TTL 회수가 걸립니다.

## 콘솔 UI (`console/`)

React + Vite 관리 대시보드. 빌드 산출물(`console/dist`)이 있으면 FastAPI가 `/console`에 자동
마운트합니다(없어도 API는 동일 기동).

```bash
cd platform/console
npm install
npm run build        # tsc 타입체크 + vite build → dist/
# 개발 모드: npm run dev (http://localhost:5173/console/, API는 :7000으로 프록시)
```

- 접속: `http://<서버>:7000/console/` → API 키로 로그인
  (admin 키: 대시보드·감사 로그·키 발급·프로바이더 등록 포함, 일반 키: 프로젝트 운영 화면)
- 화면: 시스템 대시보드(CPU/메모리/디스크/GPU 게이지, 키 발급), 프로젝트(생성·dev/release
  배포·롤백·중지·배포 이력·로그 3초 폴링·환경변수·모듈 바인딩·프리뷰), 모듈 레지스트리,
  LLM 프로바이더, 대화식 코드 편집(diff 뷰 + 승인/거절 + 브랜치 리뷰), 감사 로그
- 인증은 `x-api-key`를 sessionStorage에 보관(기존 admin/mail 관례). 로그인 검증은 admin 전용
  `GET /status` 응답 코드(200 admin / 403 일반 / 401 무효)를 프로브로 재사용
- 의존성: react·react-dom·react-router-dom (전부 MIT). 라우팅은 해시 기반이라 새로고침·딥링크에
  백엔드 폴백이 필요 없습니다

## 기업용 옵션 (14.2절 갭 구현)

- **사내 Git 서버(Gitea)**: GitHub 대신 소스가 사외로 나가지 않는 self-host Git 서버 배포.
  Docker Compose(1차)/K8s manifests(2차) + 웹훅·Keycloak SSO 연동은
  [`infra/gitea/README.md`](infra/gitea/README.md) 참고. `PAAS_GITEA_URL`을 설정하면
  콘솔 상단 메뉴에 **Git** 탭이 나타나 등록된 프로젝트별 리포 바로가기를 보여준다.
- **코드 내부 관리 강제**: `PAAS_GIT_INTERNAL_ONLY=true` + `PAAS_GITEA_URL` 설정 시
  프로젝트 등록 단계에서 `git_url` 호스트가 사내 Gitea와 다르면 422로 거부(github.com 등
  외부 호스트 등록 원천 차단). internal LLM 프로바이더 강제(12절)와 동일한 원칙.
- **조직별 작업공간**: 콘솔의 조직 페이지(admin)에서 조직을 만들면 사내 Gitea에 동일한
  이름의 Organization이 함께 생성된다(`PAAS_GITEA_API_TOKEN` 필요). 조직 소속 프로젝트는
  리포를 플랫폼이 내부에서 자동 생성·관리하며, git_url 등 메타 정보는 **일반 사용자
  응답에서 마스킹**된다(admin만 실제 값 조회 가능) — `POST /orgs`, `GET /orgs`,
  `POST /projects`의 `organization_id` 참고.
- **OIDC/RBAC (Keycloak 호환)**: `PAAS_OIDC_ISSUER` 설정 시 `Authorization: Bearer <JWT>`
  인증 병행. `realm_access.roles`에 `PAAS_OIDC_ADMIN_ROLE`(기본 paas-admin)이 있으면 admin.
- **비동기 배포**: `POST /projects/{id}/deploy`에 `"wait": false` → 202 즉시 반환,
  `GET /projects/{id}/deployments`로 진행 폴링. 워커 수는 `PAAS_DEPLOY_WORKERS`(기본 2).
- **OpenBao 시크릿**: `PAAS_OPENBAO_URL/TOKEN/KEY_PATH` 설정 시 Fernet 키를 KV v2에서 로드.
- **멀티테넌시 격리**: `PAAS_K8S_ISOLATION=true` → 유닛별 NetworkPolicy
  (ingress 컨트롤러 네임스페이스는 `PAAS_K8S_INGRESS_NAMESPACE`).
- **외부 호출 재시도 + 서킷브레이커**: 토스·메일 호출은 네트워크 오류에 한해 3회 백오프
  재시도(HTTP 오류 응답은 재시도하지 않음 — 결제 중복 방지). 호스트별 연속 5회 실패 시
  60초 차단 후 half-open 복구.
- **GitOps(ArgoCD)**: `PAAS_K8S_GITOPS_REPO` 설정 시 직접 apply 대신 매니페스트를
  해당 리포에 커밋·푸시 (`PAAS_K8S_GITOPS_BRANCH`/`_PATH`). ArgoCD가 sync 담당.
- **키 회전**: 새 키를 `PAAS_FERNET_KEY`로, 기존 키를 `PAAS_FERNET_KEYS_OLD`로 옮겨
  재기동 → `POST /admin/rotate-secrets`(admin) → 완료 후 구 키 제거.
- **네임스페이스 Quota**: `PAAS_K8S_QUOTA_CPU`/`_MEMORY` 설정 시 ResourceQuota +
  기본 LimitRange 매니페스트 생성.

## 플랫폼 내 Git 구현

플랫폼은 **자체 리포(chofam)와는 무관하게**, 배포 대상 프로젝트마다 독립된 로컬 git 체크아웃을
`work_dir`(기본 `./data/workspaces/{project}`) 아래 두고 조작한다. 전부 `subprocess`로 시스템 git을
호출하며(플랫폼 자체 git 라이브러리 없음), 외부로 나가는 지점은 웹훅 수신과 GitOps 푸시 둘뿐이다.

| 컴포넌트 | 파일 | 동작 |
| --- | --- | --- |
| **배포 체크아웃** | `services/build.py` `checkout()` | 최초엔 `git clone --branch`, 이후는 `fetch`+`reset --hard`로 매 배포마다 최신화. `git_sha` 지정 시 해당 커밋으로 `checkout`. **읽기 전용** — 이 리포에 커밋하지 않음 |
| **웹훅 자동 배포** | `api/webhooks.py` | GitHub/Gitea push 이벤트를 **수신**(HMAC 서명 검증 필수)해 위 checkout→build 파이프라인을 트리거. 플랫폼이 밖으로 나가는 방향이 아니라 받는 방향 |
| **코드 워크스페이스(채팅 편집)** | `services/workspace.py` | LLM이 제안한 diff를 `git apply` 후 작업 브랜치(`paas/chat-{id}`)에 **로컬 커밋만** 한다(`ensure_branch`, `apply_diff`). **자동 push 없음** — 승인(`/changes/{id}/apply`)해도 원격에 반영되지 않고, 실제 배포(release/development)를 실행해야 그 브랜치가 빌드된다 |
| **GitOps 연계** | `services/runtime/k8s_runtime.py` `_gitops_push`/`_sync_gitops_repo` | 2차(K8s) 티어에서 `PAAS_K8S_GITOPS_REPO` 설정 시에만 활성화. 배포 **매니페스트**(이미지 태그·비-시크릿 env)를 별도 GitOps 리포에 커밋·푸시해 ArgoCD가 반영하게 한다. **시크릿은 여기 포함되지 않음**(15절) — 애초에 소스 코드가 아니라 K8s 매니페스트만 다루는 경로 |
| **프리뷰** | `services/preview.py` | 위 checkout 재사용, 별도 git 조작 없음 |

**핵심 경계선**: 프로젝트 소스 코드 자체가 플랫폼 밖의 git 리포로 나가는 경로는 없다
(체크아웃은 읽기 전용, 채팅 편집은 로컬 커밋만). 외부로 실제 전송되는 것은 두 가지뿐이다 —
① LLM 채팅 시 파일 **내용**이 API 호출로 프로바이더에 전송(어느 프로바이더인지는 12절/15절의
internal·external 구분과 admin 게이트로 통제), ② GitOps 모드에서 배포 **매니페스트**(소스 아님)가
운영자가 지정한 리포로 푸시.

## DB 마이그레이션 (PostgreSQL 운영)

SQLite 빠른 시작은 기동 시 자동 생성(create_all)으로 충분하다.
**PostgreSQL 운영 전환 시에는 Alembic으로 스키마를 관리**한다:

```bash
# 실행 위치: platform/
PAAS_DATABASE_URL=postgresql://user:pw@host/paas python -m alembic upgrade head
# 모델 변경 후 새 리비전: python -m alembic revision --autogenerate -m "설명"
```

## 테스트

```bash
cd platform && python -m pytest tests/ -q   # 107 passed
```

Docker/K8s 미설치 환경에서도 컨트롤 플레인·매니페스트 생성·프로필 로직이 검증됩니다.
