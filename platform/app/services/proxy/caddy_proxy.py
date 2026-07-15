"""1차(small) 기본 리버스프록시 — Caddy.

메인 Caddyfile에 아래 한 줄만 있으면 된다:
    import <caddy_sites_dir>/*.caddy

도메인 추가 = 사이트 파일 생성 + admin API로 무중단 reload.
"""
import subprocess

import httpx

from ...config import get_settings
from ...models import BuildProfile
from ..runtime.base import Endpoint
from .base import PathRoute, RedirectSpec, ReverseProxy, site_name

SITE_TEMPLATE = """{domain} {{
{redirects}    reverse_proxy {host}:{port}
    log
}}
"""

SITE_TEMPLATE_PATHS = """{domain} {{
{redirects}{blocks}    log
}}
"""


def _redirect_lines(redirects: list[RedirectSpec]) -> str:
    lines = []
    for r in redirects:
        if r.kind == "redirect":
            lines.append(f"    redir {r.from_path} {r.to_path} {r.status_code}")
        else:
            lines.append(f"    rewrite {r.from_path} {r.to_path}")
    return "".join(f"{line}\n" for line in lines)


def _site_file(project_name: str, profile: BuildProfile):
    settings = get_settings()
    return settings.caddy_sites_dir / f"{site_name(project_name, profile)}.caddy"


def _path_block(route: PathRoute) -> str:
    if route.path_prefix in ("/", ""):
        return f"    reverse_proxy {route.endpoint.host}:{route.endpoint.port}\n"
    prefix = route.path_prefix.rstrip("/")
    return (
        f"    handle_path {prefix}/* {{\n"
        f"        reverse_proxy {route.endpoint.host}:{route.endpoint.port}\n"
        f"    }}\n"
    )


class CaddyProxy(ReverseProxy):
    def configure(self, project_name, profile, domain, endpoint: Endpoint,
                  redirects: list[RedirectSpec]) -> None:
        _site_file(project_name, profile).write_text(
            SITE_TEMPLATE.format(
                domain=domain, redirects=_redirect_lines(redirects),
                host=endpoint.host, port=endpoint.port,
            ),
            encoding="utf-8",
        )
        reload_caddy()

    def configure_paths(self, project_name, profile, domain, routes: list[PathRoute],
                         redirects: list[RedirectSpec]) -> None:
        # handle_path는 첫 매칭 블록만 실행하므로 "/"(캐치올)는 반드시 마지막에 둔다.
        ordered = sorted(routes, key=lambda r: r.path_prefix in ("/", ""))
        blocks = "".join(_path_block(r) for r in ordered)
        _site_file(project_name, profile).write_text(
            SITE_TEMPLATE_PATHS.format(
                domain=domain, redirects=_redirect_lines(redirects), blocks=blocks,
            ),
            encoding="utf-8",
        )
        reload_caddy()

    def remove(self, project_name, profile) -> None:
        _site_file(project_name, profile).unlink(missing_ok=True)
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
