"""후속1 — GitOps(ArgoCD) 연계: 매니페스트가 GitOps 리포에 커밋·푸시되는지 검증."""
import subprocess

import pytest

from app.config import get_settings
from app.models import BuildProfile
from app.services.runtime.base import RuntimeSpec
from app.services.runtime.k8s_runtime import K8sRuntime


def _spec(image: str = "shop:abc") -> RuntimeSpec:
    return RuntimeSpec("shop", image, 8000, BuildProfile.release, "shop.apps.test")


@pytest.fixture
def gitops_env(monkeypatch, tmp_path, fresh_settings):
    bare = tmp_path / "gitops.git"
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main", str(bare)], check=True)
    monkeypatch.setenv("PAAS_K8S_GITOPS_REPO", str(bare))
    monkeypatch.setenv("PAAS_WORK_DIR", str(tmp_path / "work"))
    get_settings.cache_clear()
    return bare


def _log(bare) -> list[str]:
    out = subprocess.run(
        ["git", "log", "--format=%s", "main"], cwd=bare, capture_output=True, text=True
    )
    return out.stdout.strip().splitlines()


def test_deploy_pushes_manifest_to_gitops_repo(gitops_env, tmp_path):
    endpoint = K8sRuntime().start(_spec())
    assert endpoint.port == 80

    checkout = tmp_path / "verify"
    subprocess.run(["git", "clone", "-q", str(gitops_env), str(checkout)], check=True)
    manifest = checkout / "apps" / "paas-shop.yaml"
    assert manifest.exists()
    content = manifest.read_text(encoding="utf-8")
    assert "kind: Deployment" in content and "shop:abc" in content
    assert _log(gitops_env) == ["paas: deploy paas-shop (shop:abc)"]


def test_redeploy_same_manifest_skips_commit(gitops_env):
    K8sRuntime().start(_spec())
    K8sRuntime().start(_spec())  # 동일 내용 — 커밋 없음
    assert len(_log(gitops_env)) == 1

    K8sRuntime().start(_spec(image="shop:def456"))  # 새 이미지 — 커밋 추가
    assert len(_log(gitops_env)) == 2
