import os
import secrets
from pathlib import Path

from fastapi import FastAPI
from starlette.staticfiles import StaticFiles

from .api import llm, modules, orgs, payments, previews, projects, system, webhooks
from .config import get_settings
from .db import Base, engine
from .features import enabled_features


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
    features = enabled_features()

    # core — 항상 켜짐 (projects 안의 배포 계열 엔드포인트는 require_feature("deploy")로 게이트)
    app.include_router(system.router)
    app.include_router(projects.router)
    app.include_router(orgs.router)
    app.include_router(modules.router)

    # 선택 모듈 (설치 빌드옵션)
    if "deploy" in features:
        app.include_router(webhooks.router)
        app.include_router(previews.router)
    if "workspace" in features:
        app.include_router(llm.router)
    if "payment" in features:
        app.include_router(payments.router)

    # 콘솔 UI(React 빌드 산출물) — dist가 있을 때만 마운트, 없어도 API는 동일 기동
    console_dist = Path(
        os.environ.get("PAAS_CONSOLE_DIST")
        or Path(__file__).resolve().parents[1] / "console" / "dist"
    )
    if console_dist.is_dir():
        app.mount("/console", StaticFiles(directory=console_dist, html=True), name="console")
    return app


app = create_app()
