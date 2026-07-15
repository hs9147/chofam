"""1차(small) 리버스프록시 대안 — Apache httpd (mod_proxy + mod_rewrite).

프로젝트별 VirtualHost 설정 파일을 PAAS_APACHE_SITES_DIR에 생성하고, 설정 반영을 위해
PAAS_APACHE_RELOAD_CMD(기본 "apachectl graceful")를 실행한다. 파일을 어느 Include
디렉티브로 불러올지는 Apache 본 설정(httpd.conf) 쪽의 몫이다 — Caddy의
"import <sites_dir>/*.caddy" 관례와 동일하게, 운영자가 한 번만 연결해두면 된다.
"""
import subprocess

from ...config import get_settings
from ...models import BuildProfile
from ..runtime.base import Endpoint
from .base import PathRoute, RedirectSpec, ReverseProxy, site_name


def _directive(r: RedirectSpec) -> str:
    if r.kind == "redirect":
        return f"    Redirect {r.status_code} {r.from_path} {r.to_path}\n"
    return f"    RewriteRule ^{r.from_path}$ {r.to_path} [L]\n"


def _vhost_conf(domain: str, endpoint: Endpoint, redirects: list[RedirectSpec]) -> str:
    rewrite_engine = "    RewriteEngine On\n" if any(r.kind == "rewrite" for r in redirects) else ""
    directives = "".join(_directive(r) for r in redirects)
    return (
        "<VirtualHost *:80>\n"
        f"    ServerName {domain}\n"
        f"{rewrite_engine}"
        f"{directives}"
        "    ProxyPreserveHost On\n"
        f"    ProxyPass / http://{endpoint.host}:{endpoint.port}/\n"
        f"    ProxyPassReverse / http://{endpoint.host}:{endpoint.port}/\n"
        "</VirtualHost>\n"
    )


def _conf_file(project_name: str, profile: BuildProfile):
    settings = get_settings()
    return settings.apache_sites_dir / f"{site_name(project_name, profile)}.conf"


def _path_directives(routes: list[PathRoute]) -> str:
    """ProxyPass는 등록 순서대로 매칭하므로 비루트(prefix) 규칙을 먼저 둔다 — mod_proxy가
    접두사를 자동으로 벗겨내므로 handle_path/IIS rewrite와 동일한 규약이 된다."""
    lines = []
    for r in routes:
        if r.path_prefix in ("/", ""):
            continue
        prefix = "/" + r.path_prefix.strip("/") + "/"
        lines.append(f"    ProxyPass {prefix} http://{r.endpoint.host}:{r.endpoint.port}/\n")
        lines.append(f"    ProxyPassReverse {prefix} http://{r.endpoint.host}:{r.endpoint.port}/\n")
    return "".join(lines)


def _vhost_conf_paths(domain: str, routes: list[PathRoute], redirects: list[RedirectSpec]) -> str:
    root = next((r for r in routes if r.path_prefix in ("/", "")), routes[-1])
    rewrite_engine = "    RewriteEngine On\n" if any(r.kind == "rewrite" for r in redirects) else ""
    directives = "".join(_directive(r) for r in redirects)
    return (
        "<VirtualHost *:80>\n"
        f"    ServerName {domain}\n"
        f"{rewrite_engine}"
        f"{directives}"
        "    ProxyPreserveHost On\n"
        f"{_path_directives(routes)}"
        f"    ProxyPass / http://{root.endpoint.host}:{root.endpoint.port}/\n"
        f"    ProxyPassReverse / http://{root.endpoint.host}:{root.endpoint.port}/\n"
        "</VirtualHost>\n"
    )


class ApacheProxy(ReverseProxy):
    def configure(self, project_name, profile: BuildProfile, domain, endpoint: Endpoint,
                  redirects: list[RedirectSpec]) -> None:
        _conf_file(project_name, profile).write_text(
            _vhost_conf(domain, endpoint, redirects), encoding="utf-8",
        )
        self._reload()

    def configure_paths(self, project_name, profile: BuildProfile, domain,
                         routes: list[PathRoute], redirects: list[RedirectSpec]) -> None:
        _conf_file(project_name, profile).write_text(
            _vhost_conf_paths(domain, routes, redirects), encoding="utf-8",
        )
        self._reload()

    def remove(self, project_name, profile: BuildProfile) -> None:
        _conf_file(project_name, profile).unlink(missing_ok=True)
        self._reload()

    def _reload(self) -> bool:
        """apachectl 미설치 환경(테스트 등)에서는 조용히 넘어간다 — Caddy reload와 동일 정책."""
        try:
            proc = subprocess.run(
                get_settings().apache_reload_cmd.split(), capture_output=True, timeout=15,
            )
            return proc.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
