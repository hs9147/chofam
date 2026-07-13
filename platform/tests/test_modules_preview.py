"""Module 환경 주입 규약, 시크릿 암호화/마스킹, 프리뷰 이름·TTL 검증."""
from datetime import datetime, timedelta, timezone

from app.models import Module, ModuleType, PreviewSession
from app.services import modules as svc
from app.services import preview


def _module(mtype: ModuleType, config: dict) -> Module:
    return Module(name="m", type=mtype, config=svc.encrypt_config(config))


def test_external_api_env():
    m = _module(ModuleType.external_api,
                {"url": "https://pay.example.com", "api_key": "sk-123"})
    env = svc.binding_env(m, "pay")
    assert env == {"PAY_URL": "https://pay.example.com", "PAY_API_KEY": "sk-123"}
    # 저장 형태는 암호문, 마스킹 조회는 평문 노출 없음
    assert m.config["api_key"] != "sk-123"
    assert svc.masked_config(m.config)["api_key"] == "•••"


def test_database_env_encrypted_dsn():
    m = _module(ModuleType.database, {"dsn": "postgresql://u:pw@db/prod"})
    assert svc.binding_env(m, "MAIN")["MAIN_DSN"] == "postgresql://u:pw@db/prod"
    assert "pw" not in str(m.config)


def test_internal_api_env_resolves_by_tier():
    m = _module(ModuleType.internal_api, {"target_project": "mail-api"})
    small = svc.binding_env(m, "MAIL")
    assert small == {"MAIL_URL": "https://mail-api.apps.test"}

    from app.config import get_settings
    enterprise = get_settings().model_copy(
        update={"tier": "enterprise", "k8s_namespace": "paas-apps"}
    )
    ent = svc.binding_env(m, "MAIL", settings=enterprise)
    assert ent == {"MAIL_URL": "http://paas-mail-api.paas-apps.svc"}


def test_file_storage_env():
    m = _module(ModuleType.file_storage,
                {"endpoint": "http://seaweed:8333", "bucket": "assets"})
    env = svc.binding_env(m, "FS")
    assert env == {"FS_ENDPOINT": "http://seaweed:8333", "FS_BUCKET": "assets"}


def test_preview_naming_and_expiry():
    assert preview.preview_unit_name("shop", 7) == "shop-pv7"
    assert preview.preview_domain("shop", 7) == "shop-pv7.apps.test"

    now = datetime.now(timezone.utc)
    live = PreviewSession(project_id=1, branch="b", expires_at=now + timedelta(minutes=5))
    dead = PreviewSession(project_id=1, branch="b", expires_at=now - timedelta(minutes=5))
    naive = PreviewSession(project_id=1, branch="b",
                           expires_at=(now - timedelta(minutes=5)).replace(tzinfo=None))
    assert not preview.is_expired(live, now)
    assert preview.is_expired(dead, now)
    assert preview.is_expired(naive, now)  # SQLite naive datetime도 처리
