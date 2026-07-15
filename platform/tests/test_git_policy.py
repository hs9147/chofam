"""기업용 거버넌스 — PAAS_GIT_INTERNAL_ONLY 시 프로젝트 git_url을 사내 Gitea로 한정."""
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app
from app.git_policy import enforce_internal_git_url

ADMIN = {"x-api-key": "test-admin-key"}


def _client(monkeypatch, gitea_url: str = "https://git.example.com", internal_only: str = "true"):
    monkeypatch.setenv("PAAS_GIT_INTERNAL_ONLY", internal_only)
    if gitea_url:
        monkeypatch.setenv("PAAS_GITEA_URL", gitea_url)
    get_settings.cache_clear()
    return TestClient(create_app())


def test_disabled_by_default_any_host_allowed(fresh_settings):
    get_settings.cache_clear()
    c = TestClient(create_app())
    r = c.post("/projects", json={
        "name": "ext-app", "type": "python", "git_url": "https://github.com/org/repo",
    }, headers=ADMIN)
    assert r.status_code == 201


def test_external_host_rejected_when_enabled(monkeypatch, fresh_settings):
    c = _client(monkeypatch)
    r = c.post("/projects", json={
        "name": "ext-app", "type": "python", "git_url": "https://github.com/org/repo",
    }, headers=ADMIN)
    assert r.status_code == 422
    assert "git.example.com" in r.text


def test_internal_host_allowed_when_enabled(monkeypatch, fresh_settings):
    c = _client(monkeypatch)
    r = c.post("/projects", json={
        "name": "int-app", "type": "python",
        "git_url": "https://git.example.com/org/repo",
    }, headers=ADMIN)
    assert r.status_code == 201


def test_ssh_scp_form_host_matches(monkeypatch, fresh_settings):
    c = _client(monkeypatch)
    r = c.post("/projects", json={
        "name": "ssh-app", "type": "python",
        "git_url": "git@git.example.com:org/repo.git",
    }, headers=ADMIN)
    assert r.status_code == 201


def test_ssh_scp_form_wrong_host_rejected(monkeypatch, fresh_settings):
    c = _client(monkeypatch)
    r = c.post("/projects", json={
        "name": "ssh-bad", "type": "python", "git_url": "git@github.com:org/repo.git",
    }, headers=ADMIN)
    assert r.status_code == 422


def test_enabled_without_gitea_url_gives_clear_error(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_GIT_INTERNAL_ONLY", "true")
    monkeypatch.delenv("PAAS_GITEA_URL", raising=False)
    get_settings.cache_clear()
    c = TestClient(create_app())
    r = c.post("/projects", json={
        "name": "misconfigured", "type": "python", "git_url": "https://git.example.com/org/repo",
    }, headers=ADMIN)
    assert r.status_code == 503
    assert "PAAS_GITEA_URL" in r.text


def test_helper_noop_when_disabled(fresh_settings):
    get_settings.cache_clear()
    enforce_internal_git_url("https://anywhere.example.com/x")  # 예외 없이 통과해야 함
