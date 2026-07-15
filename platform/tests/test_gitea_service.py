"""Gitea REST API 클라이언트 — 멱등 생성, 설정 누락/실패 경로."""
import pytest

from app.config import get_settings
from app.services import gitea


class _Res:
    def __init__(self, status: int, body: dict | None = None, text: str = ""):
        self.status_code = status
        self._body = body or {}
        self.text = text or str(body)

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def _configured(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_GITEA_URL", "https://git.example.com")
    monkeypatch.setenv("PAAS_GITEA_API_TOKEN", "tok-123")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ensure_org_created(monkeypatch):
    calls = []
    monkeypatch.setattr(gitea.httpx, "post", lambda url, **kw: (calls.append((url, kw)), _Res(201))[1])
    gitea.ensure_org("shop-team")
    url, kw = calls[0]
    assert url == "https://git.example.com/api/v1/orgs"
    assert kw["headers"]["Authorization"] == "token tok-123"
    assert kw["json"]["username"] == "shop-team"


def test_ensure_org_already_exists_is_idempotent(monkeypatch):
    monkeypatch.setattr(gitea.httpx, "post", lambda url, **kw: _Res(422))
    gitea.ensure_org("shop-team")  # 예외 없이 통과해야 함


def test_ensure_org_other_error_raises(monkeypatch):
    monkeypatch.setattr(gitea.httpx, "post", lambda url, **kw: _Res(500, text="boom"))
    with pytest.raises(gitea.GiteaError, match="500"):
        gitea.ensure_org("shop-team")


def test_ensure_repo_created_returns_clone_url(monkeypatch):
    monkeypatch.setattr(
        gitea.httpx, "post",
        lambda url, **kw: _Res(201, {"clone_url": "https://git.example.com/shop-team/api.git"}),
    )
    url = gitea.ensure_repo("shop-team", "api")
    assert url == "https://git.example.com/shop-team/api.git"


def test_ensure_repo_conflict_reuses_existing(monkeypatch):
    monkeypatch.setattr(gitea.httpx, "post", lambda url, **kw: _Res(409))
    monkeypatch.setattr(
        gitea.httpx, "get",
        lambda url, **kw: _Res(200, {"clone_url": "https://git.example.com/shop-team/api.git"}),
    )
    url = gitea.ensure_repo("shop-team", "api")
    assert url == "https://git.example.com/shop-team/api.git"


def test_not_configured_raises_specific_error(monkeypatch, fresh_settings):
    monkeypatch.delenv("PAAS_GITEA_URL", raising=False)
    get_settings.cache_clear()
    with pytest.raises(gitea.GiteaNotConfigured):
        gitea.ensure_org("x")
