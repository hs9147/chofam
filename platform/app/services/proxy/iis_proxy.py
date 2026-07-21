"""1차(small) 리버스프록시 대안 — IIS (URL Rewrite 모듈 사용, Windows 전용).

배포 URL은 서브패스 기반이다: 프로젝트들은 기본적으로 base_domain 하나를 공유하고
/{조직}/{프로젝트}/ 경로로 구분된다(services/proxy/__init__.py의 path_prefix_for).
IIS URL Rewrite는 Caddy의 "import 디렉터리 글롭"이나 Apache의 IncludeOptional 같은
다중 파일 결합 수단이 없어, 프로젝트별로 규칙 조각(XML fragment) 파일 하나를
routes/ 아래 쓰고, 배포/제거 때마다 그 조각들을 모아 base 사이트의 web.config
하나로 다시 합성한다(_regenerate_base_web_config). 조각 파일명은 site_name만으로
정해지므로(조직 정보 불필요) remove()가 project_name/profile만으로도 정확히
지울 수 있다 — 기존 인터페이스를 그대로 유지한다.

release 배포에 커스텀 도메인(project.domain)을 지정한 예외만 기존처럼 독립된
사이트(자기 physicalPath·바인딩)를 그대로 쓴다.
"""
import subprocess

from ...config import get_settings
from ...models import BuildProfile
from ..runtime.base import Endpoint
from .base import PathRoute, RedirectSpec, ReverseProxy, site_name

REDIRECT_TYPES = {301: "Permanent", 302: "Found", 303: "SeeOther", 307: "Temporary"}

BASE_SITE_NAME = "_base"


class IISError(RuntimeError):
    pass


def _prefixed(path_prefix: str, sub_path: str) -> str:
    """redirect/rewrite의 from_path/to_path는 프로젝트 자신의 경로 기준이므로,
    공유 사이트(site 루트 기준 규칙만 지원)에서는 조직/프로젝트 접두사를 명시적으로
    붙여야 한다 — Caddy의 handle_path 자동 경로 스트리핑과 동일한 의미를 낸다."""
    return path_prefix.rstrip("/") + "/" + sub_path.lstrip("/")


def _rule_xml(name: str, match_url: str, r: RedirectSpec) -> str:
    if r.kind == "redirect":
        redirect_type = REDIRECT_TYPES.get(r.status_code, "Found")
        return (
            f'        <rule name="{name}" stopProcessing="true">\n'
            f'          <match url="^{match_url}$" />\n'
            f'          <action type="Redirect" url="{r.to_path}" redirectType="{redirect_type}" />\n'
            f'        </rule>\n'
        )
    return (
        f'        <rule name="{name}" stopProcessing="true">\n'
        f'          <match url="^{match_url}$" />\n'
        f'          <action type="Rewrite" url="{r.to_path}" />\n'
        f'        </rule>\n'
    )


def _path_rule_xml(name: str, route: PathRoute) -> str:
    prefix = route.path_prefix.strip("/")
    proxy_target = f"http://{route.endpoint.host}:{route.endpoint.port}/{{R:1}}"
    return (
        f'        <rule name="{name}" stopProcessing="true">\n'
        f'          <match url="^{prefix}/(.*)" />\n'
        f'          <action type="Rewrite" url="{proxy_target}" />\n'
        f'        </rule>\n'
    )


def _web_config_paths(routes: list[PathRoute], redirects: list[RedirectSpec]) -> str:
    """비루트(prefix) 규칙을 먼저 매칭시키고, "/"는 캐치올로 마지막에 둔다 —
    매칭된 접두사는 업스트림에 전달되기 전에 제거된다(handle_path/ProxyPass와 동일 규약)."""
    rule_blocks = "".join(
        _rule_xml(f"redirect-{i}", r.from_path.lstrip("/"), r) for i, r in enumerate(redirects)
    )
    non_root = [r for r in routes if r.path_prefix not in ("/", "")]
    root = next((r for r in routes if r.path_prefix in ("/", "")), routes[-1])
    path_blocks = "".join(_path_rule_xml(f"path-{i}", r) for i, r in enumerate(non_root))
    proxy_target = f"http://{root.endpoint.host}:{root.endpoint.port}/{{R:1}}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<configuration>\n"
        "  <system.webServer>\n"
        "    <rewrite>\n"
        "      <rules>\n"
        f"{rule_blocks}"
        f"{path_blocks}"
        '        <rule name="reverse-proxy" stopProcessing="true">\n'
        '          <match url="(.*)" />\n'
        f'          <action type="Rewrite" url="{proxy_target}" />\n'
        "        </rule>\n"
        "      </rules>\n"
        "    </rewrite>\n"
        "  </system.webServer>\n"
        "</configuration>\n"
    )


def _is_shared(domain: str) -> bool:
    return domain == get_settings().base_domain


