"""mail 모듈 — CHO-FAM 메일 API(POST {mail_api_url}/send)로 관리자 알림을 보낸다.

기능 비활성이거나 설정이 비어 있으면 조용히 no-op. 알림 실패가 본 작업(배포 등)을
실패시키지 않도록 예외를 삼킨다.
"""
import httpx

from ..config import get_settings
from ..features import is_enabled


def send_alert(subject: str, body: str) -> bool:
    settings = get_settings()
    if not is_enabled("mail"):
        return False
    if not (settings.mail_api_url and settings.mail_api_key and settings.mail_alert_to
            and settings.mail_template_id):
        return False
    payload = {
        "to": settings.mail_alert_to,
        "templateId": settings.mail_template_id,
        "dynamicData": {"subject": subject, "body": body},
    }
    print(f"[paas] mail send request: to={payload['to']} templateId={payload['templateId']} "
          f"subject={subject!r} body={body!r}")
    try:
        from .httpx_retry import post_with_retry  # noqa: PLC0415

        res = post_with_retry(
            f"{settings.mail_api_url.rstrip('/')}/send",
            headers={"x-api-key": settings.mail_api_key},
            json=payload,
            timeout=10,
        )
        return res.status_code < 400
    except Exception:
        return False
