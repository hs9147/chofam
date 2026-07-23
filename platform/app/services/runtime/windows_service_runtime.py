"""1차(small) 대안 런타임 — Windows Service (Docker 없이 네이티브 프로세스로 실행).

IIS/Apache 뒤에 배치하는 Windows 환경 등 Docker Engine을 쓸 수 없는 구성을 위한
런타임이다. 컨테이너 이미지 대신 체크아웃된 리포 루트의 paas-start.cmd(필수 관례 —
PORT 환경변수로 리슨 포트를 전달받아 그 포트에서 서비스를 띄운다)를
nssm(Non-Sucking Service Manager, public domain)으로 Windows Service에 등록해 실행한다.

Docker와 달리 네이티브 프로세스라 플랫폼이 바인드 주소를 강제할 방법이 없다 — PORT와
함께 HOST=127.0.0.1도 넘겨주므로, 앱이 이를 지켜 바인드하면 프록시(단일 외부 포트)만
접근 가능해진다. 앱이 HOST를 무시하고 0.0.0.0에 바인드할 수도 있으므로, 운영 환경에서는
Windows 방화벽으로 외부에서 port_range(PAAS_PORT_RANGE_START~END) 인바운드를 반드시
차단해야 한다(3.6절 문서 참고).

DockerRuntime과 동일한 블루-그린 패턴: 서비스 이름은 {unit}-a / {unit}-b를 번갈아
쓰고, 새 슬롯이 헬스체크를 통과한 뒤에만 이전 슬롯을 제거한다.
"""
import socket
import subprocess
import time
import urllib.request

from ...config import get_settings
from ...models import BuildProfile
from .base import Endpoint, Runtime, RuntimeSpec


class WindowsServiceError(RuntimeError):
    pass


def allocate_port() -> int:
    settings = get_settings()
    for port in range(settings.port_range_start, settings.port_range_end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("no free port in configured range")


def _sc_binary() -> str:
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    if shutil.which("sc"):
        return "sc"
    default_sc = r"C:\Windows\System32\sc.exe"
    if os.path.exists(default_sc):
        return default_sc
    return "sc"


def _nssm_binary() -> str:
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    configured = get_settings().nssm_path
    if os.path.exists(configured):
        return configured
    found = shutil.which(configured)
    if found:
        return found
    candidates = [
        r"C:\tools\nssm-2.24\win64\nssm.exe",
        r"C:\tools\nssm-2.24\win32\nssm.exe",
        r"C:\tools\nssm\nssm.exe",
        r"C:\Program Files\nssm\win64\nssm.exe",
        r"C:\Program Files\nssm\nssm.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return configured


class WindowsServiceRuntime(Runtime):
    def start(self, spec: RuntimeSpec) -> Endpoint:
        settings = get_settings()
        workdir = settings.work_dir / spec.project_name
        start_script = workdir / "paas-start.cmd"
        if not start_script.exists():
            raise WindowsServiceError(
                "windows_service 런타임은 리포 루트에 paas-start.cmd가 필요합니다 "
                f"(PORT 환경변수로 리슨 포트 전달): {start_script}"
            )

        host_port = allocate_port()
        old_slot = self._current_slot(spec.unit_name)
        slot = "b" if old_slot == "a" else "a"
        name = f"{spec.unit_name}-{slot}"
        log_path = settings.build_log_dir / f"{name}.log"
        env_pairs = " ".join(
            f"{k}={v}" for k, v in {**spec.env, "PORT": str(host_port), "HOST": "127.0.0.1"}.items()
        )

        self._nssm("install", name, str(start_script))
        self._nssm("set", name, "AppDirectory", str(workdir))
        self._nssm("set", name, "AppEnvironmentExtra", env_pairs)
        self._nssm("set", name, "AppStdout", str(log_path))
        self._nssm("set", name, "AppStderr", str(log_path))
        self._nssm("start", name)

        if not self._wait_healthy(host_port, spec.health_check_path):
            self._teardown(name)
            raise WindowsServiceError(f"health check failed on :{host_port}")

        if old_slot is not None:
            self._teardown(f"{spec.unit_name}-{old_slot}")
        return Endpoint(host="127.0.0.1", port=host_port)

    def stop(self, project_name: str, profile: BuildProfile) -> None:
        spec = RuntimeSpec(project_name, "", 0, profile, "")
        for slot in ("a", "b"):
            name = f"{spec.unit_name}-{slot}"
            if self._exists(name):
                self._teardown(name)

    def status(self, project_name: str, profile: BuildProfile) -> str:
        spec = RuntimeSpec(project_name, "", 0, profile, "")
        slot = self._current_slot(spec.unit_name)
        if slot is None:
            return "stopped"
        return self._query_state(f"{spec.unit_name}-{slot}")

    def logs(self, project_name: str, profile: BuildProfile, tail: int = 200) -> str:
        spec = RuntimeSpec(project_name, "", 0, profile, "")
        slot = self._current_slot(spec.unit_name)
        if slot is None:
            return ""
        log_path = get_settings().build_log_dir / f"{spec.unit_name}-{slot}.log"
        if not log_path.exists():
            return ""
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-tail:])

    def _current_slot(self, unit_name: str) -> str | None:
        for slot in ("a", "b"):
            if self._exists(f"{unit_name}-{slot}"):
                return slot
        return None

    def _exists(self, name: str) -> bool:
        try:
            proc = subprocess.run([_sc_binary(), "query", name], capture_output=True, text=True)
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    def _query_state(self, name: str) -> str:
        try:
            proc = subprocess.run([_sc_binary(), "query", name], capture_output=True, text=True)
            if proc.returncode != 0:
                return "stopped"
            out = proc.stdout.upper()
            if "RUNNING" in out:
                return "running"
            if "STOPPED" in out:
                return "stopped"
            return "unknown"
        except FileNotFoundError:
            return "stopped"

    def _teardown(self, name: str) -> None:
        nssm = _nssm_binary()
        try:
            subprocess.run([nssm, "stop", name], capture_output=True, text=True)
            subprocess.run([nssm, "remove", name, "confirm"], capture_output=True, text=True)
        except FileNotFoundError:
            pass

    def _nssm(self, *args: str) -> None:
        nssm = _nssm_binary()
        try:
            proc = subprocess.run([nssm, *args], capture_output=True, text=True)
        except FileNotFoundError as e:
            raise WindowsServiceError(
                f"nssm 실행 파일을 찾을 수 없습니다 (PAAS_NSSM_PATH={get_settings().nssm_path}): {e}"
            ) from e
        if proc.returncode != 0:
            raise WindowsServiceError(
                f"nssm {args[0]} 실패 (nssm 미설치 시 PAAS_NSSM_PATH 확인): "
                f"{(proc.stderr or proc.stdout).strip()[:500]}"
            )

    @staticmethod
    def _wait_healthy(port: int, path: str, timeout: float = 60.0) -> bool:
        url = f"http://127.0.0.1:{port}{path}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as res:
                    if res.status < 500:
                        return True
            except Exception:
                pass
            time.sleep(2)
        return False
