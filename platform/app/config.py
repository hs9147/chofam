"""플랫폼 전역 설정.

PAAS_ 접두사의 환경변수로 재정의한다. 예:
  PAAS_TIER=enterprise PAAS_BASE_DOMAIN=apps.example.com uvicorn app.main:app
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Tier = Literal["small", "enterprise"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAAS_", env_file=".env", extra="ignore")

    # 1차(small): Docker 단일/소수 서버, 2차(enterprise): Kubernetes 클러스터
    tier: Tier = "small"

    # --- 설치 빌드옵션 ---
    # 기능 모듈 선택 (core는 항상 켜짐). 예: "deploy" 만 켜면 배포 전용 서버.
    features: str = "deploy,workspace,mail,payment"
    # 운영환경 OS. auto면 platform.system()으로 감지. 컨테이너 등 감지가 틀릴 때 명시.
    host_os: Literal["auto", "linux", "macos", "windows"] = "auto"
    # 기능 매트릭스가 GPU 불가로 판단해도 강제 허용 (예: 커스텀 GPU 런타임)
    force_gpu: bool = False

    # --- mail 모듈: CHO-FAM 메일 API 연동 ---
    mail_api_url: str = ""  # 예: https://cho-fam.web.app/api/mail
    mail_api_key: str = ""
    mail_alert_to: str = ""  # 관리자 알림 수신 주소
    mail_template_id: str = ""  # 알림용 SendGrid 동적 템플릿 ID

    # --- payment 모듈: 토스페이먼츠 ---
    toss_secret_key: str = ""
    toss_api_base: str = "https://api.tosspayments.com"

    # --- OIDC/RBAC (Keycloak 호환, 선택 — API 키 체계와 병행) ---
    oidc_issuer: str = ""  # 예: https://sso.example.com/realms/company
    oidc_audience: str = ""  # 비우면 audience 검증 생략
    oidc_jwks_url: str = ""  # 비우면 {issuer}/protocol/openid-connect/certs (Keycloak 규약)
    oidc_admin_role: str = "paas-admin"  # realm_access.roles에 이 롤이 있으면 admin

    # --- 배포 작업 큐 ---
    deploy_workers: int = 2

    # --- OpenBao 시크릿 (선택 — 설정 시 Fernet 키를 KV v2에서 로드) ---
    openbao_url: str = ""  # 예: https://bao.example.com
    openbao_token: str = ""
    openbao_key_path: str = "secret/data/paas/fernet"  # data.data.key 에 Fernet 키 저장

    database_url: str = "sqlite:///./paas.db"
    base_domain: str = "deploy.localhost"

    # 관리자 부트스트랩 API 키. 미설정 시 기동 로그에 일회성 키를 출력한다.
    admin_api_key: str = ""
    # EnvVar 암호화용 Fernet 키(urlsafe base64 32byte). 미설정 시 개발용 키를 생성한다.
    fernet_key: str = ""
    # 키 회전용 구(舊) 키 목록(콤마 구분) — 복호화에만 사용, 암호화는 fernet_key로.
    # 회전 절차: 새 키 발급 → fernet_key 교체 + 기존 키를 여기로 이동 →
    # POST /admin/rotate-secrets 로 전체 재암호화 → 구 키 제거.
    fernet_keys_old: str = ""

    # Git 작업 디렉토리 / 빌드 로그 저장소
    work_dir: Path = Path("./data/workspaces")
    build_log_dir: Path = Path("./data/build-logs")

    # --- 1차(small) 전용 ---
    caddy_sites_dir: Path = Path("./data/caddy-sites")
    caddy_admin_url: str = "http://127.0.0.1:2019"
    port_range_start: int = 8100
    port_range_end: int = 8999

    # --- 2차(enterprise) 전용 ---
    k8s_namespace: str = "paas-apps"
    k8s_registry: str = ""  # 예: harbor.example.com/paas — 빈 값이면 로컬 이미지명 사용
    k8s_ingress_class: str = "traefik"
    k8s_cluster_issuer: str = "letsencrypt"  # cert-manager ClusterIssuer
    # 멀티테넌시 격리(갭6): 유닛별 NetworkPolicy 생성 — ingress 컨트롤러·동일 네임스페이스만 허용
    k8s_isolation: bool = False
    k8s_ingress_namespace: str = "traefik"  # ingress 컨트롤러가 사는 네임스페이스
    # GitOps(ArgoCD) 연계: 설정 시 직접 apply 대신 매니페스트를 이 리포에 커밋·푸시
    k8s_gitops_repo: str = ""  # 예: git@git.example.com:org/paas-apps.git
    k8s_gitops_branch: str = "main"
    k8s_gitops_path: str = "apps"  # 리포 내 매니페스트 디렉토리
    # 네임스페이스 ResourceQuota (빈 값이면 미생성)
    k8s_quota_cpu: str = ""  # 예: "20"
    k8s_quota_memory: str = ""  # 예: "64Gi"
    # kubernetes 패키지가 없거나 apply 권한이 없을 때 매니페스트를 내려쓸 위치
    k8s_manifest_dir: Path = Path("./data/k8s-manifests")

    # 웹훅 서명 검증용 공유 시크릿 (GitHub/Gitea 웹훅 설정에 동일 값 입력)
    webhook_secret: str = ""

    # 사내 Git 서버(Gitea 등) 기본 URL — 콘솔에 "Git" 메뉴를 노출하는 용도로만 쓰인다
    # (배포 동작에는 영향 없음, git_url은 프로젝트별로 여전히 개별 지정). infra/gitea/ 참고.
    gitea_url: str = ""
    # 조직/리포 자동 생성용 Gitea API 토큰 (Site Administration → Applications에서 발급,
    # 조직 생성 권한 필요). 설정 없으면 /orgs API는 503으로 명확히 실패한다.
    gitea_api_token: str = ""
    # 기업용 거버넌스: true면 프로젝트 등록 시 git_url 호스트가 gitea_url과 일치해야
    # 한다(github.com 등 외부 호스트 등록을 422로 거부). "소스가 사외로 나가지 않는다"는
    # 보장을 internal LLM 강제(schemas.py)와 동일한 원칙으로 git 저장소에도 적용한다.
    git_internal_only: bool = False

    # release 빌드 기본 리소스 (development는 build.py의 프로필 정의가 절반 수준으로 축소)
    default_memory_limit: str = "1g"
    default_cpu_limit: float = 1.0


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.work_dir, s.build_log_dir, s.caddy_sites_dir, s.k8s_manifest_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
