"""Thin wrappers around the docker CLI used by the experiment runner."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOCKER = shutil.which("docker") or str(
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe")
TOOLS_IMAGE = "mqtt-vs-rest/rest:latest"   # has iproute2 (tc) and python; used for sidecars
RESULTS_VOLUME = "mqtt-vs-rest-results"


def docker(*args: str, timeout: float | None = 120, check: bool = True, env: dict | None = None,
           cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([DOCKER, *args], capture_output=True, text=True, timeout=timeout, check=check,
                          env={**os.environ, **(env or {})}, cwd=cwd)


class Stack:
    """One Compose stack (rest-version or mqtt-version) with a fixed environment."""

    def __init__(self, arch: str, env: dict[str, str]) -> None:
        self.arch = arch
        self.dir = REPO / f"{arch}-version"
        self.project = f"{arch}-version"
        self.env = env

    def compose(self, *args: str, timeout: float | None = 180, check: bool = True) -> subprocess.CompletedProcess:
        return docker("compose", *args, timeout=timeout, check=check, env=self.env, cwd=self.dir)

    def container_id(self, service: str) -> str:
        out = self.compose("ps", "-a", "-q", service).stdout.split()
        if not out:
            raise RuntimeError(f"no container for service {service}")
        return out[0]

    def services_up(self) -> list[str]:
        return self.compose("ps", "--services", "--status", "running").stdout.split()


def exec_ok(container: str, *cmd: str, timeout: float = 5) -> bool:
    try:
        return docker("exec", container, *cmd, timeout=timeout, check=False).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def is_ready(container: str, service: str) -> bool:
    if service == "broker":
        return exec_ok(container, "mosquitto_pub", "-h", "localhost", "-t", "healthcheck", "-m", "ok", "-q", "0")
    return exec_ok(container, "python", "-c",
                   "import urllib.request; urllib.request.urlopen('http://localhost:8000/ready', timeout=1)")


def wait_ready(container: str, service: str, timeout: float = 60, poll: float = 0.2) -> float | None:
    """Poll until ready; returns host wall time (s) of readiness, or None on timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if is_ready(container, service):
            return time.time()
        time.sleep(poll)
    return None


def service_stats(container: str) -> dict | None:
    """The service's own /stats (counters + clock), read from inside the container."""
    result = docker("exec", container, "python", "-c",
                    "import urllib.request, sys; sys.stdout.write(urllib.request.urlopen("
                    "'http://localhost:8000/stats', timeout=2).read().decode())",
                    timeout=10, check=False)
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def apply_netem(container: str, netem_args: str) -> str:
    """Apply `tc netem` to a container's eth0 from a sidecar sharing its network namespace.

    A sidecar works for every container, including the Mosquitto image, which has
    no tc of its own. Returns the qdisc line tc reports, as evidence for meta.json.
    """
    docker("run", "--rm", "--net", f"container:{container}", "--cap-add", "NET_ADMIN", TOOLS_IMAGE,
           "sh", "-c", f"tc qdisc replace dev eth0 root netem {netem_args}", timeout=60)
    shown = docker("run", "--rm", "--net", f"container:{container}", TOOLS_IMAGE,
                   "tc", "qdisc", "show", "dev", "eth0", timeout=60)
    return shown.stdout.strip()


def clock_offset_ns(container: str) -> dict:
    """Container wall clock minus host wall clock, measured with one docker exec.

    Fault times are recorded on the host; message times on the container side.
    The offset lets the analysis line them up (uncertainty = half the round trip).
    """
    t0 = time.time_ns()
    result = docker("exec", container, "python", "-c", "import time; print(time.time_ns())", timeout=10)
    t1 = time.time_ns()
    container_ns = int(result.stdout.strip())
    return {"offset_ns": container_ns - (t0 + t1) // 2, "uncertainty_ns": (t1 - t0) // 2}


def ensure_results_volume() -> None:
    if docker("volume", "inspect", RESULTS_VOLUME, check=False).returncode != 0:
        docker("volume", "create", RESULTS_VOLUME)


def environment_info() -> dict:
    info = json.loads(docker("info", "--format", "{{json .}}").stdout)
    version = json.loads(docker("version", "--format", "{{json .}}").stdout)
    return {
        "docker_server": version.get("Server", {}).get("Version"),
        "docker_client": version.get("Client", {}).get("Version"),
        "docker_ncpu": info.get("NCPU"),
        "docker_mem_bytes": info.get("MemTotal"),
        "docker_kernel": info.get("KernelVersion"),
        "docker_os": info.get("OperatingSystem"),
        "cgroup_version": info.get("CgroupVersion"),
    }


def image_ids() -> dict:
    ids = {}
    for image in ("mqtt-vs-rest/rest:latest", "mqtt-vs-rest/mqtt:latest", "eclipse-mosquitto:2.0.20"):
        result = docker("image", "inspect", image, "--format", "{{.Id}}", check=False)
        ids[image] = result.stdout.strip() or None
    return ids
