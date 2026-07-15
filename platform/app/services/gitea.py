"""Gitea REST API 클라이언트.

조직(Organization) 생성 시 대응하는 Gitea Organization을, 조직 소속 프로젝트 생성 시
대응하는 리포를 플랫폼이 대신 만든다. 사용자는 Gitea URL/리포 주소를 직접 다루지
않는다 — git_url은 서버 내부에서만 사용되고 비관리자 API 응답에서는 마스킹된다
(api/projects.py `_serialize_project` 참고).
"""
import httpx

from ..config import get_settings


class GiteaError(RuntimeError):
    """Gitea API 호출 자체는 성공했지만(설정은 있음) 요청이 실패한 경우 — 502로 매핑."""


class GiteaNotConfigured(GiteaError):
    """PAAS_GITEA_URL/PAAS_GITEA_API_TOKEN 미설정 — 503으로 매핑."""


def _base_and_headers() -> tuple[str, dict[str, str]]:
    settings = get_settings()
    if not settings.gitea_url:
        raise GiteaNotConfigured("PAAS_GITEA_URL이 설정되지 않았습니다.")
    if not settings.gitea_api_token:
        raise GiteaNotConfigured("PAAS_GITEA_API_TOKEN이 설정되지 않았습니다.")
    return settings.gitea_url.rstrip("/"), {"Authorization": f"token {settings.gitea_api_token}"}


def ensure_org(name: str) -> None:
    """조직(Gitea Organization)이 없으면 생성한다. 이미 있으면 조용히 통과(멱등)."""
    base, headers = _base_and_headers()
    res = httpx.post(
        f"{base}/api/v1/orgs", headers=headers,
        json={"username": name, "visibility": "private"}, timeout=15,
    )
    if res.status_code in (201, 422):  # 422 = username already exists
        return
    raise GiteaError(f"Gitea 조직 생성 실패 (HTTP {res.status_code}): {res.text[:300]}")


def ensure_repo(org_name: str, repo_name: str) -> str:
    """조직 아래 리포가 없으면 생성하고, 이미 있으면 조회해서 clone URL을 반환한다."""
    base, headers = _base_and_headers()
    res = httpx.post(
        f"{base}/api/v1/orgs/{org_name}/repos", headers=headers,
        json={"name": repo_name, "private": True, "auto_init": True}, timeout=15,
    )
    if res.status_code == 201:
        return res.json()["clone_url"]
    if res.status_code == 409:  # 이미 존재 — 조회해서 재사용
        got = httpx.get(f"{base}/api/v1/repos/{org_name}/{repo_name}", headers=headers, timeout=15)
        if got.status_code == 200:
            return got.json()["clone_url"]
        raise GiteaError(f"Gitea 리포 조회 실패 (HTTP {got.status_code}): {got.text[:300]}")
    raise GiteaError(f"Gitea 리포 생성 실패 (HTTP {res.status_code}): {res.text[:300]}")
