"""서버구성 시각화 + 프로젝트별 redirect/rewrite 규칙 관리.

1차(small)의 리버스프록시(Caddy/IIS/Apache)·런타임(Docker/Windows Service) 선택과
등록된 사이트(도메인·상태·리다이렉트 규칙 수)를 한 화면에서 보여준다 — "서버구성
시각화" + "메뉴(라우팅/사이트 항목) 관리" 요건. redirect/rewrite 규칙은 다음
배포/롤백 때 프록시 설정에 반영된다(services/deployer.py의 redirects_for 참고).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..config import get_settings
from ..db import get_db
from ..models import ApiKey, BuildProfile, Project, RedirectKind, RedirectRule
from ..schemas import RedirectRuleCreate, RedirectRuleOut, ServerConfigOut, ServerConfigSite
from ..security import require_api_key
from ..services import deployer
from ..services.proxy import domain_for

router = APIRouter(tags=["server"])


@router.get("/server-config", response_model=ServerConfigOut)
def server_config(db: Session = Depends(get_db), _: ApiKey = Depends(require_api_key)):
    settings = get_settings()
    runtime = deployer.get_runtime()
    projects = db.execute(select(Project).order_by(Project.id)).scalars().all()
    counts = dict(
        db.execute(
            select(RedirectRule.project_id, func.count(RedirectRule.id))
            .group_by(RedirectRule.project_id)
        ).all()
    )
    sites = []
    for p in projects:
        for profile in BuildProfile:
            try:
                status = runtime.status(p.name, profile)
            except Exception as e:  # noqa: BLE001 — 런타임 미설치/미접근이 전체 화면을 막지 않게
                status = f"unknown ({e})"
            sites.append(ServerConfigSite(
                project_id=p.id,
                project_name=p.name,
                profile=profile,
                domain=domain_for(p.name, p.domain, profile),
                status=status,
                redirect_count=counts.get(p.id, 0),
            ))
    return ServerConfigOut(
        runtime_backend=settings.runtime_backend if settings.tier == "small" else "kubernetes",
        proxy_backend=settings.proxy_backend if settings.tier == "small" else "k8s-ingress",
        sites=sites,
    )


@router.post("/projects/{project_id}/redirects", response_model=RedirectRuleOut, status_code=201)
def create_redirect(
    project_id: int,
    body: RedirectRuleCreate,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    row = RedirectRule(
        project_id=project_id, from_path=body.from_path, to_path=body.to_path,
        kind=RedirectKind(body.kind), status_code=body.status_code,
    )
    db.add(row)
    db.commit()
    audit.record(db, key.name, "redirect.create", project.name,
                 {"from": body.from_path, "to": body.to_path, "kind": body.kind})
    return row


@router.get("/projects/{project_id}/redirects", response_model=list[RedirectRuleOut])
def list_redirects(
    project_id: int,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_api_key),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return list(
        db.execute(
            select(RedirectRule)
            .where(RedirectRule.project_id == project_id)
            .order_by(RedirectRule.id)
        ).scalars()
    )


@router.delete("/redirects/{redirect_id}", status_code=204)
def delete_redirect(
    redirect_id: int,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    row = db.get(RedirectRule, redirect_id)
    if row is None:
        raise HTTPException(status_code=404, detail="redirect not found")
    project = db.get(Project, row.project_id)
    db.delete(row)
    db.commit()
    audit.record(db, key.name, "redirect.delete",
                 project.name if project else str(row.project_id), {"id": redirect_id})
