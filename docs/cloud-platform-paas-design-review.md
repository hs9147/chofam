# Cloud Platform(내부 PaaS) 개발 검토

> 대상: React · Python · Node · LLM 앱을 하나의 서버에서 배포·운영하는 자체 Deploy Server(내부 PaaS) 제안
> 작성일: 2026-07-12
> 관련 인프라: CHO-FAM(Firebase Hosting + Functions + Firestore), liv-ay 게임서버

---

## 1. 총평

제안된 구조(Build Manager / Container Manager / Reverse Proxy / SSL / Log / Monitor / Auto Restart / API)는
내부 PaaS의 표준 구성을 정확히 짚고 있고, 방향성 자체는 타당합니다. 다만 그대로 전부 구현하면
**사실상 Coolify/Dokploy를 재작성하는 규모**가 되므로, 아래 세 가지를 권장합니다.

1. **런타임은 처음부터 Docker로 고정** — "Docker 없이 프로세스 방식"은 제안서에 대안으로 있지만,
   의존성 충돌·포트 관리·보안 격리·재시작 정책을 전부 직접 구현하게 되어 오히려 일이 커집니다.
   Docker restart policy, 로그, 리소스 제한을 공짜로 얻는 쪽이 이득입니다.
2. **Reverse Proxy는 Caddy** — Let's Encrypt 발급·갱신이 내장되어 있어 제안서의
   "SSL Manager" 컴포넌트가 통째로 사라집니다. (Nginx 선택 시 certbot 연동·갱신 크론·리로드를 직접 관리)
3. **초기 스택 다이어트** — PostgreSQL + Redis + Celery/RabbitMQ는 1인~소규모 운영에는 과합니다.
   SQLite + FastAPI(BackgroundTasks 또는 arq)로 시작해도 동일한 기능을 구현할 수 있고,
   나중에 교체 비용도 낮습니다.

**결론: 자체 개발 가치는 "LLM/GPU 관리 레이어"에 있습니다.** 일반 웹앱 배포(React/Node/Python)는
기존 오픈소스가 이미 잘 해결한 영역이고, vLLM/Ollama 모델 관리·VRAM 스케줄링·API 키/사용량 제한은
기존 도구가 약한 영역이므로 여기에 개발력을 집중하는 것을 추천합니다.

---

## 2. 자체 개발 vs 오픈소스 활용

| 선택지 | 장점 | 단점 | 적합한 경우 |
| --- | --- | --- | --- |
| **자체 개발 (제안안)** | liv-ay/LLM 요구에 정확히 맞춤, 학습 효과 | 개발·유지보수 비용 최대, 보안 책임 전부 부담 | LLM 관리가 핵심이고 장기 운영 의지가 있을 때 |
| **Coolify** | Git push 배포, SSL, 도메인, 로그, 웹훅 전부 내장. 가장 활발한 커뮤니티 | LLM/GPU 관리 기능 없음, 커스터마이징 한계 | 웹앱 배포가 주 목적일 때 |
| **Dokploy** | Docker Compose 친화, Traefik 내장, 가벼움 | 위와 동일 | 위와 동일 |
| **하이브리드 (권장)** | 웹앱은 Coolify/Dokploy에 맡기고, **LLM 관리 플랫폼만 자체 개발** | 두 시스템 운영 | 개발 리소스가 제한적이고 LLM이 차별점일 때 |

전부 직접 만드는 경험 자체가 목표라면 자체 개발도 좋은 선택입니다. 그 경우 아래 3~7절의
설계 보완 사항을 반영하는 것을 전제로 합니다.

---

## 3. 컴포넌트별 검토

### 3.1 Build Manager

제안된 명령(npm build / pip install / vllm serve)은 맞지만, 두 가지 보완이 필요합니다.

- **빌드 격리**: 호스트에서 직접 `npm install`을 실행하면 프로젝트 간 Node/Python 버전 충돌이 납니다.
  빌드도 컨테이너 안에서 수행하세요. 프로젝트 타입별 기본 Dockerfile 템플릿을 플랫폼이 제공하고,
  리포에 Dockerfile이 있으면 그것을 우선하는 방식이 단순하고 예측 가능합니다.
  (Nixpacks/Buildpacks 자동 감지는 매력적이지만 디버깅이 어려워 초기에는 비추천)
- **빌드 산출물 = 이미지 태그**: 빌드 결과를 `프로젝트명:git-sha` 이미지로 남기면
  **Rollback이 "이전 이미지로 컨테이너 재기동" 한 줄**이 됩니다. 별도 버전 관리 로직이 거의 필요 없습니다.

### 3.2 Runtime Manager

- Docker Engine API(python `docker` SDK)로 충분합니다. Kubernetes는 단일 서버에서는 불필요.
- 컨테이너 생성 시 반드시 지정할 것: `restart_policy={"Name": "on-failure", "MaximumRetryCount": 3}`,
  메모리 제한(`mem_limit`), CPU 제한, 그리고 LLM 컨테이너는 `device_requests`로 GPU 할당.
