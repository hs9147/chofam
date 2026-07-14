"""배포 오케스트레이터.

checkout → build(프로필별) → runtime 기동(1차 Docker / 2차 K8s) → (1차만) Caddy 전환.
프로젝트별 락으로 동시 배포를 1건으로 제한한다 (웹훅 연속 push 대비).
"""
import asyncio
import threading
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import BuildProfile, Deployment, DeploymentStatus, EnvVar, Project
from ..security import decrypt_value
from . import proxy
from .build import PROFILES, BuildError, build_image, checkout, internal_port
from .runtime.base import Runtime, RuntimeSpec

_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)


def get_runtime() -> Runtime:
    settings = get_settings()
    if settings.tier == "enterprise":
        from .runtime.k8s_runtime import K8sRuntime  # noqa: PLC0415

        return K8sRuntime()
    from .runtime.docker_runtime import DockerRuntime  # noqa: PLC0415

    return DockerRuntime()


def resolve_env(db: Session, project: Project, profile: BuildProfile) -> dict[str, str]:
    from . import modules  # noqa: PLC0415 — 순환 import 회피

    env = dict(PROFILES[profile].env)
    env.update(modules.env_for_project(db, project))  # 바인딩된 Module 자동 주입
    rows = db.execute(select(EnvVar).where(EnvVar.project_id == project.id)).scalars()
    for row in rows:
        env[row.key] = decrypt_value(row.value_encrypted)  # 프로젝트 EnvVar가 최우선
    return env


def make_spec(
    db: Session, project: Project, image_tag: str, profile: BuildProfile
) -> RuntimeSpec:
    from .host import gpu_allowed  # noqa: PLC0415

    settings = get_settings()
    return RuntimeSpec(
        project_name=project.name,
        image_tag=image_tag,
        internal_port=internal_port(project.type, profile),
        profile=profile,
        domain=proxy.domain_for(project.name, project.domain, profile),
        env=resolve_env(db, project, profile),
        memory_limit=project.memory_limit or settings.default_memory_limit,
        cpu_limit=project.cpu_limit or settings.default_cpu_limit,
        replicas=PROFILES[profile].replicas,
        gpu=project.type.value == "llm" and gpu_allowed(),
        health_check_path=project.health_check_path,
    )


def deploy_sync(
    db: Session, project: Project, profile: BuildProfile, git_sha: str | None = None,
    record: Deployment | None = None,
) -> Deployment:
    """블로킹 배포 파이프라인. API에서는 스레드로 위임해 이벤트 루프를 막지 않는다.

    record가 주어지면(큐 경로에서 선생성) 새로 만들지 않고 그 레코드를 채운다.
    """
    lock = _locks[project.id]
    if not lock.acquire(blocking=False):
        if record is not None:
            record.status = DeploymentStatus.failed
            record.error = f"deployment already in progress for {project.name}"
            record.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise DeployInProgress(project.name)
    try:
        workdir, sha = checkout(project, git_sha)
        if record is None:
            record = Deployment(
                project_id=project.id,
                git_sha=sha,
                image_tag="",
                profile=profile,
                status=DeploymentStatus.building,
            )
            db.add(record)
        else:
            record.git_sha = sha
        db.commit()
        try:
            result = build_image(project, workdir, sha, profile)
            record.image_tag = result.image_tag
            record.build_log_path = str(result.log_path)
            db.commit()

            spec = make_spec(db, project, result.image_tag, profile)
            endpoint = get_runtime().start(spec)
            if get_settings().tier == "small":
                proxy.configure(project.name, profile, spec.domain, endpoint)
                record.host_port = endpoint.port

            record.status = DeploymentStatus.running
            record.finished_at = datetime.now(timezone.utc)
            db.commit()
            _mark_previous_stopped(db, record)
            return record
        except (BuildError, RuntimeError) as e:
            record.status = DeploymentStatus.failed
            record.error = str(e)
            if isinstance(e, BuildError) and e.log_path:
                record.build_log_path = str(e.log_path)
            record.finished_at = datetime.now(timezone.utc)
            db.commit()
            from . import notify  # noqa: PLC0415 — mail 모듈 (비활성 시 no-op)

            notify.send_alert(
                f"[paas] {project.name} {profile.value} 배포 실패",
                f"sha={record.git_sha}\n{str(e)[:1000]}",
            )
            raise
    finally:
        lock.release()


async def deploy(
    db: Session, project: Project, profile: BuildProfile, git_sha: str | None = None
) -> Deployment:
    return await asyncio.to_thread(deploy_sync, db, project, profile, git_sha)


def deploy_queued(
    db: Session, project: Project, profile: BuildProfile, git_sha: str | None = None
) -> Deployment:
    """비동기 배포(갭2): building 레코드를 즉시 만들고 파이프라인은 작업 큐에서 실행.

    반환된 레코드 id로 GET /projects/{id}/deployments 폴링으로 진행을 확인한다.
    """
    from ..db import SessionLocal  # noqa: PLC0415
    from . import jobs  # noqa: PLC0415

    record = Deployment(
        project_id=project.id,
        git_sha=git_sha or "",
        image_tag="",
        profile=profile,
        status=DeploymentStatus.building,
    )
    db.add(record)
    db.commit()
    record_id, project_id = record.id, project.id

    def _task() -> None:
        with SessionLocal() as session:
            proj = session.get(Project, project_id)
            rec = session.get(Deployment, record_id)
            if proj is None or rec is None:
                return
            try:
                deploy_sync(session, proj, profile, git_sha, record=rec)
            except Exception:
                # 실패 상태·에러는 deploy_sync가 레코드에 기록함
                pass

    jobs.submit(_task)
    return record


def rollback(db: Session, project: Project, profile: BuildProfile) -> Deployment:
    """직전 성공 배포의 이미지로 재기동 — 재빌드 없음."""
    rows = (
        db.execute(
            select(Deployment)
            .where(
                Deployment.project_id == project.id,
                Deployment.profile == profile,
                Deployment.image_tag != "",
            )
            .order_by(Deployment.id.desc())
        )
        .scalars()
        .all()
    )
    current = next((d for d in rows if d.status == DeploymentStatus.running), None)
    candidates = [
        d
        for d in rows
        if d.status in (DeploymentStatus.stopped, DeploymentStatus.running)
        and (current is None or d.id < current.id)
    ]
    if not candidates:
        raise NoRollbackTarget(project.name)
    target = candidates[0]

    spec = make_spec(db, project, target.image_tag, profile)
    endpoint = get_runtime().start(spec)
    if get_settings().tier == "small":
        proxy.configure(project.name, profile, spec.domain, endpoint)

    record = Deployment(
        project_id=project.id,
        git_sha=target.git_sha,
        image_tag=target.image_tag,
        profile=profile,
        status=DeploymentStatus.running,
        host_port=endpoint.port if get_settings().tier == "small" else None,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    _mark_previous_stopped(db, record)
    return record


def _mark_previous_stopped(db: Session, new_record: Deployment) -> None:
    db.query(Deployment).filter(
        Deployment.project_id == new_record.project_id,
        Deployment.profile == new_record.profile,
        Deployment.status == DeploymentStatus.running,
        Deployment.id != new_record.id,
    ).update({"status": DeploymentStatus.stopped})
    db.commit()


class DeployInProgress(RuntimeError):
    def __init__(self, name: str):
        super().__init__(f"deployment already in progress for {name}")


class NoRollbackTarget(RuntimeError):
    def __init__(self, name: str):
        super().__init__(f"no previous successful deployment for {name}")
