"""payment 모듈 — 토스 confirm/cancel 흐름 (HTTP 경계 _post 목킹)."""
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import toss

ADMIN = {"x-api-key": "test-admin-key"}
CONFIRM = {"paymentKey": "pk_test_1", "orderId": "order-1", "amount": 15000}


def _client() -> TestClient:
    return TestClient(create_app())


def _mock_ok(monkeypatch):
    monkeypatch.setattr(
        toss, "_post",
        lambda url, headers, payload: (200, {"status": "DONE", "method": "카드"}),
    )


def test_confirm_records_payment(monkeypatch):
    _mock_ok(monkeypatch)
    c = _client()
    r = c.post("/paas/api/v1/payments/confirm", json=CONFIRM, headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "confirmed"
    assert body["method"] == "카드"
    assert body["source"] == "bootstrap-admin"

    listing = c.get("/paas/api/v1/payments", headers=ADMIN).json()
    assert len(listing) == 1
    rows = c.get("/paas/api/v1/audit", headers=ADMIN).json()
    assert any(a["action"] == "payment.confirm" and a["target"] == "order-1" for a in rows)


def test_confirm_is_idempotent_but_conflicts_on_mismatch(monkeypatch):
    _mock_ok(monkeypatch)
    c = _client()
    assert c.post("/paas/api/v1/payments/confirm", json=CONFIRM, headers=ADMIN).status_code == 200
    # 동일 내용 재시도 → 멱등 200
    assert c.post("/paas/api/v1/payments/confirm", json=CONFIRM, headers=ADMIN).status_code == 200
    # 같은 orderId, 다른 금액 → 409
    bad = dict(CONFIRM, amount=99999)
    assert c.post("/paas/api/v1/payments/confirm", json=bad, headers=ADMIN).status_code == 409


def test_toss_error_marks_failed(monkeypatch):
    monkeypatch.setattr(
        toss, "_post",
        lambda url, headers, payload: (400, {"code": "INVALID_CARD", "message": "카드 오류"}),
    )
    c = _client()
    r = c.post("/paas/api/v1/payments/confirm", json=CONFIRM, headers=ADMIN)
    assert r.status_code == 502
    assert "INVALID_CARD" in r.json()["detail"]
    listing = c.get("/paas/api/v1/payments", headers=ADMIN).json()
    assert listing[0]["status"] == "failed"
    assert "INVALID_CARD" in listing[0]["fail_reason"]


def test_cancel_flow_and_permissions(monkeypatch):
    _mock_ok(monkeypatch)
    c = _client()
    c.post("/paas/api/v1/payments/confirm", json=CONFIRM, headers=ADMIN)

    member = c.post("/paas/api/v1/keys", json={"name": "svc"}, headers=ADMIN).json()["key"]
    # 일반 키는 취소 불가
    r = c.post("/paas/api/v1/payments/pk_test_1/cancel", json={"reason": "테스트"},
               headers={"x-api-key": member})
    assert r.status_code == 403

    r = c.post("/paas/api/v1/payments/pk_test_1/cancel", json={"reason": "고객 변심"}, headers=ADMIN)
    assert r.status_code == 200
    assert r.json()["status"] == "canceled"
    # 이미 취소된 건 재취소 불가
    assert c.post("/paas/api/v1/payments/pk_test_1/cancel", json={}, headers=ADMIN).status_code == 409


def test_missing_secret_gives_clear_error(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_TOSS_SECRET_KEY", "")
    from app.config import get_settings

    get_settings.cache_clear()
    c = _client()
    r = c.post("/paas/api/v1/payments/confirm", json=CONFIRM, headers=ADMIN)
    assert r.status_code == 503
    assert "PAAS_TOSS_SECRET_KEY" in r.json()["detail"]
