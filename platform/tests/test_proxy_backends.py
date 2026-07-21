"""리버스프록시 백엔드 — Caddy(기본)/IIS/Apache 서브패스 라우팅 + redirect/rewrite 반영."""
import subprocess

from app.config import get_settings
from app.models import BuildProfile
from app.services import proxy
from app.services.proxy.apache_proxy import ApacheProxy
from app.services.proxy.base import PathRoute, RedirectSpec
from app.services.proxy.caddy_proxy import CaddyProxy
from app.services.proxy.iis_proxy import IISProxy
from app.services.runtime.base import Endpoint

ENDPOINT = Endpoint(host="127.0.0.1", port=8123)
REDIRECTS = [
    RedirectSpec(from_path="/old", to_path="/new", kind="redirect", status_code=301),
    RedirectSpec(from_path="/internal", to_path="/v2/internal", kind="rewrite"),
]

BACKEND_ENDPOINT = Endpoint(host="127.0.0.1", port=8001)
FRONTEND_ENDPOINT = Endpoint(host="127.0.0.1", port=8002)


def _composite_routes(base_prefix: str) -> list[PathRoute]:
    return [
        PathRoute(path_prefix=base_prefix + "api/", endpoint=BACKEND_ENDPOINT),
        PathRoute(path_prefix=base_prefix, endpoint=FRONTEND_ENDPOINT),
    ]


def test_get_proxy_selects_backend(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_PROXY_BACKEND", "iis")
    get_settings.cache_clear()
    assert isinstance(proxy.get_proxy(), IISProxy)

    monkeypatch.setenv("PAAS_PROXY_BACKEND", "apache")
    get_settings.cache_clear()
    assert isinstance(proxy.get_proxy(), ApacheProxy)

    monkeypatch.setenv("PAAS_PROXY_BACKEND", "caddy")
    get_settings.cache_clear()
    assert isinstance(proxy.get_proxy(), CaddyProxy)


def test_domain_for_is_shared_base_domain_by_default(fresh_settings):
    """서브패스 라우팅 — 커스텀 도메인이 없으면(또는 development면) 항상
    base_domain 하나를 공유한다. release+커스텀 도메인만 예외."""
    assert proxy.domain_for("shop", None, BuildProfile.release) == "apps.test"
    assert proxy.domain_for("shop", "custom.example.com", BuildProfile.release) == "custom.example.com"
    assert proxy.domain_for("shop", "custom.example.com", BuildProfile.development) == "apps.test"


def test_path_prefix_for_org_and_legacy_and_dev(fresh_settings):
    assert proxy.path_prefix_for("acme", "shop", None, BuildProfile.release) == "/apps/acme/shop/"
    assert proxy.path_prefix_for("acme", "shop", None, BuildProfile.development) == "/apps/acme/shop/dev/"
    assert proxy.path_prefix_for(None, "shop", None, BuildProfile.release) == "/apps/_/shop/"
    # 커스텀 도메인 + release만 "/"(도메인 전체가 이 프로젝트 것)
    assert proxy.path_prefix_for("acme", "shop", "custom.example.com", BuildProfile.release) == "/"
    assert proxy.path_prefix_for("acme", "shop", "custom.example.com", BuildProfile.development) == "/apps/acme/shop/dev/"


def test_domain_and_path_prefix_unaffected_on_enterprise_tier(monkeypatch, fresh_settings):
    """2차(K8s)는 서브패스 라우팅 대상이 아니다 — 프로젝트당 서브도메인 1개 그대로."""
    monkeypatch.setenv("PAAS_TIER", "enterprise")
    get_settings.cache_clear()
    assert proxy.domain_for("shop", None, BuildProfile.release) == "shop.apps.test"
    assert proxy.domain_for("shop", None, BuildProfile.development) == "shop-dev.apps.test"
    assert proxy.path_prefix_for("acme", "shop", None, BuildProfile.release) == "/"


def test_caddy_configure_shared_writes_handle_path_snippet_and_base_site(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_CADDY_SITES_DIR", str(tmp_path))
    monkeypatch.setenv("PAAS_BASE_DOMAIN", "apps.test")
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))

    CaddyProxy().configure("shop", BuildProfile.release, "apps.test", "/acme/shop/", ENDPOINT, REDIRECTS)

    snippet = (tmp_path / "handles" / "shop.caddy").read_text(encoding="utf-8")
    assert "handle_path /acme/shop/* {" in snippet
    assert "reverse_proxy 127.0.0.1:8123" in snippet
    assert "redir /old /new 301" in snippet
    assert "rewrite /internal /v2/internal" in snippet

    base_site = (tmp_path / "_base.caddy").read_text(encoding="utf-8")
    assert "apps.test {" in base_site
    assert "import" in base_site and "handles" in base_site


