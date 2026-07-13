"""1차(small) 전용 도메인 라우팅 — Caddy.

메인 Caddyfile에 아래 한 줄만 있으면 된다:
    import <caddy_sites_dir>/*.caddy

도메인 추가 = 사이트 파일 생성 + admin API로 무중단 reload.
(2차/k8s에서는 Ingress + cert-manager가 이 역할을 하므로 이 모듈을 쓰지 않는다)
"""
import subprocess

import httpx

from ..config import get_settings
from ..models import BuildProfile
from .runtime.base import Endpoint

SITE_TEMPLATE = """{domain} {{
    reverse_proxy {host}:{port}
    log
}}
"""


def domain_for(project_name: str, custom_domain: str | None, profile: BuildProfile) -> str:
    """release는 지정 도메인(없으면 {name}.{base}), development는 항상 {name}-dev.{base}."""
    settings = get_settings()
    if profile == BuildProfile.development:
        return f"{project_name}-dev.{settings.base_domain}"
    return custom_domain or f"{project_name}.{settings.base_domain}"


def configure(project_name: str, profile: BuildProfile, domain: str, endpoint: Endpoint) -> None:
    settings = get_settings()
    suffix = "-dev" if profile == BuildProfile.development else ""
    site_file = settings.caddy_sites_dir / f"{project_name}{suffix}.caddy"
    site_file.write_text(
        SITE_TEMPLATE.format(domain=domain, host=endpoint.host, port=endpoint.port),
        encoding="utf-8",
    )
    reload_caddy()


def remove(project_name: str, profile: BuildProfile) -> None:
    settings = get_settings()
    suffix = "-dev" if profile == BuildProfile.development else ""
    site_file = settings.caddy_sites_dir / f"{project_name}{suffix}.caddy"
    site_file.unlink(missing_ok=True)
    reload_caddy()


def reload_caddy() -> bool:
    """caddy CLI 우선, 실패 시 admin API. Caddy 미기동 환경(테스트 등)에서는 조용히 넘어간다."""
    try:
        proc = subprocess.run(["caddy", "reload"], capture_output=True, timeout=15)
        if proc.returncode == 0:
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    try:
        settings = get_settings()
        httpx.post(f"{settings.caddy_admin_url}/load", timeout=5)
        return True
    except Exception:
        return False
