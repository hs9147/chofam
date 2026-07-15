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


def test_html_serves_static_files_port_80():
    assert internal_port(ProjectType.html, BuildProfile.release) == 80
    assert internal_port(ProjectType.html, BuildProfile.development) == 80
    for profile in ("development", "release"):
        content = (TEMPLATE_DIR / f"html.{profile}.Dockerfile").read_text(encoding="utf-8")
        assert "caddy" in content and "file-server" in content


def test_streamlit_runs_via_streamlit_cli_port_8501():
    assert internal_port(ProjectType.streamlit, BuildProfile.release) == 8501
    assert internal_port(ProjectType.streamlit, BuildProfile.development) == 8501
    dev = (TEMPLATE_DIR / "streamlit.development.Dockerfile").read_text(encoding="utf-8")
    rel = (TEMPLATE_DIR / "streamlit.release.Dockerfile").read_text(encoding="utf-8")
    assert "streamlit" in dev and "--server.runOnSave=true" in dev
    assert "streamlit" in rel and "--server.runOnSave=true" not in rel
    assert "--server.port=8501" in dev and "--server.port=8501" in rel
