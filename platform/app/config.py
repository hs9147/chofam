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