- **포트는 플랫폼이 할당**(예: 8001부터 순차)하고 DB에 기록. 컨테이너는 내부 포트만 알면 됩니다.
- 제안서의 "Auto Restart → 3회 실패 → 관리자 알림"은 Docker restart policy + Docker 이벤트 스트림
  구독(`docker events`)으로 구현하면 폴링이 필요 없습니다. 알림은 이미 운영 중인
  **CHO-FAM 메일 API(`POST /api/mail/send`)를 그대로 재사용**하면 됩니다 — 신규 개발 불필요.

### 3.3 Reverse Proxy + SSL + Domain

- **Caddy 강력 추천.** 도메인 추가 = Caddyfile에 블록 한 개 추가 + `caddy reload`(무중단).
  인증서 발급·갱신·HTTP→HTTPS 리다이렉트가 전부 자동이라 제안서의 4·5번 컴포넌트가
  "Caddyfile 템플릿 렌더링 + reload API 호출"로 축소됩니다.
- 서브도메인이 많아질 예정이면 와일드카드 DNS(`*.deploy.example.com` → 서버 IP) 하나 잡아두면
  도메인 등록 절차 자체가 사라집니다.

### 3.4 Log Manager

- `docker logs --follow`를 FastAPI WebSocket으로 릴레이하면 실시간 로그는 하루면 구현됩니다.
- 주의: **로그 로테이션**을 Docker daemon 옵션(`json-file` + `max-size=10m`, `max-file=3`)으로
  걸어두지 않으면 디스크가 반드시 찹니다. 초기 설정에 포함할 것.
- 빌드 로그는 배포(Deployment) 레코드에 파일로 붙여 보관 — 실패 원인 추적에 필수.

### 3.5 Monitoring

- 시스템: `psutil` (CPU/메모리/디스크/네트워크), GPU: `nvidia-ml-py`(NVML 공식 바인딩) 또는
  `nvidia-smi --query-gpu=... --format=csv` 파싱. 컨테이너별은 Docker stats API.
- 초기에는 30초 주기 수집 → SQLite에 링버퍼(최근 24h)로 충분. Prometheus+Grafana는
  대시보드 요구가 커졌을 때 도입해도 늦지 않습니다.
- **VRAM은 LLM 플랫폼의 핵심 지표**: 모델 로드 전에 "요청 모델의 예상 VRAM vs 현재 여유 VRAM"을
  검사해서 OOM으로 GPU 전체가 죽는 것을 막는 로직이 기존 PaaS에 없는 진짜 차별화 기능입니다.

### 3.6 Auto Deploy (GitHub Webhook)

- **HMAC 서명 검증(`X-Hub-Signature-256`)은 선택이 아니라 필수**입니다. 미검증 웹훅 엔드포인트는
  임의 코드 실행 취약점과 같습니다.
- 같은 프로젝트에 push가 연달아 오는 경우를 대비해 **프로젝트별 배포 락**(동시 배포 1건) +
  마지막 커밋만 배포(중간 커밋 스킵)를 넣으세요.
- 배포 순서는 무중단을 고려해: 새 컨테이너 기동 → 헬스체크 통과 → 프록시 전환 → 구 컨테이너 종료.
  (blue-green 최소형. 처음부터 이렇게 잡는 게 나중에 고치는 것보다 쉽습니다)

---

## 4. 데이터 모델 보강

제안된 단일 `Project` 테이블에서 **배포 이력과 환경변수를 분리**해야 Rollback과 시크릿 관리가 됩니다.

```
Project                    Deployment                 EnvVar
--------                   -----------                -------
id                         id                         id
name                       project_id (FK)            project_id (FK)
type (react/python/        git_sha                    key
      node/llm)            image_tag                  value_encrypted   ← 평문 저장 금지
git_url                    status (building/running/  is_secret
branch                             failed/stopped)
domain                     build_log_path
port (플랫폼 할당)          created_at
health_check_path          finished_at
created_at
```

- `Deployment`가 이력 테이블이므로 Rollback = "이전 Deployment의 image_tag로 재기동".
- 환경변수는 **암호화 저장**(예: `cryptography.Fernet`, 키는 서버 환경변수로만 보관).
  현재 functions에서 시크릿을 Firebase secrets로 관리하는 것과 같은 원칙입니다.
- LLM 프로젝트는 확장 필드: `model_name`, `quantization`, `max_model_len`, `gpu_ids`, `estimated_vram_gb`.

---

## 5. 기술 스택 검토 (제안 대비 수정안)

