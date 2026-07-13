"""Build Manager.

빌드 옵션은 development / release 두 프로필로 구분한다 (BuildProfile).

  development: 디버깅 우선 — dev 서버(HMR/--reload), 소스맵, 리소스 절반, 단일 replica,
               이미지 태그에 "-dev" 접미사, {name}-dev.{base_domain} 도메인.
  release:     운영 최적화 — 프로덕션 빌드(minify), 멀티스테이지 이미지, 리소스 전량,
               2차(k8s)에서는 replicas 2 + 롤링 업데이트.

프로젝트 리포에 Dockerfile이 있으면 그것을 우선하고(--build-arg APP_PROFILE 전달),
없으면 templates/dockerfiles/{type}.{profile}.Dockerfile 템플릿을 사용한다.
"""
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings
from ..models import BuildProfile, Project, ProjectType

TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "dockerfiles"

# 프로젝트 타입별 컨테이너 내부 포트. (react release는 정적 파일을 caddy로 서빙)
INTERNAL_PORTS: dict[tuple[ProjectType, BuildProfile], int] = {
    (ProjectType.react, BuildProfile.development): 3000,
    (ProjectType.react, BuildProfile.release): 80,
    (ProjectType.node, BuildProfile.development): 3000,
    (ProjectType.node, BuildProfile.release): 3000,
    (ProjectType.python, BuildProfile.development): 8000,
    (ProjectType.python, BuildProfile.release): 8000,
    (ProjectType.llm, BuildProfile.development): 8000,
    (ProjectType.llm, BuildProfile.release): 8000,
}


@dataclass
class ProfileSpec:
    """프로필이 빌드·배포 전반에 미치는 효과를 한 곳에 모은 정의."""

    profile: BuildProfile
    tag_suffix: str
    env: dict[str, str]
    resource_factor: float  # release 대비 리소스 배율
    replicas: int  # 2차(k8s)에서 사용. 1차는 항상 1.

    def image_tag(self, project_name: str, git_sha: str) -> str:
        return f"{project_name}:{git_sha[:12]}{self.tag_suffix}"


PROFILES: dict[BuildProfile, ProfileSpec] = {
    BuildProfile.development: ProfileSpec(
        profile=BuildProfile.development,
        tag_suffix="-dev",
        env={"APP_ENV": "development", "NODE_ENV": "development"},
        resource_factor=0.5,
        replicas=1,
    ),
    BuildProfile.release: ProfileSpec(
        profile=BuildProfile.release,
        tag_suffix="",
        env={"APP_ENV": "production", "NODE_ENV": "production"},
        resource_factor=1.0,
        replicas=2,
    ),
}


@dataclass
class BuildResult:
    image_tag: str
    internal_port: int
    log_path: Path
    profile: BuildProfile
    extra_env: dict[str, str] = field(default_factory=dict)


def dockerfile_for(project_type: ProjectType, profile: BuildProfile, workdir: Path) -> Path:
    """리포 자체 Dockerfile 우선, 없으면 타입·프로필별 템플릿."""
    own = workdir / "Dockerfile"
    if own.exists():
        return own
    template = TEMPLATE_DIR / f"{project_type.value}.{profile.value}.Dockerfile"
    if not template.exists():
        raise FileNotFoundError(f"no dockerfile template: {template.name}")
    return template


def internal_port(project_type: ProjectType, profile: BuildProfile) -> int:
    return INTERNAL_PORTS[(project_type, profile)]


def build_image(project: Project, workdir: Path, git_sha: str, profile: BuildProfile) -> BuildResult:
    settings = get_settings()
    spec = PROFILES[profile]
    tag = spec.image_tag(project.name, git_sha)
    dockerfile = dockerfile_for(project.type, profile, workdir)

    log_path = settings.build_log_dir / f"{project.name}-{git_sha[:12]}{spec.tag_suffix}.log"
    cmd = [
        "docker", "build",
        "-f", str(dockerfile),
        "-t", tag,
        "--build-arg", f"APP_PROFILE={profile.value}",
        str(workdir),
    ]
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"$ {' '.join(cmd)}\n")
        log.flush()
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise BuildError(f"docker build failed (exit {proc.returncode})", log_path)

    return BuildResult(
        image_tag=tag,
        internal_port=internal_port(project.type, profile),
        log_path=log_path,
        profile=profile,
        extra_env=dict(spec.env),
    )


class BuildError(RuntimeError):
    def __init__(self, message: str, log_path: Path | None = None):
        super().__init__(message)
        self.log_path = log_path


def checkout(project: Project, git_sha: str | None = None) -> tuple[Path, str]:
    """clone 또는 pull 후 (작업 디렉토리, 해석된 커밋 SHA)를 반환한다."""
    settings = get_settings()
    workdir = settings.work_dir / project.name
    if not (workdir / ".git").exists():
        shutil.rmtree(workdir, ignore_errors=True)
        _run_git(["clone", "--branch", project.branch, project.git_url, str(workdir)])
    else:
        _run_git(["fetch", "origin", project.branch], cwd=workdir)
        _run_git(["checkout", project.branch], cwd=workdir)
        _run_git(["reset", "--hard", f"origin/{project.branch}"], cwd=workdir)
    if git_sha:
        _run_git(["checkout", git_sha], cwd=workdir)
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=workdir, capture_output=True, text=True, check=True
    )
    return workdir, out.stdout.strip()


def _run_git(args: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise BuildError(f"git {args[0]} failed: {proc.stderr.strip()[:500]}")
