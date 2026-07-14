"""갭7 — 외부 호출 재시도: 네트워크 오류만 재시도, HTTP 오류 응답은 재시도 금지."""
import httpx
import pytest

from app.services import httpx_retry


class _Res:
    status_code = 200


def test_retries_connect_error_then_succeeds(monkeypatch):
    calls = []

    def flaky(url, **kw):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("refused")
        return _Res()

    monkeypatch.setattr(httpx_retry.httpx, "post", flaky)
    monkeypatch.setattr(httpx_retry.time, "sleep", lambda s: None)
    res = httpx_retry.post_with_retry("https://x/api")
    assert res.status_code == 200
    assert len(calls) == 3


def test_gives_up_after_max_attempts(monkeypatch):
    calls = []

    def down(url, **kw):
        calls.append(1)
        raise httpx.ConnectTimeout("timeout")

    monkeypatch.setattr(httpx_retry.httpx, "post", down)
    monkeypatch.setattr(httpx_retry.time, "sleep", lambda s: None)
    with pytest.raises(httpx.ConnectTimeout):
        httpx_retry.post_with_retry("https://x/api")
    assert len(calls) == 3


def test_http_error_response_not_retried(monkeypatch):
    """4xx/5xx는 '응답을 받은' 상태 — 비멱등 호출 중복 방지를 위해 재시도하지 않는다."""
    calls = []

    class _Bad:
        status_code = 500

    monkeypatch.setattr(httpx_retry.httpx, "post", lambda url, **kw: (calls.append(1), _Bad())[1])
    res = httpx_retry.post_with_retry("https://x/api")
    assert res.status_code == 500
    assert len(calls) == 1


def test_non_network_exception_not_retried(monkeypatch):
    calls = []

    def boom(url, **kw):
        calls.append(1)
        raise ValueError("programming error")

    monkeypatch.setattr(httpx_retry.httpx, "post", boom)
    with pytest.raises(ValueError):
        httpx_retry.post_with_retry("https://x/api")
    assert len(calls) == 1
