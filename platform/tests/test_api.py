"""API 인증·프로젝트 CRUD·웹훅 서명·시크릿 마스킹 검증 (런타임 호출 없는 경로만)."""
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app.main import create_app

ADMIN = {"x-api-key": "test-admin-key"}


def _client() -> TestClient:
    return TestClient(create_app())


def test_requires_api_key():
    c = _client()
    assert c.get("/projects").status_code == 401
    assert c.get("/projects", headers={"x-api-key": "wrong"}).status_code == 401


def test_project_crud_and_env_masking():
    c = _client()
    body = {
        "name": "shop-front",
        "type": "react",
        "git_url": "https://git.example.com/org/shop-front",
    }
    r = c.post("/projects", json=body, headers=ADMIN)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["default_profile"] == "release"

    assert c.post("/projects", json=body, headers=ADMIN).status_code == 409

    r = c.put(f"/projects/{pid}/env", json={"key": "API_TOKEN", "value": "s3cret"}, headers=ADMIN)
    assert r.status_code == 204
    r = c.get(f"/projects/{pid}/env", headers=ADMIN)
    assert r.json() == [{"key": "API_TOKEN", "is_secret": True, "value": "•••"}]


def test_issue_key_and_use_it():
    c = _client()
    r = c.post("/keys", json={"name": "ci-bot"}, headers=ADMIN)
    assert r.status_code == 201
    issued = r.json()["key"]
    assert issued.startswith("paas_")
    assert c.get("/projects", headers={"x-api-key": issued}).status_code == 200
    # 일반 키로는 관리자 엔드포인트 접근 불가
    assert c.get("/audit", headers={"x-api-key": issued}).status_code == 403


def test_webhook_signature_required():
    c = _client()
    payload = {"ref": "refs/heads/main", "repository": {"clone_url": "https://x/y/z.git"}}
    raw = json.dumps(payload).encode()

    r = c.post("/webhooks/git", content=raw, headers={"x-hub-signature-256": "sha256=bad"})
    assert r.status_code == 401

    sig = hmac.new(b"test-webhook-secret", raw, hashlib.sha256).hexdigest()
    r = c.post(
        "/webhooks/git", content=raw,
        headers={"x-hub-signature-256": f"sha256={sig}",
                 "content-type": "application/json"},
    )
    assert r.status_code == 200
    assert "skipped" in r.json()


def test_audit_trail_recorded():
    c = _client()
    c.post("/projects", json={
        "name": "audit-target", "type": "python",
        "git_url": "https://git.example.com/org/api",
    }, headers=ADMIN)
    rows = c.get("/audit", headers=ADMIN).json()
    assert any(r["action"] == "project.create" and r["target"] == "audit-target" for r in rows)
