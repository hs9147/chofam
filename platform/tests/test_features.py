"""기능 모듈 설치 옵션(PAAS_FEATURES) — 비활성 모듈 404, /health 반영 검증."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

ADMIN = {"x-api-key": "test-admin-key"}


def _client(monkeypatch, features: str) -> TestClient:
    monkeypatch.setenv("PAAS_FEATURES", features)
    get_settings.cache_clear()
    return TestClient(create_app())


def test_default_enables_all(monkeypatch, fresh_settings):
    c = _client(monkeypatch, "deploy,workspace,mail,payment")
    assert c.get("/health").json()["features"] == ["deploy", "mail", "payment", "workspace"]


def test_deploy_only_hides_other_modules(monkeypatch, fresh_settings):
    c = _client(monkeypatch, "deploy")
    assert c.get("/health").json()["features"] == ["deploy"]
    # core는 살아있음
    assert c.get("/projects", headers=ADMIN).status_code == 200
    assert c.get("/modules", headers=ADMIN).status_code == 200
    # 비활성 모듈 라우터는 미마운트 → 404
    assert c.get("/llm/providers", headers=ADMIN).status_code == 404
    assert c.get("/payments", headers=ADMIN).status_code == 404
    assert c.post("/chat/sessions", json={"project_id": 1, "provider_id": 1},
                  headers=ADMIN).status_code == 404


def test_deploy_endpoints_gated_when_disabled(monkeypatch, fresh_settings):
    c = _client(monkeypatch, "workspace")
    r = c.post("/projects", json={
        "name": "no-deploy", "type": "python", "git_url": "https://git.example.com/x",
    }, headers=ADMIN)
    assert r.status_code == 201  # 프로젝트 CRUD는 core
    pid = r.json()["id"]
    assert c.post(f"/projects/{pid}/deploy", json={}, headers=ADMIN).status_code == 404
    assert c.get(f"/projects/{pid}/deployments", headers=ADMIN).status_code == 404
    # 웹훅·프리뷰 라우터도 미마운트
    assert c.post("/webhooks/git", content=b"{}").status_code == 404
    assert c.get(f"/projects/{pid}/previews", headers=ADMIN).status_code == 404


def test_unknown_feature_rejected(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_FEATURES", "deploy,nonsense")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="nonsense"):
        create_app()
