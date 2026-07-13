from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit
from ..db import get_db
from ..models import ApiKey, Module, ModuleBinding, ModuleType, Project
from ..schemas import ModuleBind, ModuleCreate
from ..security import require_api_key
from ..services import modules as svc

router = APIRouter(tags=["modules"])


@router.post("/modules", status_code=201)
def create_module(
    body: ModuleCreate,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    if db.execute(select(Module).where(Module.name == body.name)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="module name already exists")
    row = Module(name=body.name, type=ModuleType(body.type), config=svc.encrypt_config(body.config))
    db.add(row)
    db.commit()
    audit.record(db, key.name, "module.create", body.name, {"type": body.type})
    return {"id": row.id, "name": row.name, "type": row.type.value,
            "config": svc.masked_config(row.config)}


@router.get("/modules")
def list_modules(db: Session = Depends(get_db), _: ApiKey = Depends(require_api_key)):
    rows = db.execute(select(Module).order_by(Module.id)).scalars()
    return [
        {"id": m.id, "name": m.name, "type": m.type.value, "config": svc.masked_config(m.config)}
        for m in rows
    ]


@router.post("/projects/{project_id}/modules/{module_id}/bind", status_code=201)
def bind_module(
    project_id: int,
    module_id: int,
    body: ModuleBind,
    db: Session = Depends(get_db),
    key: ApiKey = Depends(require_api_key),
):
    project = db.get(Project, project_id)
    module = db.get(Module, module_id)
    if project is None or module is None:
        raise HTTPException(status_code=404, detail="project or module not found")
    dup = db.execute(
        select(ModuleBinding).where(
            ModuleBinding.project_id == project_id,
            ModuleBinding.env_prefix == body.env_prefix,
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="env_prefix already used in this project")
    db.add(ModuleBinding(project_id=project_id, module_id=module_id, env_prefix=body.env_prefix))
    db.commit()
    audit.record(db, key.name, "module.bind", project.name,
                 {"module": module.name, "prefix": body.env_prefix})
    # 주입될 환경변수 키를 미리 보여준다 (값은 배포 시에만 주입)
    return {"injected_env": sorted(svc.binding_env(module, body.env_prefix).keys())}


@router.get("/projects/{project_id}/modules")
def project_modules(
    project_id: int,
    db: Session = Depends(get_db),
    _: ApiKey = Depends(require_api_key),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return svc.context_for_llm(db, project)
