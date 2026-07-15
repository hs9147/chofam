"""조직(Organization) 운영 — 조직별 작업공간을 만들고 사내 Gitea에 대응 Organization을
할당한다. 프로젝트별 리포 생성은 프로젝트 생성 시(api/projects.py) 플랫폼이 내부에서
처리하며, 사용자에게 git_url 등 메타 정보를 노출하지 않는다."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import ApiKey, Organization, Project
from ..schemas import OrgCreate, OrgOut
from ..security import require_admin, require_api_key
from ..services import gitea
from ..services.gitea import GiteaError, GiteaNotConfigured

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.post("", response_model=OrgOut, status_code=201)
def create_org(
    body: OrgCreate,
    db: Session = Depends(get_db),
    admin: ApiKey = Depends(require_admin),
):
    if db.execute(select(Organization).where(Organization.name == body.name)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="organization already exists")
    try:
        gitea.ensure_org(body.name)
    except GiteaNotConfigured as e:
        raise HTTPException(status_code=503, detail=str(e))
    except GiteaError as e:
        raise HTTPException(status_code=502, detail=str(e))

    org = Organization(name=body.name)
    db.add(org)
    db.commit()
    audit.record(db, admin.name, "org.create", org.name)
    return OrgOut(id=org.id, name=org.name, created_at=org.created_at, project_count=0)


@router.get("", response_model=list[OrgOut])
def list_orgs(db: Session = Depends(get_db), _: ApiKey = Depends(require_api_key)):
    rows = db.execute(
        select(Organization, func.count(Project.id))
        .outerjoin(Project, Project.organization_id == Organization.id)
        .group_by(Organization.id)
        .order_by(Organization.id)
    ).all()
    return [
        OrgOut(id=org.id, name=org.name, created_at=org.created_at, project_count=count)
        for org, count in rows
    ]
