"""서버구성 시각화 + redirect/rewrite 규칙 CRUD."""
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import deployer

ADMIN = {"x-api-key": "test-admin-key"}


class _FakeRuntime:
    def status(self, *a):
        return "running"


def _client() -> TestClient:
    return TestClient(create_app())


def _create_project(c: TestClient, name="shop-web") -> int:
    return c.post("/projects", json={
        "name": name, "type": "react", "git_url": "https://git.example.com/x",
    }, headers=ADMIN).json()["id"]


def test_server_config_defaults(monkeypatch, fresh_settings):
    monkeypatch.setattr(deployer, "get_runtime", lambda: _FakeRuntime())
    c = _client()
    pid = _create_project(c)
    r = c.get("/server-config", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["runtime_backend"] == "docker"
    assert body["proxy_backend"] == "caddy"
    profiles = {s["profile"] for s in body["sites"] if s["project_id"] == pid}
    assert profiles == {"release", "development"}
    release = next(s for s in body["sites"] if s["project_id"] == pid and s["profile"] == "release")
    assert release["domain"] == "shop-web.apps.test"
    assert release["status"] == "running"
    assert release["redirect_count"] == 0


def test_server_config_reflects_backend_settings(monkeypatch, fresh_settings):
    from app.config import get_settings

    monkeypatch.setattr(deployer, "get_runtime", lambda: _FakeRuntime())
    monkeypatch.setenv("PAAS_RUNTIME_BACKEND", "windows_service")
    monkeypatch.setenv("PAAS_PROXY_BACKEND", "iis")
    get_settings.cache_clear()
    c = _client()
    body = c.get("/server-config", headers=ADMIN).json()
    assert body["runtime_backend"] == "windows_service"
    assert body["proxy_backend"] == "iis"


def test_server_config_tolerates_runtime_errors(monkeypatch, fresh_settings):
    """런타임 상태 조회가 실패(예: docker SDK 미설치)해도 전체 화면이 500으로 죽지 않는다."""
    class _BrokenRuntime:
        def status(self, *a):
            raise RuntimeError("docker SDK가 설치되지 않았습니다")

    monkeypatch.setattr(deployer, "get_runtime", lambda: _BrokenRuntime())
    c = _client()
    _create_project(c)
    r = c.get("/server-config", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert all(s["status"].startswith("unknown") for s in r.json()["sites"])


def test_redirect_crud_flow(fresh_settings):
    c = _client()
    pid = _create_project(c)

    r = c.post(f"/projects/{pid}/redirects", json={
        "from_path": "/old", "to_path": "/new", "kind": "redirect", "status_code": 301,
    }, headers=ADMIN)
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["project_id"] == pid
    assert rule["kind"] == "redirect"

    listing = c.get(f"/projects/{pid}/redirects", headers=ADMIN).json()
    assert len(listing) == 1

    server_cfg = c.get("/server-config", headers=ADMIN).json()
    release = next(s for s in server_cfg["sites"] if s["project_id"] == pid and s["profile"] == "release")
    assert release["redirect_count"] == 1

    assert c.delete(f"/redirects/{rule['id']}", headers=ADMIN).status_code == 204
    assert c.get(f"/projects/{pid}/redirects", headers=ADMIN).json() == []


def test_redirect_defaults_kind_and_status(fresh_settings):
    c = _client()
    pid = _create_project(c)
    r = c.post(f"/projects/{pid}/redirects", json={
        "from_path": "/a", "to_path": "/b",
    }, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["kind"] == "redirect"
    assert r.json()["status_code"] == 302


def test_redirect_rewrite_kind(fresh_settings):
    c = _client()
    pid = _create_project(c)
    r = c.post(f"/projects/{pid}/redirects", json={
        "from_path": "/internal", "to_path": "/v2/internal", "kind": "rewrite",
    }, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["kind"] == "rewrite"


def test_redirect_unknown_project_404(fresh_settings):
    c = _client()
    r = c.post("/projects/999999/redirects", json={"from_path": "/a", "to_path": "/b"}, headers=ADMIN)
    assert r.status_code == 404
    assert c.get("/projects/999999/redirects", headers=ADMIN).status_code == 404


def test_delete_unknown_redirect_404(fresh_settings):
    c = _client()
    assert c.delete("/redirects/999999", headers=ADMIN).status_code == 404