def _routes_dir():
    settings = get_settings()
    d = settings.iis_sites_root / BASE_SITE_NAME / "routes"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _route_fragment_file(project_name: str, profile: BuildProfile):
    return _routes_dir() / f"{site_name(project_name, profile)}.xml"


def _build_shared_fragment(
    frag_key: str, routes: list[PathRoute], redirects: list[RedirectSpec],
) -> str:
    ordered = sorted(routes, key=lambda r: r.path_prefix in ("/", ""))
    blocks = []
    for i, r in enumerate(ordered):
        prefix = r.path_prefix.strip("/")
        proxy_target = f"http://{r.endpoint.host}:{r.endpoint.port}/{{R:1}}"
        blocks.append(
            f'        <rule name="{frag_key}-path-{i}" stopProcessing="true">\n'
            f'          <match url="^{prefix}/(.*)" />\n'
            f'          <action type="Rewrite" url="{proxy_target}" />\n'
            f'        </rule>\n'
        )
    # redirect는 가장 넓게 매칭하는(마지막) 라우트의 경로를 기준으로 접두사를 붙인다.
    root_prefix = ordered[-1].path_prefix
    redirect_blocks = "".join(
        _rule_xml(f"{frag_key}-redirect-{i}", _prefixed(root_prefix, r.from_path).lstrip("/"), r)
        for i, r in enumerate(redirects)
    )
    return redirect_blocks + "".join(blocks)


def _regenerate_base_web_config() -> None:
    settings = get_settings()
    routes_dir = _routes_dir()
    fragments = sorted(routes_dir.glob("*.xml"))
    rule_blocks = "".join(f.read_text(encoding="utf-8") for f in fragments)
    site_dir = settings.iis_sites_root / BASE_SITE_NAME
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "web.config").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<configuration>\n  <system.webServer>\n    <rewrite>\n      <rules>\n"
        f"{rule_blocks}"
        "      </rules>\n    </rewrite>\n  </system.webServer>\n</configuration>\n",
        encoding="utf-8",
    )


def _ensure_base_site() -> None:
    settings = get_settings()
    site_dir = settings.iis_sites_root / BASE_SITE_NAME
    site_dir.mkdir(parents=True, exist_ok=True)
    if not (site_dir / "web.config").exists():
        _regenerate_base_web_config()
    proc = subprocess.run(
        [settings.iis_appcmd_path, "list", "site", f"/name:{BASE_SITE_NAME}"],
        capture_output=True, text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return
    _run_appcmd(
        "add", "site",
        f"/name:{BASE_SITE_NAME}", f"/physicalPath:{site_dir}",
        f"/bindings:http/*:80:{settings.base_domain}",
    )


def _run_appcmd(*args: str) -> None:
    appcmd = get_settings().iis_appcmd_path
    proc = subprocess.run([appcmd, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise IISError(
            f"appcmd {args[0]} 실패 (IIS 미설치 시 PAAS_IIS_APPCMD_PATH 확인): "
            f"{(proc.stderr or proc.stdout).strip()[:500]}"
        )


class IISProxy(ReverseProxy):
    def configure(self, project_name, profile: BuildProfile, domain, path_prefix,
                  endpoint: Endpoint, redirects: list[RedirectSpec]) -> None:
        self.configure_paths(
            project_name, profile, domain, [PathRoute(path_prefix=path_prefix, endpoint=endpoint)],
            redirects,
        )

    def configure_paths(self, project_name, profile: BuildProfile, domain,
                         routes: list[PathRoute], redirects: list[RedirectSpec]) -> None:
        if _is_shared(domain):
            frag_key = site_name(project_name, profile)
            _route_fragment_file(project_name, profile).write_text(
                _build_shared_fragment(frag_key, routes, redirects), encoding="utf-8",
            )
            _regenerate_base_web_config()
            _ensure_base_site()
            return

        settings = get_settings()
        name = site_name(project_name, profile)
        site_dir = settings.iis_sites_root / name
        site_dir.mkdir(parents=True, exist_ok=True)
        (site_dir / "web.config").write_text(_web_config_paths(routes, redirects), encoding="utf-8")

        subprocess.run(
            [settings.iis_appcmd_path, "delete", "site", f"/site.name:{name}"],
            capture_output=True, text=True,
        )
        _run_appcmd(
            "add", "site",
            f"/name:{name}", f"/physicalPath:{site_dir}", f"/bindings:http/*:80:{domain}",
        )

    def remove(self, project_name, profile: BuildProfile) -> None:
        settings = get_settings()
        # 공유 모드 조각 파일 — 있으면 지우고 base web.config를 다시 합성한다.
        frag = _route_fragment_file(project_name, profile)
        if frag.exists():
            frag.unlink()
            _regenerate_base_web_config()

        # 전용 모드(커스텀 도메인) 사이트 — 없으면 조용히 넘어간다.
        name = site_name(project_name, profile)
        subprocess.run(
            [settings.iis_appcmd_path, "delete", "site", f"/site.name:{name}"],
            capture_output=True, text=True,
        )
