import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ProjectType(str, enum.Enum):
    react = "react"
    python = "python"
    node = "node"
    llm = "llm"


class BuildProfile(str, enum.Enum):
    """빌드 옵션. development는 디버깅용 경량 실행, release는 운영용 최적화 빌드."""

    development = "development"
    release = "release"


class DeploymentStatus(str, enum.Enum):
    building = "building"
    running = "running"
    failed = "failed"
    stopped = "stopped"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    type: Mapped[ProjectType] = mapped_column(Enum(ProjectType))
    git_url: Mapped[str] = mapped_column(String(512))
    branch: Mapped[str] = mapped_column(String(128), default="main")
    # 미지정 시 {name}.{base_domain} / development는 {name}-dev.{base_domain}
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    health_check_path: Mapped[str] = mapped_column(String(255), default="/")
    memory_limit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cpu_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 웹훅 자동 배포 시 사용할 기본 프로필
    default_profile: Mapped[BuildProfile] = mapped_column(
        Enum(BuildProfile), default=BuildProfile.release
    )
    # LLM 전용 확장 필드 (vLLM 옵션 등)
    llm_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    deployments: Mapped[list["Deployment"]] = relationship(back_populates="project")
    env_vars: Mapped[list["EnvVar"]] = relationship(back_populates="project")


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    git_sha: Mapped[str] = mapped_column(String(40))
    image_tag: Mapped[str] = mapped_column(String(255))
    profile: Mapped[BuildProfile] = mapped_column(Enum(BuildProfile))
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus), default=DeploymentStatus.building
    )
    # 1차(small)에서 Caddy 업스트림으로 쓰는 호스트 포트. 2차(k8s)에서는 None.
    host_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    build_log_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="deployments")


class EnvVar(Base):
    __tablename__ = "env_vars"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(128))
    value_encrypted: Mapped[str] = mapped_column(Text)  # Fernet 암호문. 평문 저장 금지.
    is_secret: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped[Project] = relationship(back_populates="env_vars")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    key_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 hex
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    """감사 로그. 2차(대기업) 요구를 위해 1차부터 배포·롤백·시크릿 변경·키 발급을 기록한다."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(64))  # API 키 이름 또는 "webhook"
    action: Mapped[str] = mapped_column(String(64))  # deploy / rollback / env.set / key.issue ...
    target: Mapped[str] = mapped_column(String(255))
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
