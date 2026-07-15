"""리버스프록시 백엔드 — Caddy(기존)/IIS/Apache 사이트 설정 생성 + redirect/rewrite 반영."""
import subprocess

from app.config import get_settings
from app.models import BuildProfile
from app.services import proxy
from app.services.proxy.apache_proxy import ApacheProxy
from app.services.proxy.base import RedirectSpec
from app.services.proxy.caddy_proxy import CaddyProxy
from app.services.proxy.iis_proxy import IISProxy
from app.services.runtime.base import Endpoint

ENDPOINT = Endpoint(host="127.0.0.1", port=8123)
REDIRECTS = [
    RedirectSpec(from_path="/old", to_path="/new", kind="redirect", status_code=301),
    RedirectSpec(from_path="/internal", to_path="/v2/internal", kind="rewrite"),
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


def test_domain_for_release_and_dev(fresh_settings):
    assert proxy.domain_for("shop", None, BuildProfile.release) == "shop.apps.test"
    assert proxy.domain_for("shop", "custom.example.com", BuildProfile.release) == "custom.example.com"
    assert proxy.domain_for("shop", "custom.example.com", BuildProfile.development) == "shop-dev.apps.test"


def test_caddy_configure_writes_site_with_redirects(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_CADDY_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))

    CaddyProxy().configure("shop", BuildProfile.release, "shop.apps.test", ENDPOINT, REDIRECTS)
    content = (tmp_path / "shop.caddy").read_text(encoding="utf-8")
    assert "shop.apps.test {" in content
    assert "reverse_proxy 127.0.0.1:8123" in content
    assert "redir /old /new 301" in content
    assert "rewrite /internal /v2/internal" in content


def test_caddy_remove_deletes_site_file(tmp_path, monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_CADDY_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    site = tmp_path / "shop.caddy"
    site.write_text("x", encoding="utf-8")

    CaddyProxy().remove("shop", BuildProfile.release)
    assert not site.exists()


def test_iis_configure_writes_web_config_and_calls_appcmd(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    monkeypatch.setenv("PAAS_IIS_APPCMD_PATH", "appcmd.exe")
    get_settings.cache_clear()

    calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kw: (calls.append(args), _Ok())[1],
    )

    IISProxy().configure("shop", BuildProfile.release, "shop.apps.test", ENDPOINT, REDIRECTS)

    web_config = (tmp_path / "sites" / "shop" / "web.config").read_text(encoding="utf-8")
    assert 'redirectType="Permanent"' in web_config
    assert 'action type="Rewrite" url="/v2/internal"' in web_config
    assert "http://127.0.0.1:8123/{R:1}" in web_config

    # delete-then-add 시퀀스
    assert calls[0][1:3] == ["delete", "site"]
    assert calls[1][1:3] == ["add", "site"]
    assert any("/bindings:http/*:80:shop.apps.test" in a for a in calls[1])


def test_iis_configure_raises_on_add_failure(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_IIS_SITES_ROOT", str(tmp_path / "sites"))
    get_settings.cache_clear()

    def fake_run(args, **kw):
        if "add" in args:
            return _Fail()
        return _Ok()

    monkeypatch.setattr(subprocess, "run", fake_run)
    try:
        IISProxy().configure("shop", BuildProfile.release, "shop.apps.test", ENDPOINT, [])
        raised = False
    except Exception:
        raised = True
    assert raised


def test_apache_configure_writes_vhost_and_reloads(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_APACHE_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    reload_calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda args, **kw: (reload_calls.append(args), _Ok())[1],
    )

    ApacheProxy().configure("shop", BuildProfile.release, "shop.apps.test", ENDPOINT, REDIRECTS)

    conf = (tmp_path / "shop.conf").read_text(encoding="utf-8")
    assert "ServerName shop.apps.test" in conf
    assert "ProxyPass / http://127.0.0.1:8123/" in conf
    assert "Redirect 301 /old /new" in conf
    assert "RewriteEngine On" in conf
    assert "RewriteRule ^/internal$ /v2/internal [L]" in conf
    assert reload_calls  # apachectl graceful 실행 시도됨


def test_apache_reload_missing_binary_is_silent(monkeypatch, tmp_path, fresh_settings):
    monkeypatch.setenv("PAAS_APACHE_SITES_DIR", str(tmp_path))
    get_settings.cache_clear()
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(FileNotFoundError()))
    ApacheProxy().configure("shop", BuildProfile.release, "shop.apps.test", ENDPOINT, [])  # 예외 없이 통과


class _Ok:
    returncode = 0
    stdout = ""
    stderr = ""


class _Fail:
    returncode = 1
    stdout = ""
    stderr = "boom"
