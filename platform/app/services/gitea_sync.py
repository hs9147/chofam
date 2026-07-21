"""Gitea 기준으로 조직·프로젝트 현황을 동기화한다 (관리자 수동 트리거, POST /orgs/sync).

방향은 Gitea → 플랫폼 한쪽만이다: Gitea에는 있지만 플랫폼 DB에 없는 조직/리포를
찾아 Organization/Project 행을 새로 만든다. 반대 방향(플랫폼에만 있는 걸 Gitea에
반영하거나, Gitea에서 지워진 걸 플랫폼에서도 지우는 것)은 다루지 않는다 — 기존
ensure_org/ensure_repo가 이미 "플랫폼 → Gitea" 방향을 담당하고 있으므로, 이 모듈은
그 반대 경로(수동으로 Gitea에 만든 조직/리포를 플랫폼이 뒤늦게 인식)만 메운다.

리포의 Project.type은 얕은 clone으로 시그니처 파일을 확인해 추론한다
(services/build.py의 detect_project_type — detect_composite_components와 동일한
"추측성 기본값 금지" 원칙). 추론할 수 없거나 이름 규칙(^[a-z0-9][a-z0-9-]{1,40}$)에
안 맞는 리포는 만들지 않고 이유와 함께 건너뛴다.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Organization, Project
from . import gitea
from .build import detect_project_type
from .git_auth import auth_args

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def sync_from_gitea(db: Session) -> dict:
    orgs_created: list[str] = []
    projects_created: list[str] = []
    skipped: list[dict[str, str]] = []

    existing_org_names = {row[0] for row in db.execute(select(Organization.name)).all()}
    existing_project_names = {row[0] for row in db.execute(select(Project.name)).all()}

    for gitea_org in gitea.list_orgs():
        org_name = gitea_org["username"]
        if not NAME_RE.match(org_name):
            skipped.append({"name": org_name, "kind": "org", "reason": "이름 규칙에 맞지 않음"})
            continue

        if org_name in existing_org_names:
            org = db.execute(
                select(Organization).where(Organization.name == org_name)
            ).scalar_one()
        else:
            org = Organization(name=org_name)
            db.add(org)
            db.commit()
            db.refresh(org)
            existing_org_names.add(org_name)
            orgs_created.append(org_name)

        for repo in gitea.list_org_repos(org_name):
            repo_name = repo["name"]
            if not NAME_RE.match(repo_name):
                skipped.append({"name": repo_name, "kind": "project", "reason": "이름 규칙에 맞지 않음"})
                continue
            if repo_name in existing_project_names:
                continue  # 이미 등록됨(이 조직이거나, 이름이 겹치는 다른 조직 소속)

            branch = repo.get("default_branch") or "main"
            workdir = None
            try:
                workdir = _shallow_clone(repo["clone_url"], branch)
                ptype = detect_project_type(workdir)
            except RuntimeError as e:
                skipped.append({"name": repo_name, "kind": "project", "reason": f"clone 실패: {e}"})
                continue
            finally:
                if workdir is not None:
                    shutil.rmtree(workdir, ignore_errors=True)

            if ptype is None:
                skipped.append({
                    "name": repo_name, "kind": "project",
                    "reason": "타입을 추론할 수 없음 (시그니처 파일 없음)",
                })
                continue

            project = Project(
                name=repo_name, type=ptype, organization_id=org.id,
                git_url=repo["clone_url"], branch=branch,
            )
            db.add(project)
            db.commit()
            existing_project_names.add(repo_name)
            projects_created.append(repo_name)

    return {
        "orgs_created": orgs_created,
        "projects_created": projects_created,
        "skipped": skipped,
    }


def _shallow_clone(git_url: str, branch: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="gitea-sync-"))
    proc = subprocess.run(
        ["git", *auth_args(git_url), "clone", "--depth", "1", "--branch", branch, git_url, str(tmp)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        shutil.rmtree(tmp, ignore_errors=True)
        raise RuntimeError(proc.stderr.strip()[:300])
    return tmp
