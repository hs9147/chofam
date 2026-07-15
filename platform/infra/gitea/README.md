# 사내 Git 서버 (Gitea)

GitHub을 대신하는 self-host Git 서버. MIT 라이선스로 상용·사내 사용에 제약이 없다
(근거: [설계 검토 문서 10.2절](../../../docs/cloud-platform-paas-design-review.md)).
소스가 사외 SaaS로 나가지 않아야 하는 기업용 요건에 맞춰 여기 구성한다.

플랫폼(FastAPI 컨트롤 플레인) 코드는 이미 GitHub과 Gitea 웹훅 서명을 둘 다
인식하므로(`X-Hub-Signature-256` / `X-Gitea-Signature`, `app/security.py`), 애플리케이션
변경 없이 아래 배포만으로 연동된다.

## 어느 걸 쓸지

| | 1차(중소규모) | 2차(기업용) |
| --- | --- | --- |
| 파일 | `docker-compose.yml` + `Caddyfile.example` | `k8s/*.yaml` |
| 대상 | 플랫폼과 같은 서버(3.1~3.2절 흐름 그대로) | 플랫폼 K8s 클러스터(6.2절 ingress·cert-manager 재사용 |
| DB | 내장 SQLite | 내장 SQLite → 팀 규모가 크면 Postgres로 교체(주석 참고) |

## 1차 배포 (Docker Compose)

```bash
# 실행 위치: 플랫폼 서버 — /opt/paas/platform/infra/gitea
GITEA_DOMAIN=git.example.com docker compose -f docker-compose.yml up -d
```

메인 Caddyfile에 `Caddyfile.example` 내용을 `import`하거나 그대로 복사한다.
DNS: `git.example.com → 서버 IP` A 레코드 하나면 충분(플랫폼과 같은 서버 전제).

## 2차 배포 (Kubernetes)

```bash
kubectl apply -f k8s/namespace.yaml -f k8s/pvc.yaml -f k8s/deployment.yaml \
  -f k8s/service.yaml -f k8s/ingress.yaml
```

`deployment.yaml`·`ingress.yaml`의 `git.example.com`을 실제 도메인으로 바꾸고,
DB를 Postgres로 교체하려면 deployment.yaml 주석의 `GITEA__database__*` 블록을 활성화한 뒤
비밀번호는 플랫폼의 시크릿 관행과 동일하게 `envFrom: secretRef`로 주입할 것
(평문 env 금지 — [15절](../../../docs/cloud-platform-paas-design-review.md) 참고).

## 최초 설정 (공통)

1. `https://git.example.com` 접속 → 설치 마법사에서 관리자 계정 생성
2. Site Administration → Configuration → **"Enable registration"이 꺼져 있는지 확인**
   (compose/K8s 모두 `DISABLE_REGISTRATION=true` 기본값 — 계정은 관리자가 초대)
3. (선택) Keycloak SSO 연동 — 플랫폼의 `PAAS_OIDC_ISSUER`와 동일 Realm을 재사용해
   콘솔·Gitea 로그인을 통일:
   ```bash
   gitea admin auth add-oauth \
     --name keycloak --provider openidConnect \
     --key <gitea client id> --secret <gitea client secret> \
     --auto-discover-url "${PAAS_OIDC_ISSUER}/.well-known/openid-configuration"
   ```
   (Keycloak 쪽에 `gitea`용 OIDC 클라이언트를 먼저 등록해야 한다 — Keycloak 자체 배포는
   이 문서의 범위 밖.)

## 플랫폼과 연결

0. **(조직별 자동 관리 — 권장)** Site Administration → Applications에서 조직/리포 생성
   권한이 있는 API 토큰을 발급해 플랫폼 `.env`의 `PAAS_GITEA_API_TOKEN`에 설정하면,
   콘솔의 "조직" 페이지(admin)에서 조직을 만들 때마다 여기 동명의 Organization이
   자동 생성되고, 조직 소속 프로젝트의 리포도 플랫폼이 대신 만든다 — 사용자는
   Gitea 화면에서 직접 리포를 만들 필요가 없다(일반 사용자에게 git_url도 노출 안 됨).
1. **(레거시) 프로젝트 등록**: 조직을 쓰지 않는 경우 `POST /projects`의 `git_url`을
   이 Gitea 인스턴스 주소로 직접 지정 (예: `https://git.example.com/org/shop-api`)
2. **웹훅 자동 배포**: Gitea 리포 → Settings → Webhooks → Add Webhook
   - Payload URL: `https://<플랫폼>/webhooks/git`
   - Secret: 플랫폼 `.env`의 `PAAS_WEBHOOK_SECRET`과 동일 값
   - Trigger: Push events
3. 이후 흐름은 [deployment-guide.md 3.4절](../../../docs/deployment-guide.md)의 GitHub 웹훅
   절차와 동일 — 서명 헤더 이름만 다를 뿐 플랫폼이 자동으로 구분한다.

## 백업

`gitea-data`(compose 볼륨) 또는 `gitea-data` PVC(K8s) 하나가 저장소·설정·DB(SQLite)를
전부 담고 있다. 정기 스냅샷 또는 `gitea dump` 명령으로 백업할 것.
