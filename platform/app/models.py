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


class LlmProviderKind(str, enum.Enum):
    external = "external"  # Claude API, OpenAI 등 — 코드가 외부로 나감
    internal = "internal"  # 플랫폼에 배포된 vLLM/Ollama — 사내망 내에서 처리


class LlmProvider(Base):
    """OpenAI 호환 chat completions 엔드포인트로 통일해 외부/내부를 같은 인터페이스로 다룬다."""

    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[LlmProviderKind] = mapped_column(Enum(LlmProviderKind))
    # internal은 "project://<llm 프로젝트명>" 표기를 허용 — 배포 도메인으로 자동 해석
    base_url: Mapped[str] = mapped_column(String(512))
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("llm_providers.id"))
    branch: Mapped[str] = mapped_column(String(128))  # 편집 대상 작업 브랜치
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChangeStatus(str, enum.Enum):
    proposed = "proposed"
    applied = "applied"
    rejected = "rejected"


class ProposedChange(Base):
    """LLM 수정 제안. 항상 diff로만 존재하며 승인(apply) 시에만 작업 브랜치에 커밋된다."""

    __tablename__ = "proposed_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    diff: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[ChangeStatus] = mapped_column(Enum(ChangeStatus), default=ChangeStatus.proposed)
    applied_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModuleType(str, enum.Enum):
    external_api = "external_api"
    internal_api = "internal_api"
    database = "database"
    file_storage = "file_storage"


class Module(Base):
    """코드가 의존하는 외부/내부 자원. 바인딩 시 규약된 환경변수로 자동 주입된다."""

    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    type: Mapped[ModuleType] = mapped_column(Enum(ModuleType))
    # 민감 필드(api_key, dsn, password, secret)는 저장 시 Fernet 암호화됨
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ModuleBinding(Base):
    __tablename__ = "module_bindings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"))
    env_prefix: Mapped[str] = mapped_column(String(32))  # 예: PAY → PAY_URL, PAY_API_KEY


class PreviewStatus(str, enum.Enum):
    running = "running"
    expired = "expired"
    failed = "failed"


class PreviewSession(Base):
    """편집 브랜치의 TTL 임시 프리뷰. development 프로필로 빌드해 별도 유닛으로 기동한다."""

    __tablename__ = "preview_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    branch: Mapped[str] = mapped_column(String(128))
    url: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[PreviewStatus] = mapped_column(Enum(PreviewStatus), default=PreviewStatus.running)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
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
