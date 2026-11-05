"""End-to-end checks against the real Docker stacks (run with `pytest -m docker`).

- Equivalence: REST and MQTT, given the same workload, deliver the same
  business output (same readings, same alerts) at the Alert Service.
- MQTT persistent sessions: with QoS 1 an Alert Service killed mid-run loses
  nothing (the broker queues for it); with QoS 0 the messages sent while it
  was down are lost.

Each test takes 30-60 seconds.
"""

import csv
import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCKER = shutil.which("docker") or str(
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DockerDesktop/resources/bin/docker.exe")

pytestmark = pytest.mark.docker

import sys  # noqa: E402

sys.path.insert(0, str(REPO / "experiments"))
from export_results import delete_run, export_run  # noqa: E402


def compose(arch: str, env: dict, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([DOCKER, "compose", *args], cwd=REPO / f"{arch}-version",
                          env={**os.environ, **env}, capture_output=True, text=True, check=check)


def run_stack(arch: str, run_id: str, tmp: Path, extra: dict | None = None, fault=None) -> Path:
    env = {"RUN_ID": run_id, "RATE": "100", "DURATION_S": "6", "SEED": "11", "SENSOR_COUNT": "3",
           "SPIKE_PROBABILITY": "0.05", **(extra or {})}
    compose(arch, env, "up", "-d", "--build")
    try:
        if fault:
            fault(lambda *a: compose(arch, env, *a))
        compose(arch, env, "wait", "sensor-simulator", check=False)
        time.sleep(3)                                     # let in-flight messages drain
        compose(arch, env, "stop")
    finally:
        compose(arch, env, "down", "-v", check=False)
    dest = export_run(f"{arch}/{run_id}", tmp, docker=DOCKER)
    delete_run(f"{arch}/{run_id}", docker=DOCKER)
    return dest


def unique_received(folder: Path) -> dict:
    with open(folder / "received.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    return {(r["sensor_id"], int(r["seq"])): (r["value"], r["is_alert"]) for r in rows}


def summary(folder: Path) -> dict:
    return json.loads((folder / "simulator_summary.json").read_text())


@pytest.fixture
def run_id():
    return f"pytest-{uuid.uuid4().hex[:8]}"


def test_rest_and_mqtt_produce_the_same_business_output(tmp_path, run_id):
    rest = run_stack("rest", run_id, tmp_path)
    mqtt = run_stack("mqtt", run_id, tmp_path, {"MQTT_QOS": "1"})
    assert summary(rest)["trace_id"] == summary(mqtt)["trace_id"]
    rest_out, mqtt_out = unique_received(rest), unique_received(mqtt)
    assert len(rest_out) == len(mqtt_out) == 600
    assert rest_out == mqtt_out          # same readings, same values, same alert flags
    alerts = sum(flag == "1" for _, flag in rest_out.values())
    assert alerts == summary(rest)["expected_alerts"] == summary(mqtt)["expected_alerts"] > 0


def kill_alert_for(seconds: float):
    def fault(compose_cmd) -> None:
        time.sleep(4)
        compose_cmd("kill", "-s", "SIGKILL", "alert")
        time.sleep(seconds)
        compose_cmd("start", "alert")
    return fault


def test_mqtt_qos1_queues_for_a_crashed_subscriber(tmp_path, run_id):
    folder = run_stack("mqtt", run_id, tmp_path, {"MQTT_QOS": "1", "DURATION_S": "10"}, kill_alert_for(3))
    assert len(unique_received(folder)) == summary(folder)["workload"]["total"] == 1000


def test_mqtt_qos0_loses_messages_while_the_subscriber_is_down(tmp_path, run_id):
    folder = run_stack("mqtt", run_id, tmp_path, {"MQTT_QOS": "0", "DURATION_S": "10"}, kill_alert_for(3))
    sim = summary(folder)
    assert sim["producer"]["ok"] == 1000          # the broker accepted every message...
    assert len(unique_received(folder)) < 900     # ...but ~300 never reached the Alert Service
