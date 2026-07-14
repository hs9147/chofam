from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import BuildProfile, DeploymentStatus, ProjectType


class ProjectCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")
    type: ProjectType
    git_url: str
    branch: str = "main"
    domain: str | None = None
    health_check_path: str = "/"
    memory_limit: str | None = None
    cpu_limit: float | None = None
    default_profile: BuildProfile = BuildProfile.release
    llm_config: dict | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: ProjectType
    git_url: str
    branch: str
    domain: str | None
    default_profile: BuildProfile
    created_at: datetime


class DeployRequest(BaseModel):
    # 빌드 옵션: development | release. 생략 시 프로젝트 기본값.
    profile: BuildProfile | None = None
    git_sha: str | None = None
    # False면 202 + building 레코드 즉시 반환, 파이프라인은 작업 큐에서 실행 (폴링으로 확인)
    wait: bool = True


class DeploymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    git_sha: str
    image_tag: str
    profile: BuildProfile
    status: DeploymentStatus
    host_port: int | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class EnvVarSet(BaseModel):
    key: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    value: str
    is_secret: bool = True


class LlmProviderCreate(BaseModel):
    name: str
    kind: str = Field(pattern=r"^(external|internal)$")
    base_url: str  # internal은 project://<프로젝트명> 형식만 허용 (아래 검증)
    api_key: str | None = None
    model: str

    @model_validator(mode="after")
    def _internal_must_use_project_scheme(self) -> "LlmProviderCreate":
        # kind="internal"은 "소스가 사외로 나가지 않는다"는 보장의 근거다.
        # base_url을 자유 문자열로 두면 라벨만 internal이고 실제로는 외부 URL을
        # 가리키는 설정 실수(또는 악용)를 코드가 전혀 막지 못한다 — 여기서 강제한다.
        if self.kind == "internal" and not self.base_url.startswith("project://"):
            raise ValueError(
                "internal 프로바이더는 base_url이 'project://<프로젝트명>' 형식이어야 합니다 "
                "(외부 URL을 쓰려면 kind를 external로 등록하세요)"
            )
        return self


class LlmProviderOut(BaseModel):
    id: int
    name: str
    kind: str
    base_url: str
    model: str
    has_api_key: bool


class ChatSessionCreate(BaseModel):
    project_id: int
    provider_id: int
    branch: str | None = None  # 기본: paas/chat-{session_id}


class ChatMessageIn(BaseModel):
    content: str
    files: list[str] = []  # 컨텍스트로 포함할 리포 내 파일 경로


class ChatReply(BaseModel):
    reply: str
    proposed_change_id: int | None = None


class ReviewRequest(BaseModel):
    provider_id: int
    diff: str | None = None  # 생략 시 base_ref..HEAD로 계산
    base_ref: str | None = None


class ModuleCreate(BaseModel):
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,40}$")
    type: str = Field(pattern=r"^(external_api|internal_api|database|file_storage)$")
    config: dict = {}


class ModuleBind(BaseModel):
    env_prefix: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,24}$")


class PreviewCreate(BaseModel):
    branch: str | None = None
    ttl_minutes: int = Field(default=60, ge=5, le=480)


class PreviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    branch: str
    url: str
    status: str
    expires_at: datetime


class ApiKeyCreate(BaseModel):
    name: str
    is_admin: bool = False


class ApiKeyIssued(BaseModel):
    name: str
    key: str  # 발급 시 1회만 노출
    is_admin: bool
