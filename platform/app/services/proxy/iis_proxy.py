"""1차(small) 리버스프록시 대안 — IIS (URL Rewrite 모듈 사용, Windows 전용).

사이트별 물리 경로에 web.config(URL Rewrite 규칙)를 생성하고 appcmd.exe로 사이트를
등록한다. redirect/rewrite 규칙은 web.config의 rewrite rule로, 나머지 모든 요청은
백엔드 endpoint로 리버스프록시한다.
"""
import subprocess

from ...config import get_settings
from ...models import BuildProfile
from ..runtime.base import Endpoint
from .base import RedirectSpec, ReverseProxy, site_name

REDIRECT_TYPES = {301: "Permanent", 302: "Found", 303: "SeeOther", 307: "Temporary"}


class IISError(RuntimeError):
    pass


def _rule_xml(idx: int, r: RedirectSpec) -> str:
    match = r.from_path.lstrip("/")
    if r.kind == "redirect":
        redirect_type = REDIRECT_TYPES.get(r.status_code, "Found")
        return (
            f'        <rule name="redirect-{idx}" stopProcessing="true">\n'
            f'          <match url="^{match}$" />\n'
            f'          <action type="Redirect" url="{r.to_path}" redirectType="{redirect_type}" />\n'
            f'        </rule>\n'
        )
    return (
        f'        <rule name="rewrite-{idx}" stopProcessing="true">\n'
        f'          <match url="^{match}$" />\n'
        f'          <action type="Rewrite" url="{r.to_path}" />\n'
        f'        </rule>\n'
    )


def _web_config(endpoint: Endpoint, redirects: list[RedirectSpec]) -> str:
    rule_blocks = "".join(_rule_xml(i, r) for i, r in enumerate(redirects))
    proxy_target = f"http://{endpoint.host}:{endpoint.port}/{{R:1}}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<configuration>\n"
        "  <system.webServer>\n"
        "    <rewrite>\n"
        "      <rules>\n"
        f"{rule_blocks}"
        '        <rule name="reverse-proxy" stopProcessing="true">\n'
        '          <match url="(.*)" />\n'
        f'          <action type="Rewrite" url="{proxy_target}" />\n'
        "        </rule>\n"
        "      </rules>\n"
        "    </rewrite>\n"
        "  </system.webServer>\n"
        "</configuration>\n"
    )


class IISProxy(ReverseProxy):
    def configure(self, project_name, profile: BuildProfile, domain, endpoint: Endpoint,
                  redirects: list[RedirectSpec]) -> None:
        settings = get_settings()
        name = site_name(project_name, profile)
        site_dir = settings.iis_sites_root / name
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "web.config").write_text(_web_config(endpoint, redirects), encoding="utf-8")

        # 이미 있으면 삭제 후 재생성 — 존재 여부를 appcmd 출력에서 파싱하는 것보다 단순하고
        # 멱등하다(사이트가 없어 delete가 실패해도 조용히 넘어간다).
        subprocess.run(
            [settings.iis_appcmd_path, "delete", "site", f"/site.name:{name}"],
            capture_output=True, text=True,
        )
        self._appcmd(
            "add", "site",
            f"/name:{name}", f"/physicalPath:{site_dir}", f"/bindings:http/*:80:{domain}",
        )

    def remove(self, project_name, profile: BuildProfile) -> None:
        settings = get_settings()
        name = site_name(project_name, profile)
        subprocess.run(
            [settings.iis_appcmd_path, "delete", "site", f"/site.name:{name}"],
            capture_output=True, text=True,
        )

    def _appcmd(self, *args: str) -> None:
        appcmd = get_settings().iis_appcmd_path
        proc = subprocess.run([appcmd, *args], capture_output=True, text=True)
        if proc.returncode != 0:
            raise IISError(
                f"appcmd {args[0]} 실패 (IIS 미설치 시 PAAS_IIS_APPCMD_PATH 확인): "
                f"{(proc.stderr or proc.stdout).strip()[:500]}"
            )
