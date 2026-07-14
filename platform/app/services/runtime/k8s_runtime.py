"""2차(enterprise) 런타임 — Kubernetes.

플랫폼은 매니페스트 생성기 역할만 한다. 롤링 업데이트·자가치유·스케줄링은 K8s에 위임.
kubernetes 패키지 + 클러스터 접근이 가능하면 직접 apply하고,
아니면 매니페스트 YAML을 k8s_manifest_dir에 기록한다 (kubectl apply -f 또는 GitOps 연계).

에러 정책(갭4): "클러스터 접근 불가"(패키지 없음/설정 없음)만 파일 폴백이고,
클러스터에 연결된 상태의 apply 실패는 3회 재시도 후 K8sApplyError로 표면화한다 —
조용한 폴백은 배포 성공으로 오인되므로 금지.

프로필 반영:
  development → replicas 1, 리소스 절반, Recreate 전략, {name}-dev 도메인
  release     → replicas 2(기본), 리소스 전량, RollingUpdate(maxUnavailable 0)
"""
import time
from pathlib import Path


class K8sApplyError(RuntimeError):
    pass

import yaml

from ...config import get_settings
from ...models import BuildProfile
from ..build import PROFILES
from .base import Endpoint, Runtime, RuntimeSpec


def _mem_k8s(limit: str, factor: float) -> str:
    units = {"k": "Ki", "m": "Mi", "g": "Gi"}
    unit = limit[-1].lower()
    if unit in units:
        return f"{int(float(limit[:-1]) * factor * 1024)}Mi" if unit == "g" else \
               f"{int(float(limit[:-1]) * factor)}{units[unit]}"
    return str(int(float(limit) * factor))


def _cpu_k8s(cpu: float, factor: float) -> str:
    return f"{int(cpu * factor * 1000)}m"


def build_manifests(spec: RuntimeSpec) -> list[dict]:
    settings = get_settings()
    profile_spec = PROFILES[spec.profile]
    factor = profile_spec.resource_factor
    ns = settings.k8s_namespace
    name = spec.unit_name
    labels = {
        "app.kubernetes.io/name": spec.project_name,
        "app.kubernetes.io/managed-by": "paas",
        "paas/profile": spec.profile.value,
    }
    image = (
        f"{settings.k8s_registry}/{spec.image_tag}" if settings.k8s_registry else spec.image_tag
    )
    replicas = spec.replicas if spec.profile == BuildProfile.release else 1
    is_release = spec.profile == BuildProfile.release

    resources = {
        "requests": {
            "memory": _mem_k8s(spec.memory_limit, factor * 0.5),
            "cpu": _cpu_k8s(spec.cpu_limit, factor * 0.5),
        },
        "limits": {
            "memory": _mem_k8s(spec.memory_limit, factor),
            "cpu": _cpu_k8s(spec.cpu_limit, factor),
        },
    }
    if spec.gpu:
        resources["limits"]["nvidia.com/gpu"] = 1

    container = {
        "name": "app",
        "image": image,
        "ports": [{"containerPort": spec.internal_port}],
        "env": [{"name": k, "value": v} for k, v in sorted(spec.env.items())],
        "resources": resources,
        "readinessProbe": {
            "httpGet": {"path": spec.health_check_path, "port": spec.internal_port},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
        },
    }

    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": ns, "labels": labels},
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app.kubernetes.io/name": spec.project_name,
                                          "paas/profile": spec.profile.value}},
            "strategy": (
                {"type": "RollingUpdate",
                 "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1}}
                if is_release
                else {"type": "Recreate"}
            ),
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [container],
                    "securityContext": {"runAsNonRoot": is_release} if is_release else {},
                },
            },
        },
    }

    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": ns, "labels": labels},
        "spec": {
            "selector": {"app.kubernetes.io/name": spec.project_name,
                         "paas/profile": spec.profile.value},
            "ports": [{"port": 80, "targetPort": spec.internal_port}],
        },
    }

    ingress = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": name,
            "namespace": ns,
            "labels": labels,
            "annotations": {
                "cert-manager.io/cluster-issuer": settings.k8s_cluster_issuer,
            },
        },
        "spec": {
            "ingressClassName": settings.k8s_ingress_class,
            "tls": [{"hosts": [spec.domain], "secretName": f"{name}-tls"}],
            "rules": [{
                "host": spec.domain,
                "http": {"paths": [{
                    "path": "/",
                    "pathType": "Prefix",
                    "backend": {"service": {"name": name, "port": {"number": 80}}},
                }]},
            }],
        },
    }
    return [deployment, service, ingress]


