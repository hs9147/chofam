"""서버구성 시각화 + redirect/rewrite 규칙 CRUD."""
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.services import deployer, gitea

ADMIN = {"x-api-key": "test-admin-key"}


class _FakeRuntime:
    def status(self, *a):
        return "running"


def _client() -> TestClient:
    return TestClient(create_app())


def _create_project(c: TestClient, name="shop-web") -> int:
    return c.post("/paas/api/v1/projects", json={
        "name": name, "type": "react", "git_url": "https://git.example.com/x",
    }, headers=ADMIN).json()["id"]


def test_server_config_defaults(monkeypatch, fresh_settings):
    monkeypatch.setattr(deployer, "get_runtime", lambda: _FakeRuntime())
    c = _client()
    pid = _create_project(c)
    r = c.get("/paas/api/v1/server-config", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["runtime_backend"] == "docker"
    assert body["proxy_backend"] == "caddy"
    profiles = {s["profile"] for s in body["sites"] if s["project_id"] == pid}
    assert profiles == {"release", "development"}
    release = next(s for s in body["sites"] if s["project_id"] == pid and s["profile"] == "release")
    assert release["domain"] == "apps.test"
    assert release["path_prefix"] == "/apps/_/shop-web/"  # organization_id 없는 프로젝트 — 조직 자리는 "_"
    assert release["status"] == "running"
    assert release["redirect_count"] == 0


def test_server_config_path_prefix_uses_organization_name(monkeypatch, fresh_settings):
    """조직 소속 프로젝트는 서브패스에 조직 이름이 들어간다 — /_/{project}/가 아니라
    /{조직}/{프로젝트}/ (services/proxy/__init__.py의 path_prefix_for)."""
    monkeypatch.setattr(deployer, "get_runtime", lambda: _FakeRuntime())
    monkeypatch.setenv("PAAS_GITEA_URL", "https://git.example.com")
    monkeypatch.setenv("PAAS_GITEA_API_TOKEN", "tok-123")
    get_settings.cache_clear()
    monkeypatch.setattr(gitea.httpx, "post", lambda url, **kw: type(
        "R", (), {"status_code": 201, "text": "",
                  "json": lambda self=None: {"clone_url": "https://git.example.com/acme/api.git"}}
    )())

    c = _client()
    org_id = c.post("/paas/api/v1/orgs", json={"name": "acme"}, headers=ADMIN).json()["id"]
    pid = c.post("/paas/api/v1/projects", json={
        "name": "shop", "type": "react", "organization_id": org_id,
    }, headers=ADMIN).json()["id"]

    body = c.get("/paas/api/v1/server-config", headers=ADMIN).json()
    release = next(s for s in body["sites"] if s["project_id"] == pid and s["profile"] == "release")
    dev = next(s for s in body["sites"] if s["project_id"] == pid and s["profile"] == "development")
    assert release["path_prefix"] == "/apps/acme/shop/"
    assert dev["path_prefix"] == "/apps/acme/shop/dev/"


def test_server_config_reflects_backend_settings(monkeypatch, fresh_settings):
    from app.config import get_settings

    monkeypatch.setattr(deployer, "get_runtime", lambda: _FakeRuntime())
    monkeypatch.setenv("PAAS_RUNTIME_BACKEND", "windows_service")
    monkeypatch.setenv("PAAS_PROXY_BACKEND", "iis")
    get_settings.cache_clear()
    c = _client()
    body = c.get("/paas/api/v1/server-config", headers=ADMIN).json()
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
    r = c.get("/paas/api/v1/server-config", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert all(s["status"].startswith("unknown") for s in r.json()["sites"])


def test_server_config_composite_project_shows_components(monkeypatch, fresh_settings):
    monkeypatch.setattr(deployer, "get_runtime", lambda: _FakeRuntime())
    c = _client()
    pid = c.post("/paas/api/v1/projects", json={
        "name": "shop-app", "type": "composite", "git_url": "https://git.example.com/x",
    }, headers=ADMIN).json()["id"]

    body = c.get("/paas/api/v1/server-config", headers=ADMIN).json()
    release = next(s for s in body["sites"] if s["project_id"] == pid and s["profile"] == "release")
    assert release["status"] == "running"  # backend/frontend 둘 다 running이면 요약도 running
    assert {c["name"] for c in release["components"]} == {"backend", "frontend"}
    assert all(c["status"] == "running" for c in release["components"])

    # 일반 프로젝트는 components가 없다(None)
    other_pid = _create_project(c, "shop-plain")
    body = c.get("/paas/api/v1/server-config", headers=ADMIN).json()
    plain = next(s for s in body["sites"] if s["project_id"] == other_pid)
    assert plain.get("components") is None


def test_server_config_composite_partial_status_summarized_as_partial(monkeypatch, fresh_settings):
    class _MixedRuntime:
        def status(self, name, *a):
            return "failed" if name.endswith("-frontend") else "running"

    monkeypatch.setattr(deployer, "get_runtime", lambda: _MixedRuntime())
    c = _client()
    pid = c.post("/paas/api/v1/projects", json={
        "name": "shop-mixed", "type": "composite", "git_url": "https://git.example.com/x",
    }, headers=ADMIN).json()["id"]

    body = c.get("/paas/api/v1/server-config", headers=ADMIN).json()
    release = next(s for s in body["sites"] if s["project_id"] == pid and s["profile"] == "release")
    assert release["status"] == "partial"
    statuses = {c["name"]: c["status"] for c in release["components"]}
    assert statuses == {"backend": "running", "frontend": "failed"}


def test_redirect_crud_flow(fresh_settings):
    c = _client()
    pid = _create_project(c)

    r = c.post(f"/paas/api/v1/projects/{pid}/redirects", json={
        "from_path": "/old", "to_path": "/new", "kind": "redirect", "status_code": 301,
    }, headers=ADMIN)
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["project_id"] == pid
    assert rule["kind"] == "redirect"

    listing = c.get(f"/paas/api/v1/projects/{pid}/redirects", headers=ADMIN).json()
    assert len(listing) == 1

    server_cfg = c.get("/paas/api/v1/server-config", headers=ADMIN).json()
    release = next(s for s in server_cfg["sites"] if s["project_id"] == pid and s["profile"] == "release")
    assert release["redirect_count"] == 1

    assert c.delete(f"/paas/api/v1/redirects/{rule['id']}", headers=ADMIN).status_code == 204
    assert c.get(f"/paas/api/v1/projects/{pid}/redirects", headers=ADMIN).json() == []


def test_redirect_defaults_kind_and_status(fresh_settings):
    c = _client()
    pid = _create_project(c)
    r = c.post(f"/paas/api/v1/projects/{pid}/redirects", json={
        "from_path": "/a", "to_path": "/b",
    }, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["kind"] == "redirect"
    assert r.json()["status_code"] == 302


def test_redirect_rewrite_kind(fresh_settings):
    c = _client()
    pid = _create_project(c)
    r = c.post(f"/paas/api/v1/projects/{pid}/redirects", json={
        "from_path": "/internal", "to_path": "/v2/internal", "kind": "rewrite",
    }, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["kind"] == "rewrite"


def test_redirect_unknown_project_404(fresh_settings):
    c = _client()
    r = c.post("/paas/api/v1/projects/999999/redirects", json={"from_path": "/a", "to_path": "/b"}, headers=ADMIN)
    assert r.status_code == 404
    assert c.get("/paas/api/v1/projects/999999/redirects", headers=ADMIN).status_code == 404


def test_delete_unknown_redirect_404(fresh_settings):
    c = _client()
    assert c.delete("/paas/api/v1/redirects/999999", headers=ADMIN).status_code == 404
