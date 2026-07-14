"""payment 모듈 — 토스페이먼츠 결제(수납) 클라이언트.

결제 위젯이 successUrl로 넘겨준 paymentKey/orderId/amount를 서버가 승인(confirm)하는
표준 흐름. 인증은 Basic base64(secret_key + ":").

참고: 지급대행(payout, 셀러 송금)은 CHO-FAM functions(/api/payout)에 별도로 구현되어
있다 — 여기는 수납(결제 승인·취소) 전용이다.
"""
import base64

import httpx

from ..config import get_settings


class TossError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 502):
        super().__init__(message)
        self.code = code
        self.status = status


def _auth_header() -> dict[str, str]:
    secret = get_settings().toss_secret_key
    if not secret:
        raise TossError("not_configured", "PAAS_TOSS_SECRET_KEY가 설정되지 않았습니다.", status=503)
    token = base64.b64encode(f"{secret}:".encode()).decode()
    return {"authorization": f"Basic {token}", "content-type": "application/json"}


def confirm(payment_key: str, order_id: str, amount: int) -> dict:
    base = get_settings().toss_api_base.rstrip("/")
    status, data = _post(
        f"{base}/v1/payments/confirm",
        _auth_header(),
        {"paymentKey": payment_key, "orderId": order_id, "amount": amount},
    )
    if status >= 400:
        raise TossError(data.get("code", "toss_error"), data.get("message", f"HTTP {status}"))
    return data


def cancel(payment_key: str, reason: str) -> dict:
    base = get_settings().toss_api_base.rstrip("/")
    status, data = _post(
        f"{base}/v1/payments/{payment_key}/cancel",
        _auth_header(),
        {"cancelReason": reason},
    )
    if status >= 400:
        raise TossError(data.get("code", "toss_error"), data.get("message", f"HTTP {status}"))
    return data


def _post(url: str, headers: dict, payload: dict) -> tuple[int, dict]:
    """실제 HTTP 경계 — 테스트에서 monkeypatch한다. 네트워크 오류만 재시도(갭7)."""
    from .httpx_retry import post_with_retry  # noqa: PLC0415

    res = post_with_retry(url, headers=headers, json=payload, timeout=30)
    try:
        data = res.json()
    except ValueError:
        data = {"message": res.text[:300]}
    return res.status_code, data
