"""빌드 옵션(development/release) 구분이 태그·템플릿·포트·환경에 반영되는지 검증."""
from pathlib import Path

import pytest

from app.models import BuildProfile, ProjectType
from app.services.build import PROFILES, TEMPLATE_DIR, dockerfile_for, internal_port


def test_image_tag_suffix():
    sha = "abcdef1234567890"
    dev = PROFILES[BuildProfile.development].image_tag("myapp", sha)
    rel = PROFILES[BuildProfile.release].image_tag("myapp", sha)
    assert dev == "myapp:abcdef123456-dev"
    assert rel == "myapp:abcdef123456"


def test_profile_env_split():
    assert PROFILES[BuildProfile.development].env["NODE_ENV"] == "development"
    assert PROFILES[BuildProfile.release].env["NODE_ENV"] == "production"
    assert PROFILES[BuildProfile.development].resource_factor < 1.0
    assert PROFILES[BuildProfile.release].replicas >= 2


@pytest.mark.parametrize("ptype", list(ProjectType))
@pytest.mark.parametrize("profile", list(BuildProfile))
def test_every_type_profile_has_template(ptype, profile, tmp_path):
    df = dockerfile_for(ptype, profile, tmp_path)
    assert df.exists()
    assert df.parent == TEMPLATE_DIR


def test_repo_dockerfile_takes_precedence(tmp_path):
    own = tmp_path / "Dockerfile"
    own.write_text("FROM scratch\n")
    assert dockerfile_for(ProjectType.python, BuildProfile.release, tmp_path) == own


def test_react_release_serves_static_port_80():
    assert internal_port(ProjectType.react, BuildProfile.release) == 80
    assert internal_port(ProjectType.react, BuildProfile.development) == 3000


def test_dev_templates_run_dev_servers():
    react_dev = (TEMPLATE_DIR / "react.development.Dockerfile").read_text(encoding="utf-8")
    python_dev = (TEMPLATE_DIR / "python.development.Dockerfile").read_text(encoding="utf-8")
    python_rel = (TEMPLATE_DIR / "python.release.Dockerfile").read_text(encoding="utf-8")
    assert "npm" in react_dev and "dev" in react_dev
    assert "--reload" in python_dev
    assert "--workers" in python_rel and "--reload" not in python_rel