| 구성 요소 | 제안 | 검토 의견 |
| --- | --- | --- |
| Backend | FastAPI | ✅ 유지. WebSocket·async 지원으로 적합 |
| Frontend | React + Vite | ✅ 유지. admin 대시보드 경험(public/admin) 재활용 가능 |
| DB | PostgreSQL | ⚠️ 초기엔 **SQLite**로 충분(단일 서버, 낮은 쓰기 빈도). SQLAlchemy로 작성해두면 이관 무비용 |
| Cache | Redis | ⚠️ 초기 불필요. 큐 도입 시 함께 |
| Queue | Celery/RabbitMQ | ⚠️ 과함. FastAPI BackgroundTasks → 부족해지면 **arq**(Redis 기반, 경량) |
| Container | Docker Engine API | ✅ 유지 (python `docker` SDK) |
| Proxy | Nginx 또는 Caddy | ✅ **Caddy로 확정 권장** (SSL 컴포넌트 제거 효과) |
| Process 관리 | Supervisor | ❌ 불필요. Docker restart policy로 대체 |
| 인증 | JWT + OAuth | ⚠️ 내부 도구는 **API 키(해시 저장) + 관리자 세션**으로 시작. OAuth는 사용자가 늘면 |
| LLM | vLLM, Ollama | ✅ 유지. OpenAI 호환 엔드포인트로 통일 |

---

## 6. 보안 체크리스트 (자체 개발 시 반드시)

1. GitHub Webhook HMAC 서명 검증 (3.6절)
2. 환경변수/시크릿 암호화 저장, API 응답에서 값 마스킹
3. 배포 API 전체 인증 필수 — CHO-FAM 메일 API의 `x-api-key` 패턴 재사용 가능
4. 컨테이너에 `--privileged` 금지, 호스트 볼륨 마운트 최소화, 가능하면 non-root 실행
5. Docker 소켓(`/var/run/docker.sock`)을 노출하는 컨테이너 금지 — 배포 서버 프로세스만 접근
6. 관리 대시보드는 공개 인터넷에 그대로 노출하지 말 것 (최소한 IP 제한 또는 VPN/Tailscale)
7. LLM API 키 발급 시: 키는 해시로 저장, 프리픽스만 노출, 사용량 카운팅은 Redis 도입 후 정확화
8. 빌드 시 리포지토리 코드가 호스트 권한으로 실행되지 않도록 빌드 컨테이너 격리 (3.1절)

---

## 7. 단계별 로드맵

### Phase 1 — MVP (핵심 루프 검증)
- Project CRUD + git clone/pull
- Dockerfile 기반 빌드 → `이름:sha` 이미지 → 컨테이너 실행
- Caddy 연동(도메인 + 자동 HTTPS)
- WebSocket 실시간 로그
- API 키 인증
- 스택: FastAPI + SQLite + Docker SDK + Caddy

### Phase 2 — 자동화
- GitHub Webhook 자동 배포(서명 검증 + 배포 락)
- 헬스체크 기반 무중단 전환(blue-green 최소형)
- Rollback (Deployment 이력 기반)
- Crash 알림 → CHO-FAM 메일 API 연동
- React 관리 대시보드

### Phase 3 — LLM 플랫폼 (차별화 구간)
- vLLM/Ollama 서버 등록·모델 관리
- VRAM 사전 검사 + GPU 할당 스케줄링 (3.5절)
- OpenAI 호환 게이트웨이 + API 키 발급·rate limit·사용량 집계
- GPU/VRAM 대시보드 (NVML)

### Phase 4 — 확장 (필요해질 때만)
- PostgreSQL/Redis/arq 전환, 멀티 서버, 오토스케일링, 이미지 생성 서버(Flux 등) 등록

---

## 8. 리스크

| 리스크 | 내용 | 완화 |
| --- | --- | --- |
| 유지보수 부담 | 배포 서버 자체가 SPOF. 배포 서버가 죽으면 모든 앱 배포 불가 | 앱 런타임(Docker+Caddy)은 배포 서버 프로세스와 독립적으로 동작하도록 설계 — 배포 서버가 죽어도 서비스는 계속 뜸 |
| 보안 사고 | 웹훅/시크릿/도커 소켓 취급 실수 시 서버 전체 장악 가능 | 6절 체크리스트를 Phase 1부터 적용 |
| 범위 팽창 | 10개 컴포넌트 동시 개발 시 완성 전에 동력 상실 | Phase 1을 2주 내 완결 가능한 크기로 고정 |
| 오픈소스와의 중복 | Phase 1~2는 Coolify가 이미 제공 | LLM 요구가 확실치 않으면 2절 하이브리드안 재검토 |

---

## 9. 결론

- 설계 방향은 타당하며, 구성 요소 목록도 빠짐없음.
- **Docker 고정 + Caddy 채택 + 초기 스택 축소(SQLite, 큐 생략)** 세 가지만 반영하면
  구현 난이도가 크게 내려가고, 제안서의 컴포넌트 중 2개(SSL Manager, Process 관리)가 사실상 제거됨.
- 자체 개발의 진짜 가치는 **Phase 3(LLM/GPU 관리)**에 있으므로, 웹앱 배포(Phase 1~2)를
  오픈소스로 대체하는 하이브리드안도 병행 검토 권장.
- 기존 CHO-FAM 자산(메일 API, x-api-key 인증 패턴, admin 대시보드 UI)을 알림·인증·프론트엔드에
  재사용하면 개발량을 추가로 줄일 수 있음.
