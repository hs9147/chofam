"""LLM/모듈 API 통합 — 프로바이더 키 마스킹, 채팅→diff 제안 생성, 리뷰 엔드포인트."""
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import llm as llm_service

ADMIN = {"x-api-key": "test-admin-key"}


def _client() -> TestClient:
    return TestClient(create_app())


def _create_provider(c: TestClient, name="claude") -> int:
    r = c.post("/llm/providers", json={
        "name": name, "kind": "external", "base_url": "https://api.example.com",
        "api_key": "sk-secret", "model": "test-model",
    }, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_project(c: TestClient, name="editor-target") -> int:
    r = c.post("/projects", json={
        "name": name, "type": "python", "git_url": "https://git.example.com/org/x",
    }, headers=ADMIN)
    return r.json()["id"]


def test_provider_key_never_exposed():
    c = _client()
    _create_provider(c)
    listing = c.get("/llm/providers", headers=ADMIN).json()
    assert listing[0]["has_api_key"] is True
    assert "sk-secret" not in str(listing)


def test_internal_provider_must_use_project_scheme():
    """보안수정 — kind=internal인데 base_url이 외부 URL이면 등록 자체를 거부한다."""
    c = _client()
    r = c.post("/llm/providers", json={
        "name": "fake-internal", "kind": "internal",
        "base_url": "https://api.some-external-llm.com", "model": "m",
    }, headers=ADMIN)
    assert r.status_code == 422
    assert "project://" in r.text


def test_internal_provider_with_project_scheme_succeeds():
    c = _client()
    r = c.post("/llm/providers", json={
        "name": "llm-main", "kind": "internal", "base_url": "project://llm-main", "model": "m",
    }, headers=ADMIN)
    assert r.status_code == 201


def _member_key(c: TestClient, name="dev1") -> dict:
    key = c.post("/keys", json={"name": name}, headers=ADMIN).json()["key"]
    return {"x-api-key": key}


def test_non_admin_key_blocked_from_external_provider_session():
    c = _client()
    pid = _create_project(c)
    prov = _create_provider(c)  # external
    r = c.post("/chat/sessions", json={"project_id": pid, "provider_id": prov},
               headers=_member_key(c))
    assert r.status_code == 403
    assert "admin" in r.text


def test_non_admin_key_allowed_for_internal_provider_session():
    c = _client()
    pid = _create_project(c)
    prov_id = c.post("/llm/providers", json={
        "name": "llm-internal", "kind": "internal", "base_url": "project://llm-internal",
        "model": "m",
    }, headers=ADMIN).json()["id"]
    r = c.post("/chat/sessions", json={"project_id": pid, "provider_id": prov_id},
               headers=_member_key(c))
    assert r.status_code == 200


def test_non_admin_key_blocked_from_external_review():
    c = _client()
    pid = _create_project(c)
    prov = _create_provider(c)  # external
    r = c.post(f"/projects/{pid}/review",
               json={"provider_id": prov, "diff": "--- a/x\n+++ b/x\n"},
               headers=_member_key(c))
    assert r.status_code == 403


def test_admin_key_still_allowed_for_external_session():
    c = _client()
    pid = _create_project(c)
    prov = _create_provider(c)
    r = c.post("/chat/sessions", json={"project_id": pid, "provider_id": prov}, headers=ADMIN)
    assert r.status_code == 200


def test_chat_message_creates_proposed_change(monkeypatch):
    reply = "수정했습니다.\n```diff\n--- a/m.py\n+++ b/m.py\n@@ -1 +1 @@\n-x\n+y\n```"
    monkeypatch.setattr(
        llm_service, "_post_chat",
        lambda url, headers, payload: {"choices": [{"message": {"content": reply}}]},
    )
    c = _client()
    pid = _create_project(c)
    prov = _create_provider(c)

    r = c.post("/chat/sessions", json={"project_id": pid, "provider_id": prov}, headers=ADMIN)
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["branch"] == f"paas/chat-{sid}"

    r = c.post(f"/chat/sessions/{sid}/messages",
               json={"content": "m.py의 x를 y로 바꿔줘"}, headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["proposed_change_id"] is not None
    assert "```diff" in body["reply"]

    # reject 후 재적용 시도는 409
    cid = body["proposed_change_id"]
    assert c.post(f"/changes/{cid}/reject", headers=ADMIN).status_code == 204
    assert c.post(f"/changes/{cid}/apply", headers=ADMIN).status_code == 409


def test_chat_without_diff_makes_no_change(monkeypatch):
    monkeypatch.setattr(
        llm_service, "_post_chat",
        lambda url, headers, payload: {"choices": [{"message": {"content": "질문에 대한 답변만."}}]},
    )
    c = _client()
    pid = _create_project(c)
    prov = _create_provider(c)
    sid = c.post("/chat/sessions", json={"project_id": pid, "provider_id": prov},
                 headers=ADMIN).json()["id"]
    body = c.post(f"/chat/sessions/{sid}/messages",
                  json={"content": "이 코드 뭐하는거야?"}, headers=ADMIN).json()
    assert body["proposed_change_id"] is None


def test_review_endpoint_with_explicit_diff(monkeypatch):
    monkeypatch.setattr(
        llm_service, "_post_chat",
        lambda url, headers, payload: {"choices": [{"message": {"content":
            '[{"severity": "medium", "file": "a.py", "comment": "예외 처리 누락"}]'
        }}]},
    )
    c = _client()
    pid = _create_project(c)
    prov = _create_provider(c)
    r = c.post(f"/projects/{pid}/review",
               json={"provider_id": prov, "diff": "--- a/a.py\n+++ b/a.py\n"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["max_severity"] == "medium"


def test_module_bind_and_llm_context():
    c = _client()
    pid = _create_project(c)
    r = c.post("/modules", json={
        "name": "mail", "type": "external_api",
        "config": {"url": "https://cho-fam.web.app/api/mail", "api_key": "mk-1"},
    }, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["config"]["api_key"] == "•••"
    mid = r.json()["id"]

    r = c.post(f"/projects/{pid}/modules/{mid}/bind", json={"env_prefix": "MAIL"}, headers=ADMIN)
    assert r.status_code == 201
    assert r.json()["injected_env"] == ["MAIL_API_KEY", "MAIL_URL"]

    # 같은 prefix 재사용 금지
    assert c.post(f"/projects/{pid}/modules/{mid}/bind",
                  json={"env_prefix": "MAIL"}, headers=ADMIN).status_code == 409

    ctx = c.get(f"/projects/{pid}/modules", headers=ADMIN).json()
    assert ctx == [{"name": "mail", "type": "external_api",
                    "env": ["MAIL_API_KEY", "MAIL_URL"]}]