def test_caddy_configure_dedicated_domain_writes_full_site(monkeypatch, tmp_path, fresh_settings):
    """release + 커스텀 도메인 예외만 기존처럼 독립된 최상위 사이트 파일을 쓴다."""
    monkeypatch.setenv("PAAS_CADDY_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))

    CaddyProxy().configure("shop", BuildProfile.release, "shop.example.com", "/", ENDPOINT, REDIRECTS)
    content = (tmp_path / "shop.caddy").read_text(encoding="utf-8")
    assert "shop.example.com {" in content
    assert "reverse_proxy 127.0.0.1:8123" in content
    assert "redir /old /new 301" in content
    assert not (tmp_path / "handles" / "shop.caddy").exists()


def test_caddy_remove_deletes_both_shared_and_dedicated_files(tmp_path, monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_CADDY_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    dedicated = tmp_path / "shop.caddy"
    dedicated.write_text("x", encoding="utf-8")
    (tmp_path / "handles").mkdir()
    snippet = tmp_path / "handles" / "shop.caddy"
    snippet.write_text("x", encoding="utf-8")

    CaddyProxy().remove("shop", BuildProfile.release)
    assert not dedicated.exists()
    assert not snippet.exists()


def test_iis_configure_shared_writes_fragment_and_regenerates_base(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    monkeypatch.setenv("PAAS_IIS_APPCMD_PATH", "appcmd.exe")
    monkeypatch.setenv("PAAS_BASE_DOMAIN", "apps.test")
    get_settings.cache_clear()

    calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kw: (calls.append(args), _Ok())[1],
    )

    IISProxy().configure("shop", BuildProfile.release, "apps.test", "/acme/shop/", ENDPOINT, REDIRECTS)

    fragment = (tmp_path / "sites" / "_base" / "routes" / "shop.xml").read_text(encoding="utf-8")
    assert 'match url="^acme/shop/(.*)"' in fragment
    assert "http://127.0.0.1:8123/{R:1}" in fragment
    assert 'match url="^acme/shop/old$"' in fragment  # redirect가 조직/프로젝트 접두사를 명시적으로 반영

    base_config = (tmp_path / "sites" / "_base" / "web.config").read_text(encoding="utf-8")
    assert "acme/shop" in base_config
    assert any("_base" in a for call in calls for a in call)


def test_iis_configure_dedicated_domain_writes_own_site(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    monkeypatch.setenv("PAAS_IIS_APPCMD_PATH", "appcmd.exe")
    get_settings.cache_clear()

    calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kw: (calls.append(args), _Ok())[1],
    )

    IISProxy().configure("shop", BuildProfile.release, "shop.example.com", "/", ENDPOINT, REDIRECTS)

    web_config = (tmp_path / "sites" / "shop" / "web.config").read_text(encoding="utf-8")
    assert 'redirectType="Permanent"' in web_config
    assert 'action type="Rewrite" url="/v2/internal"' in web_config
    assert "http://127.0.0.1:8123/{R:1}" in web_config

    # ARR(Application Request Routing) 프록시 기능이 사이트 생성 전에 켜져야 한다 —
    # URL Rewrite만으로는 절대 URL(http://127.0.0.1:{port}/...) target을 실제로 전달 못 함.
    assert calls[0][1:3] == ["set", "config"]
    assert calls[1][1:3] == ["delete", "site"]
    assert calls[2][1:3] == ["add", "site"]
    assert any("/bindings:http/*:80:shop.example.com" in a for a in calls[2])


def test_iis_configure_raises_clear_error_when_arr_not_installed(monkeypatch, tmp_path, fresh_settings):
    """ARR 미설치 시 URL Rewrite 규칙은 매칭되지만 응답이 안 오는(502/무응답) 상태로
    조용히 배포가 "성공"하면 안 된다 — appcmd가 실패하면 바로 명확한 에러로 드러난다."""
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    monkeypatch.setenv("PAAS_IIS_APPCMD_PATH", "appcmd.exe")
    get_settings.cache_clear()

    def fake_run(args, **kw):
        if args[1:3] == ["set", "config"]:
            return _Fail()
        return _Ok()

    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        IISProxy().configure("shop", BuildProfile.release, "shop.example.com", "/", ENDPOINT, [])
        raised = False
    except Exception as e:
        raised = True
        assert "ARR" in str(e)
    assert raised


def test_iis_configure_raises_on_add_failure(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    get_settings.cache_clear()

    def fake_run(args, **kw):
        if "add" in args:
            return _Fail()
        return _Ok()

    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        IISProxy().configure("shop", BuildProfile.release, "shop.example.com", "/", ENDPOINT, [])
        raised = False
    except Exception:
        raised = True
    assert raised


def test_iis_remove_deletes_fragment_and_dedicated_site(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    monkeypatch.setenv("PAAS_IIS_APPCMD_PATH", "appcmd.exe")
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Ok())

    IISProxy().configure("shop", BuildProfile.release, "apps.test", "/acme/shop/", ENDPOINT, [])
    fragment = tmp_path / "sites" / "_base" / "routes" / "shop.xml"
    assert fragment.exists()

    IISProxy().remove("shop", BuildProfile.release)
    assert not fragment.exists()


def test_apache_configure_shared_writes_handle_fragment(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_APACHE_SITES_DIR", str(tmp_path))
    monkeypatch.setenv("PAAS_BASE_DOMAIN", "apps.test")
    get_settings.cache_clear()
    reload_calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kw: (reload_calls.append(args), _Ok())[1],
    )

    ApacheProxy().configure("shop", BuildProfile.release, "apps.test", "/acme/shop/", ENDPOINT, REDIRECTS)

    fragment = (tmp_path / "handles" / "shop.conf").read_text(encoding="utf-8")
    assert "ProxyPass /acme/shop/ http://127.0.0.1:8123/" in fragment
    assert "Redirect 301 /acme/shop/old /acme/shop/new" in fragment
    assert reload_calls

    base_conf = (tmp_path / "_base.conf").read_text(encoding="utf-8")
    assert "ServerName apps.test" in base_conf
    assert "IncludeOptional" in base_conf and "handles" in base_conf
    assert not (tmp_path / "shop.conf").exists()


def test_apache_configure_dedicated_domain_writes_own_vhost(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_APACHE_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Ok())

    ApacheProxy().configure("shop", BuildProfile.release, "shop.example.com", "/", ENDPOINT, REDIRECTS)

    conf = (tmp_path / "shop.conf").read_text(encoding="utf-8")
    assert "ServerName shop.example.com" in conf
    assert "ProxyPass / http://127.0.0.1:8123/" in conf
    assert "Redirect 301 /old /new" in conf
    assert "RewriteEngine On" in conf
    assert "RewriteRule ^/internal$ /v2/internal [L]" in conf


def test_apache_reload_missing_binary_is_silent(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_APACHE_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    ApacheProxy().configure("shop", BuildProfile.release, "shop.example.com", "/", ENDPOINT, [])  # 예외 없이 통과


def test_apache_remove_deletes_dedicated_and_shared_fragment(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_APACHE_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Ok())

    ApacheProxy().configure("shop", BuildProfile.release, "apps.test", "/acme/shop/", ENDPOINT, [])
    fragment = tmp_path / "handles" / "shop.conf"
    assert fragment.exists()

    ApacheProxy().remove("shop", BuildProfile.release)
    assert not fragment.exists()


def test_caddy_configure_paths_splits_by_prefix_shared(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_CADDY_SITES_DIR", str(tmp_path))
    monkeypatch.setenv("PAAS_BASE_DOMAIN", "apps.test")
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))

    CaddyProxy().configure_paths(
        "shop", BuildProfile.release, "apps.test", _composite_routes("/acme/shop/"), [],
    )
    content = (tmp_path / "handles" / "shop.caddy").read_text(encoding="utf-8")
    assert "handle_path /acme/shop/api/* {" in content
    assert "reverse_proxy 127.0.0.1:8001" in content
    assert "reverse_proxy 127.0.0.1:8002" in content
    # 구체적 경로(api)가 캐치올(/acme/shop/*)보다 먼저 와야 한다
    assert content.index("handle_path /acme/shop/api/*") < content.index("reverse_proxy 127.0.0.1:8002")


def test_iis_configure_paths_routes_prefix_before_catchall_shared(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    monkeypatch.setenv("PAAS_IIS_APPCMD_PATH", "appcmd.exe")
    monkeypatch.setenv("PAAS_BASE_DOMAIN", "apps.test")
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Ok())

    IISProxy().configure_paths(
        "shop", BuildProfile.release, "apps.test", _composite_routes("/acme/shop/"), [],
    )
    fragment = (tmp_path / "sites" / "_base" / "routes" / "shop.xml").read_text(encoding="utf-8")
    assert 'match url="^acme/shop/api/(.*)"' in fragment
    assert "http://127.0.0.1:8001/{R:1}" in fragment  # backend (prefix rule)
    assert "http://127.0.0.1:8002/{R:1}" in fragment  # frontend (catch-all)
    assert fragment.index('name="shop-path-0"') < fragment.index('name="shop-path-1"')


def test_apache_configure_paths_proxies_prefix_before_root_shared(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_APACHE_SITES_DIR", str(tmp_path))
    monkeypatch.setenv("PAAS_BASE_DOMAIN", "apps.test")
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Ok())

    ApacheProxy().configure_paths(
        "shop", BuildProfile.release, "apps.test", _composite_routes("/acme/shop/"), [],
    )
    fragment = (tmp_path / "handles" / "shop.conf").read_text(encoding="utf-8")
    assert "ProxyPass /acme/shop/api/ http://127.0.0.1:8001/" in fragment
    assert "ProxyPass /acme/shop/ http://127.0.0.1:8002/" in fragment
    assert fragment.index("ProxyPass /acme/shop/api/") < fragment.index("ProxyPass /acme/shop/ http")


class _Ok:
    returncode = 0
    stdout = ""
    stderr = ""


class _Fail:
    returncode = 1
    stdout = ""
    stderr = "boom"
