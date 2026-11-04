"""End-to-end checks of the REST version, run as real local processes.

These are the plan's acceptance checks for one architecture: counts reconcile
across sent / processing / received, alerts match the injected spikes, no
sequence gaps, duplicates are detected, malformed input is rejected and
recorded, and an Alert Service outage is measurable. Takes about 15 seconds.
"""

import csv
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REST = REPO / "rest-version"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def base_env(results: Path, run_id: str) -> dict:
    return {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO), str(REST)]),
            "RESULTS_DIR": str(results), "RUN_ID": run_id, "LOG_LEVEL": "WARNING"}


def start_service(module: str, port: int, env: dict) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"rest_services.{module}:app", "--host", "127.0.0.1",
         "--port", str(port), "--no-access-log", "--log-level", "warning"],
        env=env, cwd=REST)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1)
            return proc
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"{module} did not become ready")


def run_simulator(env: dict, processing_port: int, rate: int, duration: float) -> dict:
    sim_env = {**env, "TARGET_URL": f"http://127.0.0.1:{processing_port}/readings",
               "RATE": str(rate), "DURATION_S": str(duration), "SENSOR_COUNT": "4",
               "SPIKE_PROBABILITY": "0.05", "REQUEST_TIMEOUT_S": "30"}
    subprocess.run([sys.executable, "-m", "rest_services.sensor_simulator"],
                   env=sim_env, cwd=REST, check=True, timeout=120)
    return json.loads((Path(env["RESULTS_DIR"]) / "simulator_summary.json").read_text())


def get_json(url: str) -> dict:
    return json.load(urllib.request.urlopen(url, timeout=5))


def post(url: str, body: bytes) -> int:
    request = urllib.request.Request(url, data=body, headers={"content-type": "application/json"})
    try:
        return urllib.request.urlopen(request, timeout=5).status
    except urllib.error.HTTPError as exc:
        return exc.code


def rows(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture
def rest_stack(tmp_path):
    procs = []
    alert_port, processing_port = free_port(), free_port()
    env = base_env(tmp_path, "it-normal")
    procs.append(start_service("alert", alert_port, env))
    procs.append(start_service("processing", processing_port,
                               {**env, "ALERT_URL": f"http://127.0.0.1:{alert_port}/events"}))
    yield env, alert_port, processing_port, tmp_path
    for proc in procs:
        proc.kill()
        proc.wait()


def test_normal_run_reconciles(rest_stack):
    env, alert_port, processing_port, results = rest_stack
    summary = run_simulator(env, processing_port, rate=200, duration=3)
    total = summary["workload"]["total"]
    producer = summary["producer"]

    sent = rows(results / "sent.csv")
    processing = rows(results / "processing.csv")
    received = rows(results / "received.csv")

    # scheduled = dispatched = acknowledged = processed = received
    assert producer["scheduled"] == producer["dispatched"] == producer["ok"] == total == 600
    assert len(sent) == total and all(r["status"] == "ok" for r in sent)
    assert len(processing) == total and all(r["status"] == "forwarded" for r in processing)
    assert len(received) == total and all(r["duplicate"] == "0" for r in received)
    assert {r["msg_id"] for r in sent} == {r["msg_id"] for r in received}

    # business output matches the trace
    alert_stats = get_json(f"http://127.0.0.1:{alert_port}/stats")
    assert alert_stats["alerts"] == summary["expected_alerts"] > 0
    assert sum(r["is_alert"] == "1" for r in received) == summary["expected_alerts"]

    # no per-sensor sequence gaps
    seqs = defaultdict(set)
    for r in received:
        seqs[r["sensor_id"]].add(int(r["seq"]))
    assert len(seqs) == 4
    assert all(s == set(range(len(s))) for s in seqs.values())

    # timestamps are ordered along the path and latency is positive
    for r in received:
        assert (int(r["sent_mono_ns"]) <= int(r["processing_received_mono_ns"])
                <= int(r["processing_completed_mono_ns"]) <= int(r["alert_received_mono_ns"]))
        assert float(r["latency_ms"]) > 0

    # shared clock: wall-minus-monotonic offset agrees across services (within 5 ms)
    offsets = [get_json(f"http://127.0.0.1:{port}/stats")["clock"]["wall_minus_mono_ns"]
               for port in (alert_port, processing_port)]
    assert abs(offsets[0] - offsets[1]) < 5_000_000


def test_duplicate_delivery_is_idempotent(rest_stack):
    env, alert_port, processing_port, results = rest_stack
    run_simulator(env, processing_port, rate=50, duration=0.2)
    first = rows(results / "received.csv")[0]
    event = {
        "schema_version": 1, "run_id": first["run_id"], "msg_id": first["msg_id"],
        "sensor_id": first["sensor_id"], "seq": int(first["seq"]), "event_ts_ns": 0,
        "sent_mono_ns": int(first["sent_mono_ns"]), "value": float(first["value"]), "unit": "C",
        "is_alert": first["is_alert"] == "1", "threshold": 30.0,
        "processing_received_mono_ns": 0, "processing_completed_mono_ns": 0,
    }
    before = get_json(f"http://127.0.0.1:{alert_port}/stats")
    assert post(f"http://127.0.0.1:{alert_port}/events", json.dumps(event).encode()) == 204
    after = get_json(f"http://127.0.0.1:{alert_port}/stats")
    assert after["duplicates"] == before["duplicates"] + 1
    assert after["unique"] == before["unique"] and after["alerts"] == before["alerts"]
    assert rows(results / "received.csv")[-1]["duplicate"] == "1"


def test_malformed_payload_is_rejected_and_recorded(rest_stack):
    env, alert_port, processing_port, results = rest_stack
    assert post(f"http://127.0.0.1:{processing_port}/readings", b'{"value": 1}') == 422
    assert post(f"http://127.0.0.1:{alert_port}/events", b"garbage") == 422
    assert get_json(f"http://127.0.0.1:{processing_port}/stats")["rejected"] == 1
    assert len(rows(results / "rejected_processing.csv")) == 1
    assert len(rows(results / "rejected_alert.csv")) == 1


def test_alert_outage_is_measurable(tmp_path):
    env = base_env(tmp_path, "it-outage")
    processing_port, dead_port = free_port(), free_port()   # nothing listens on dead_port
    proc = start_service("processing", processing_port,
                         {**env, "ALERT_URL": f"http://127.0.0.1:{dead_port}/events", "REQUEST_TIMEOUT_S": "1"})
    try:
        summary = run_simulator(env, processing_port, rate=20, duration=0.5)
    finally:
        proc.kill()
        proc.wait()
    assert summary["producer"]["failed"] == summary["workload"]["total"] == 10
    sent = rows(tmp_path / "sent.csv")
    assert all(r["status"] == "failed" and r["detail"] == "502" for r in sent)
    assert all(r["status"] == "forward_failed" for r in rows(tmp_path / "processing.csv"))
    assert not (tmp_path / "received.csv").exists()
