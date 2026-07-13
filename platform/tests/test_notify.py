"""mail 모듈 — 알림 발송 (httpx 목킹), 비활성/미설정 시 no-op 검증."""
from app.config import get_settings
from app.services import notify


class _Res:
    status_code = 202


def test_sends_when_configured(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_MAIL_API_URL", "https://cho-fam.web.app/api/mail")
    monkeypatch.setenv("PAAS_MAIL_API_KEY", "mk-1")
    monkeypatch.setenv("PAAS_MAIL_ALERT_TO", "ops@example.com")
    monkeypatch.setenv("PAAS_MAIL_TEMPLATE_ID", "d-123")
    get_settings.cache_clear()

    calls = []
    monkeypatch.setattr(notify.httpx, "post", lambda url, **kw: calls.append((url, kw)) or _Res())

    assert notify.send_alert("제목", "본문") is True
    url, kw = calls[0]
    assert url == "https://cho-fam.web.app/api/mail/send"
    assert kw["headers"]["x-api-key"] == "mk-1"
    assert kw["json"]["to"] == "ops@example.com"
    assert kw["json"]["dynamicData"] == {"subject": "제목", "body": "본문"}


def test_noop_when_unconfigured(monkeypatch, fresh_settings):
    get_settings.cache_clear()
    called = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: called.append(1))
    assert notify.send_alert("x", "y") is False
    assert called == []


def test_noop_when_feature_disabled(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_FEATURES", "deploy")
    monkeypatch.setenv("PAAS_MAIL_API_URL", "https://x/api/mail")
    monkeypatch.setenv("PAAS_MAIL_API_KEY", "k")
    monkeypatch.setenv("PAAS_MAIL_ALERT_TO", "a@b.c")
    monkeypatch.setenv("PAAS_MAIL_TEMPLATE_ID", "d-1")
    get_settings.cache_clear()
    called = []
    monkeypatch.setattr(notify.httpx, "post", lambda *a, **kw: called.append(1))
    assert notify.send_alert("x", "y") is False
    assert called == []


def test_swallow_http_errors(monkeypatch, fresh_settings):
    monkeypatch.setenv("PAAS_MAIL_API_URL", "https://x/api/mail")
    monkeypatch.setenv("PAAS_MAIL_API_KEY", "k")
    monkeypatch.setenv("PAAS_MAIL_ALERT_TO", "a@b.c")
    monkeypatch.setenv("PAAS_MAIL_TEMPLATE_ID", "d-1")
    get_settings.cache_clear()

    def boom(*a, **kw):
        raise ConnectionError("down")

    monkeypatch.setattr(notify.httpx, "post", boom)
    assert notify.send_alert("x", "y") is False  # 예외가 밖으로 새지 않음
