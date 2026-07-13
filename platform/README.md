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

GET  /projects
POST /projects                        # {name, type, git_url, branch, domain?, ...}
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

## 테스트

```bash
cd platform && python -m pytest tests/ -q   # 39 passed
```

Docker/K8s 미설치 환경에서도 컨트롤 플레인·매니페스트 생성·프로필 로직이 검증됩니다.
