from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..features import require_feature
from ..models import ApiKey, BuildProfile, Deployment, EnvVar, Project
from ..schemas import (
    DeploymentOut,
    DeployRequest,
    EnvVarSet,
    ProjectCreate,
    ProjectOut,
)
from ..security import encrypt_value, require_api_key
from ..services import deployer
from ..services.deployer import DeployInProgress, NoRollbackTarget

router = APIRouter(prefix="/projects", tags=["projects"])


def _get_project(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), _: ApiKey = Depends(require_api_key)):
    return db.execute(select(Project).order_by(Project.id)).scalars().all()


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    exists = db.execute(select(Project).where(Project.name == body.name)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="project name already exists")
    project = Project(**body.model_dump())
    db.add(project)
    db.commit()
    audit.record(db, key.name, "project.create", project.name)
    return project


@router.post("/{project_id}/deploy", response_model=DeploymentOut,
             dependencies=[Depends(require_feature("deploy"))])
async def deploy_project(
    project_id: int,
    body: DeployRequest,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    project = _get_project(db, project_id)
    profile = body.profile or project.default_profile
    try:
        record = await deployer.deploy(db, project, profile, body.git_sha)
    except DeployInProgress as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:1000])
    audit.record(
        db, key.name, "deploy", project.name,
        {"profile": profile.value, "sha": record.git_sha, "deployment_id": record.id},
    )
    return record


@router.post("/{project_id}/rollback", response_model=DeploymentOut,
             dependencies=[Depends(require_feature("deploy"))])
def rollback_project(
    project_id: int,
    profile: BuildProfile = BuildProfile.release,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    project = _get_project(db, project_id)
    try:
        record = deployer.rollback(db, project, profile)
    except NoRollbackTarget as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e)[:1000])
    audit.record(db, key.name, "rollback", project.name,
                 {"profile": profile.value, "to_sha": record.git_sha})
    return record


@router.post("/{project_id}/stop", status_code=204,
             dependencies=[Depends(require_feature("deploy"))])
def stop_project(
    project_id: int,
    profile: BuildProfile = BuildProfile.release,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    project = _get_project(db, project_id)
    deployer.get_runtime().stop(project.name, profile)
    audit.record(db, key.name, "stop", project.name, {"profile": profile.value})


@router.get("/{project_id}/deployments", response_model=list[DeploymentOut],
            dependencies=[Depends(require_feature("deploy"))])
def list_deployments(
    project_id: int,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_api_key),
):
    _get_project(db, project_id)
    return (
        db.execute(
            select(Deployment)
            .where(Deployment.project_id == project_id)
            .order_by(Deployment.id.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )


@router.get("/{project_id}/logs", dependencies=[Depends(require_feature("deploy"))])
def project_logs(
    project_id: int,
    profile: BuildProfile = BuildProfile.release,
    tail: int = 200,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_api_key),
):
    project = _get_project(db, project_id)
    return {"logs": deployer.get_runtime().logs(project.name, profile, tail)}


@router.get("/{project_id}/status", dependencies=[Depends(require_feature("deploy"))])
def project_status(
    project_id: int,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_api_key),
):
    project = _get_project(db, project_id)
    runtime = deployer.get_runtime()
    return {
        profile.value: runtime.status(project.name, profile)
        for profile in BuildProfile
    }


@router.put("/{project_id}/env", status_code=204)
def set_env_var(
    project_id: int,
    body: EnvVarSet,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    project = _get_project(db, project_id)
    row = db.execute(
        select(EnvVar).where(EnvVar.project_id == project_id, EnvVar.key == body.key)
    ).scalar_one_or_none()
    if row is None:
        row = EnvVar(project_id=project_id, key=body.key)
        db.add(row)
    row.value_encrypted = encrypt_value(body.value)
    row.is_secret = body.is_secret
    db.commit()
    # 값은 감사 로그에도 남기지 않는다
    audit.record(db, key.name, "env.set", project.name, {"key": body.key})


@router.get("/{project_id}/env")
def list_env_vars(
    project_id: int,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_api_key),
):
    _get_project(db, project_id)
    rows = db.execute(select(EnvVar).where(EnvVar.project_id == project_id)).scalars()
    # 시크릿 값은 마스킹해서만 노출
    return [{"key": r.key, "is_secret": r.is_secret, "value": "•••" if r.is_secret else "(set)"}
            for r in rows]
