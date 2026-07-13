import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import ApiKey

_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        settings = get_settings()
        key = settings.fernet_key
        if not key:
            # 운영에서는 반드시 PAAS_FERNET_KEY를 고정할 것 — 미설정 시 재기동마다 복호화 불가
            key = Fernet.generate_key().decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_value(plain: str) -> str:
    return get_fernet().encrypt(plain.encode()).decode()


def decrypt_value(token: str) -> str:
    return get_fernet().decrypt(token.encode()).decode()


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_key() -> str:
    return "paas_" + secrets.token_urlsafe(32)


def verify_webhook_signature(secret: str, body: bytes, signature: str) -> bool:
    """GitHub(X-Hub-Signature-256: 'sha256=<hex>') / Gitea(X-Gitea-Signature: '<hex>') 공용."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    received = signature.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)


def require_api_key(
    x_api_key: str = Header(default=""),
    db: Session = Depends(get_db),
) -> ApiKey:
    settings = get_settings()
    if not x_api_key:
        raise HTTPException(status_code=401, detail="x-api-key header required")
    if settings.admin_api_key and hmac.compare_digest(x_api_key, settings.admin_api_key):
        return ApiKey(name="bootstrap-admin", key_hash="", is_admin=True)
    row = db.execute(select(ApiKey).where(ApiKey.key_hash == hash_key(x_api_key))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid api key")
    return row


def require_admin(key: ApiKey = Depends(require_api_key)) -> ApiKey:
    if not key.is_admin:
        raise HTTPException(status_code=403, detail="admin key required")
    return key
