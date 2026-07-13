"""2차(enterprise) 매니페스트 생성 — 프로필별 replicas/전략/리소스 차등 검증."""
from app.models import BuildProfile
from app.services.runtime.base import RuntimeSpec
from app.services.runtime.k8s_runtime import build_manifests


def _spec(profile: BuildProfile) -> RuntimeSpec:
    return RuntimeSpec(
        project_name="shop",
        image_tag="shop:abc123",
        internal_port=8000,
        profile=profile,
        domain="shop.apps.test",
        env={"APP_ENV": "production"},
        memory_limit="1g",
        cpu_limit=1.0,
        replicas=2,
        health_check_path="/healthz",
    )


def test_release_manifests():
    dep, svc, ing = build_manifests(_spec(BuildProfile.release))
    assert dep["kind"] == "Deployment"
    assert dep["spec"]["replicas"] == 2
    assert dep["spec"]["strategy"]["type"] == "RollingUpdate"
    assert dep["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"] == 0
    container = dep["spec"]["template"]["spec"]["containers"][0]
    assert container["readinessProbe"]["httpGet"]["path"] == "/healthz"
    assert svc["spec"]["ports"][0]["targetPort"] == 8000
    assert ing["spec"]["rules"][0]["host"] == "shop.apps.test"
    assert "cert-manager.io/cluster-issuer" in ing["metadata"]["annotations"]


def test_development_manifests_are_scaled_down():
    dep, _, _ = build_manifests(_spec(BuildProfile.development))
    assert dep["spec"]["replicas"] == 1
    assert dep["spec"]["strategy"]["type"] == "Recreate"
    assert dep["metadata"]["name"].endswith("-dev")
    limits = dep["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
    # release 1g/1cpu 대비 development는 절반
    assert limits["cpu"] == "500m"


def test_gpu_request():
    spec = _spec(BuildProfile.release)
    spec.gpu = True
    dep, _, _ = build_manifests(spec)
    limits = dep["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]
    assert limits["nvidia.com/gpu"] == 1
