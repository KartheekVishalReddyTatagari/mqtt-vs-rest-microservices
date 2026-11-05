"""Per-container CPU and memory sampling (RQ3), via a streaming `docker stats`.

`docker stats` prints one JSON line per running container about once a
second. CPU is Docker's own CPUPerc: 100% = one full core. Samples are
stamped with host wall time on arrival and written to resources.csv.
"""

import csv
import json
import re
import subprocess
import threading
import time
from pathlib import Path

from docker_ops import DOCKER

_JSON = re.compile(r"\{.*?\}")
_UNITS = {"B": 1 / 2**20, "KiB": 1 / 1024, "kB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024}


def _mib(text: str) -> float:
    match = re.match(r"([\d.]+)\s*([A-Za-z]+)", text.strip())
    if not match:
        return float("nan")
    return float(match.group(1)) * _UNITS.get(match.group(2), float("nan"))


class ResourceMonitor:
    COLUMNS = ["wall_ns", "container", "service", "cpu_pct", "mem_mib", "net_io", "block_io", "pids"]

    def __init__(self, project: str, out_path: Path) -> None:
        self.project = project
        self.out_path = out_path
        self.samples = 0
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen([DOCKER, "stats", "--format", "{{json .}}"],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._thread = threading.Thread(target=self._read, name="resource-monitor", daemon=True)
        self._thread.start()

    def _read(self) -> None:
        prefix = f"{self.project}-"
        with open(self.out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.COLUMNS)
            for line in self._proc.stdout:
                now = time.time_ns()
                for blob in _JSON.findall(line):
                    try:
                        row = json.loads(blob)
                    except json.JSONDecodeError:
                        continue
                    name = row.get("Name", "")
                    if not name.startswith(prefix):
                        continue
                    service = name[len(prefix):].rsplit("-", 1)[0]
                    writer.writerow([now, name, service, row.get("CPUPerc", "").rstrip("%"),
                                     f"{_mib(row.get('MemUsage', '').split('/')[0]):.2f}",
                                     row.get("NetIO", ""), row.get("BlockIO", ""), row.get("PIDs", "")])
                    self.samples += 1
                f.flush()

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._thread:
            self._thread.join(timeout=10)
