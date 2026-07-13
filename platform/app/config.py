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

    database_url: str = "sqlite:///./paas.db"
    base_domain: str = "deploy.localhost"

    # 관리자 부트스트랩 API 키. 미설정 시 기동 로그에 일회성 키를 출력한다.
    admin_api_key: str = ""
    # EnvVar 암호화용 Fernet 키(urlsafe base64 32byte). 미설정 시 개발용 키를 생성한다.
    fernet_key: str = ""

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
    # kubernetes 패키지가 없거나 apply 권한이 없을 때 매니페스트를 내려쓸 위치
    k8s_manifest_dir: Path = Path("./data/k8s-manifests")

    # 웹훅 서명 검증용 공유 시크릿 (GitHub/Gitea 웹훅 설정에 동일 값 입력)
    webhook_secret: str = ""

    # release 빌드 기본 리소스 (development는 build.py의 프로필 정의가 절반 수준으로 축소)
    default_memory_limit: str = "1g"
    default_cpu_limit: float = 1.0


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.work_dir, s.build_log_dir, s.caddy_sites_dir, s.k8s_manifest_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
