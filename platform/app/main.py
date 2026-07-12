import secrets

from fastapi import FastAPI

from .api import llm, modules, previews, projects, system, webhooks
from .config import get_settings
from .db import Base, engine


def create_app() -> FastAPI:
    settings = get_settings()
    Base.metadata.create_all(engine)

    if not settings.admin_api_key:
        # 부트스트랩 편의용 — 운영에서는 PAAS_ADMIN_API_KEY를 고정할 것
        settings.admin_api_key = "paas_" + secrets.token_urlsafe(24)
        print(f"[paas] bootstrap admin key (set PAAS_ADMIN_API_KEY to pin): {settings.admin_api_key}")

    app = FastAPI(
        title="chofam cloud platform",
        description=(
            "내부 PaaS 컨트롤 플레인. "
            f"tier={settings.tier} (small=Docker, enterprise=Kubernetes), "
            "빌드 프로필=development|release"
        ),
        version="0.1.0",
    )
    app.include_router(system.router)
    app.include_router(projects.router)
    app.include_router(webhooks.router)
    app.include_router(llm.router)
    app.include_router(modules.router)
    app.include_router(previews.router)
    return app


app = create_app()