class K8sRuntime(Runtime):
    def start(self, spec: RuntimeSpec) -> Endpoint:
        manifests = build_manifests(spec)
        if not self._apply(manifests):
            self._write_manifests(spec, manifests)
        # 트래픽은 Ingress가 받으므로 프록시 전환 불필요. Service 주소를 참고용으로 반환.
        return Endpoint(host=f"{spec.unit_name}.{get_settings().k8s_namespace}.svc", port=80)

    def stop(self, project_name: str, profile: BuildProfile) -> None:
        spec = RuntimeSpec(project_name, "", 0, profile, "")
        api = self._apps_api()
        if api is None:
            return
        settings = get_settings()
        try:
            api.patch_namespaced_deployment_scale(
                spec.unit_name, settings.k8s_namespace, {"spec": {"replicas": 0}}
            )
        except Exception:
            pass

    def status(self, project_name: str, profile: BuildProfile) -> str:
        spec = RuntimeSpec(project_name, "", 0, profile, "")
        api = self._apps_api()
        if api is None:
            return "unknown (no cluster access)"
        try:
            dep = api.read_namespaced_deployment(spec.unit_name, get_settings().k8s_namespace)
        except Exception:
            return "stopped"
        ready = dep.status.ready_replicas or 0
        want = dep.spec.replicas or 0
        return "running" if want and ready >= want else f"progressing ({ready}/{want})"

    def logs(self, project_name: str, profile: BuildProfile, tail: int = 200) -> str:
        spec = RuntimeSpec(project_name, "", 0, profile, "")
        core = self._core_api()
        if core is None:
            return ""
        settings = get_settings()
        pods = core.list_namespaced_pod(
            settings.k8s_namespace,
            label_selector=f"app.kubernetes.io/name={project_name},paas/profile={profile.value}",
        )
        chunks = []
        for pod in pods.items:
            chunks.append(
                core.read_namespaced_pod_log(
                    pod.metadata.name, settings.k8s_namespace, tail_lines=tail
                )
            )
        return "\n---\n".join(chunks)

    # --- kubernetes 패키지는 선택 의존성: 없으면 매니페스트 파일 출력으로 대체 ---

    def _apply(self, manifests: list[dict]) -> bool:
        try:
            from kubernetes import client, config, utils  # noqa: PLC0415
        except ImportError:
            return False  # 패키지 없음 → 파일 폴백 (GitOps 경로)
        try:
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
        except Exception:
            return False  # 클러스터 설정 없음 → 파일 폴백

        # 여기부터는 클러스터에 연결된 상태 — 실패를 삼키지 않는다
        k8s = client.ApiClient()
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                for m in manifests:
                    utils.create_from_dict(k8s, m, apply=True)
                return True
            except Exception as e:  # noqa: BLE001 — 재시도 후 표면화
                last_error = e
                time.sleep(0.5 * (attempt + 1))
        raise K8sApplyError(
            f"K8s apply 실패 (3회 재시도 후): {str(last_error)[:500]}"
        )

    def _write_manifests(self, spec: RuntimeSpec, manifests: list[dict]) -> Path:
        out = get_settings().k8s_manifest_dir / f"{spec.unit_name}.yaml"
        out.write_text(
            yaml.safe_dump_all(manifests, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        return out

    @staticmethod
    def _apps_api():
        try:
            from kubernetes import client, config  # noqa: PLC0415
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            return client.AppsV1Api()
        except Exception:
            return None

    @staticmethod
    def _core_api():
        try:
            from kubernetes import client, config  # noqa: PLC0415
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            return client.CoreV1Api()
        except Exception:
            return None
