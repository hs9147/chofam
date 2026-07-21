"""Gitea → 플랫폼 조직/프로젝트 동기화 — services/gitea_sync.py, POST /orgs/sync."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.main import create_app
from app.models import Organization, Project
from app.services import gitea, gitea_sync

ADMIN = {"x-api-key": "test-admin-key"}


@pytest.fixture(autouse=True)
def _configured(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_GITEA_URL", "https://git.example.com")
    monkeypatch.setenv("PAAS_GITEA_API_TOKEN", "tok-123")
    get_settings.cache_clear()
    create_app()  # Base.metadata.create_all(engine) — SessionLocal을 직접 여는 테스트용
    yield
    get_settings.cache_clear()


def test_sync_creates_missing_org_and_python_project(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(gitea, "list_orgs", lambda: [{"username": "acme"}])
    monkeypatch.setattr(
        gitea, "list_org_repos",
        lambda org: [{"name": "billing-api", "clone_url": "https://git.example.com/acme/billing-api.git",
                      "default_branch": "main"}],
    )

    def fake_clone(git_url, branch):
        d = tmp_path_factory.mktemp("billing-api")
        (d / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
        return d

    monkeypatch.setattr(gitea_sync, "_shallow_clone", fake_clone)

    with SessionLocal() as db:
        result = gitea_sync.sync_from_gitea(db)
        assert result["orgs_created"] == ["acme"]
        assert result["projects_created"] == ["billing-api"]
        assert result["skipped"] == []

        org = db.execute(select(Organization).where(Organization.name == "acme")).scalar_one()
        project = db.execute(select(Project).where(Project.name == "billing-api")).scalar_one()
        assert project.organization_id == org.id
        assert project.type.value == "python"
        assert project.git_url == "https://git.example.com/acme/billing-api.git"
        assert project.branch == "main"


def test_sync_reuses_existing_org_skips_existing_project(monkeypatch):
    with SessionLocal() as db:
        org = Organization(name="acme")
        db.add(org)
        db.commit()
        db.add(Project(name="already-here", type="python", organization_id=org.id,
                        git_url="https://git.example.com/acme/already-here.git"))
        db.commit()

    monkeypatch.setattr(gitea, "list_orgs", lambda: [{"username": "acme"}])
    monkeypatch.setattr(
        gitea, "list_org_repos",
        lambda org_name: [{"name": "already-here", "clone_url": "x", "default_branch": "main"}],
    )
    monkeypatch.setattr(
        gitea_sync, "_shallow_clone",
        lambda *a: (_ for _ in ()).throw(AssertionError("should not clone an already-known repo")),
    )

    with SessionLocal() as db:
        result = gitea_sync.sync_from_gitea(db)
        assert result["orgs_created"] == []  # 이미 있던 조직 재사용
        assert result["projects_created"] == []
        assert result["skipped"] == []
        assert len(db.execute(select(Organization)).scalars().all()) == 1  # 중복 생성 없음


def test_sync_skips_project_when_type_unrecognizable(monkeypatch, tmp_path_factory):
    monkeypatch.setattr(gitea, "list_orgs", lambda: [{"username": "acme"}])
    monkeypatch.setattr(
        gitea, "list_org_repos",
        lambda org: [{"name": "mystery", "clone_url": "https://git.example.com/acme/mystery.git",
                      "default_branch": "main"}],
    )
    monkeypatch.setattr(gitea_sync, "_shallow_clone", lambda *a: tmp_path_factory.mktemp("mystery"))

    with SessionLocal() as db:
        result = gitea_sync.sync_from_gitea(db)
        assert result["projects_created"] == []
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["name"] == "mystery"
        assert result["skipped"][0]["kind"] == "project"
        assert "추론" in result["skipped"][0]["reason"]


def test_sync_skips_invalid_names(monkeypatch):
    monkeypatch.setattr(gitea, "list_orgs", lambda: [{"username": "Bad_Org"}])
    monkeypatch.setattr(gitea, "list_org_repos", lambda org: [])

    with SessionLocal() as db:
        result = gitea_sync.sync_from_gitea(db)
        assert result["orgs_created"] == []
        assert result["skipped"] == [{"name": "Bad_Org", "kind": "org", "reason": "이름 규칙에 맞지 않음"}]


def test_sync_skips_project_on_clone_failure(monkeypatch):
    monkeypatch.setattr(gitea, "list_orgs", lambda: [{"username": "acme"}])
    monkeypatch.setattr(
        gitea, "list_org_repos",
        lambda org: [{"name": "unreachable", "clone_url": "https://git.example.com/acme/unreachable.git",
                      "default_branch": "main"}],
    )

    def fail_clone(*a):
        raise RuntimeError("fatal: repository not found")

    monkeypatch.setattr(gitea_sync, "_shallow_clone", fail_clone)

    with SessionLocal() as db:
        result = gitea_sync.sync_from_gitea(db)
        assert result["projects_created"] == []
        assert result["skipped"][0]["name"] == "unreachable"
        assert "clone 실패" in result["skipped"][0]["reason"]


def test_sync_endpoint_admin_only(monkeypatch):
    monkeypatch.setattr(gitea, "list_orgs", lambda: [])
    c = TestClient(create_app())
    r = c.post("/paas/api/v1/orgs/sync", headers=ADMIN)
    assert r.status_code == 200, r.text
    assert r.json() == {"orgs_created": [], "projects_created": [], "skipped": []}

    member_key = c.post("/paas/api/v1/keys", json={"name": "dev"}, headers=ADMIN).json()["key"]
    r2 = c.post("/paas/api/v1/orgs/sync", headers={"x-api-key": member_key})
    assert r2.status_code == 403


def test_sync_endpoint_maps_not_configured_to_503(fresh_settings, monkeypatch):
    monkeypatch.delenv("PAAS_GITEA_URL", raising=False)
    get_settings.cache_clear()
    c = TestClient(create_app())
    r = c.post("/paas/api/v1/orgs/sync", headers=ADMIN)
    assert r.status_code == 503
