"""리버스프록시 인터페이스 — 1차(small)에서 도메인 라우팅을 맡는 백엔드를 추상화한다.

caddy(기본)/iis/apache 세 구현이 있다(PAAS_PROXY_BACKEND). 2차(enterprise)는 K8s
Ingress + cert-manager가 이 역할을 대신하므로 이 패키지를 쓰지 않는다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ...models import BuildProfile, RedirectRule
from ..runtime.base import Endpoint


@dataclass
class RedirectSpec:
    """RedirectRule을 프록시 설정 생성에 필요한 최소 필드로 옮긴 것(DB 세션 비의존)."""

    from_path: str
    to_path: str
    kind: str  # "redirect" | "rewrite"
    status_code: int = 302  # kind="redirect"일 때만 의미

    @classmethod
    def from_rule(cls, rule: RedirectRule) -> "RedirectSpec":
        return cls(
            from_path=rule.from_path, to_path=rule.to_path,
            kind=rule.kind.value, status_code=rule.status_code,
        )


def site_name(project_name: str, profile: BuildProfile) -> str:
    suffix = "-dev" if profile == BuildProfile.development else ""
    return f"{project_name}{suffix}"


class ReverseProxy(ABC):
    @abstractmethod
    def configure(
        self, project_name: str, profile: BuildProfile, domain: str,
        endpoint: Endpoint, redirects: list[RedirectSpec],
    ) -> None:
        """도메인 → endpoint 라우팅 + redirect/rewrite 규칙을 반영하고 무중단 reload한다."""

    @abstractmethod
    def remove(self, project_name: str, profile: BuildProfile) -> None:
        """사이트 설정을 제거한다."""
