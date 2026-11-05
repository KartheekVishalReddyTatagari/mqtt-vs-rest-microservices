"""Experiment runner: one command runs, measures and records an experiment.

Per run (see docs/architecture.md and the design plan, section 8.1):
  1. clean up leftovers, start the stack's long-running services, wait until ready
  2. apply network impairment (tc netem) to every container, if the run has one
  3. measure the container-vs-host clock offset, start CPU/memory sampling
  4. start the Sensor Simulator (it pauses START_DELAY_S so netem can be applied to it too)
  5. inject the scheduled fault, recording exact host timestamps
  6. wait for the simulator to finish, then for in-flight messages to drain
  7. stop the stack gracefully (services write summaries), save logs, remove it
  8. copy the results out of the Docker volume and write meta.json

Usage
  python experiments/runner.py --campaign experiments/config/campaign.json [--only E1,E3] [--dry-run]
  python experiments/runner.py --profile mqtt-q1 --rate 500 --duration 60 --repetitions 3 \
      [--netem delay50] [--outage alert:20:10] [--broker abrupt:20:10]

A finished run (meta.json with status "complete") is skipped when the
campaign is started again, so an interrupted campaign simply resumes.
"""

import argparse
import json
import platform
import random
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from docker_ops import (REPO, Stack, apply_netem, clock_offset_ns, docker, ensure_results_volume,  # noqa: E402
                        environment_info, image_ids, service_stats, wait_ready)
from export_results import delete_run, export_to  # noqa: E402
from monitor import ResourceMonitor  # noqa: E402

PROFILES = {
    "rest":       ("rest", {"RETRY_ENABLED": "false"}),
    "rest-retry": ("rest", {"RETRY_ENABLED": "true"}),
    "mqtt-q0":    ("mqtt", {"MQTT_QOS": "0"}),
    "mqtt-q1":    ("mqtt", {"MQTT_QOS": "1"}),
    "mqtt-q2":    ("mqtt", {"MQTT_QOS": "2"}),
}

NETEM = {
    "delay50":       "delay 50ms 5ms",
    "delay100":      "delay 100ms 10ms",
    "loss1":         "loss 1%",
    "loss5":         "loss 5%",
    "delay50-loss1": "delay 50ms 5ms loss 1%",
}

LONG_RUNNING = {"rest": ["alert", "processing"], "mqtt": ["broker", "alert", "processing"]}
START_DELAY_S = 3.0
DRAIN_QUIET_S = 5.0
DRAIN_MAX_S = 90.0
RESULTS_ROOT = REPO / "results" / "raw"


@dataclass
class RunSpec:
    campaign: str
    experiment: str
    profile: str
    rate: float
    duration_s: float
    repetition: int
    seed: int = 42
    sensor_count: int = 5
    warmup_s: float = 5.0
    netem: str | None = None
    fault: dict | None = None
    extra_env: dict = field(default_factory=dict)

    @property
    def arch(self) -> str:
        return PROFILES[self.profile][0]

    @property
    def scenario(self) -> str:
        if self.fault and self.fault["kind"] == "outage":
            return f"{self.fault['service']}-down{int(self.fault['duration_s'])}s"
        if self.fault and self.fault["kind"] == "broker":
            return f"broker-{self.fault['mode']}{int(self.fault['duration_s'])}s"
        return self.netem or "base"

    @property
    def run_id(self) -> str:
        return (f"{self.campaign}-{self.experiment}-{self.profile}-{int(self.rate)}-"
                f"{self.scenario}-r{self.repetition:02d}")

    @property
    def total(self) -> int:
        return int(self.rate * self.duration_s)

    def env(self) -> dict[str, str]:
        return {
            "RUN_ID": self.run_id, "RATE": str(self.rate), "DURATION_S": str(self.duration_s),
            "SEED": str(self.seed), "SENSOR_COUNT": str(self.sensor_count),
            "START_DELAY_S": str(START_DELAY_S), "LOG_LEVEL": "INFO",
            **PROFILES[self.profile][1], **self.extra_env,
        }

    def estimated_s(self) -> float:
        return self.duration_s + START_DELAY_S + 30


_CAMPAIGN_GIT: dict | None = None   # captured once when the images are built


def git_info() -> dict:
    """Commit the images were built from. Captured at campaign start, because later
    edits to analysis code do not change the images and should not mark runs dirty."""
    if _CAMPAIGN_GIT is not None:
        return _CAMPAIGN_GIT

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()
    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def inject_fault(stack: Stack, spec: RunSpec, workload_start: float, events: list) -> None:
    fault = spec.fault
    service = "broker" if fault["kind"] == "broker" else fault["service"]
    container = stack.container_id(service)
    time.sleep(max(0.0, workload_start + fault["start_s"] - time.time()))

    graceful = fault.get("mode") == "graceful" or fault.get("signal") == "SIGTERM"
    events.append({"event": "fault_start", "service": service, "graceful": graceful, "host_wall_ns": time.time_ns()})
    if graceful:
        docker("stop", "-t", "10", container, timeout=60)
    else:
        docker("kill", "-s", "SIGKILL", container, timeout=60)
    events.append({"event": "service_down", "service": service, "host_wall_ns": time.time_ns()})

    time.sleep(max(0.0, workload_start + fault["start_s"] + fault["duration_s"] - time.time()))
    events.append({"event": "restart", "service": service, "host_wall_ns": time.time_ns()})
    docker("start", container, timeout=60)
    if spec.netem:  # a restarted container gets a fresh network namespace
        apply_netem(container, NETEM[spec.netem])
    ready_at = wait_ready(container, service, timeout=60)
    events.append({"event": "ready", "service": service,
                   "host_wall_ns": int(ready_at * 1e9) if ready_at else None})


def drain(stack: Stack, expected: int) -> dict:
    """Wait until the Alert Service has every message or stops receiving new ones."""
    alert = stack.container_id("alert")
    start = time.time()
    last, last_change = -1, start
    reason = "drain timeout"
    while time.time() - start < DRAIN_MAX_S:
        stats = service_stats(alert) or {}
        unique = stats.get("unique", -1)
        if unique != last:
            last, last_change = unique, time.time()
        if unique >= expected:
            reason = "all received"
            break
        if time.time() - last_change >= DRAIN_QUIET_S:
            reason = f"no new messages for {DRAIN_QUIET_S:.0f}s"
            break
        time.sleep(0.5)
    return {"drain_s": round(time.time() - start, 2), "alert_unique_at_end": last, "expected": expected,
            "reason": reason}


def run_one(spec: RunSpec, out_root: Path = RESULTS_ROOT) -> dict:
    out_dir = out_root / spec.campaign / spec.experiment / spec.run_id
    meta_path = out_dir / "meta.json"
    if meta_path.exists() and json.loads(meta_path.read_text()).get("status") == "complete":
        log(f"skip (done) {spec.run_id}")
        return json.loads(meta_path.read_text())

    stack = Stack(spec.arch, spec.env())
    meta: dict = {"run_id": spec.run_id, "spec": asdict(spec), "status": "started",
                  "started_host_wall_ns": time.time_ns(), "git": git_info(),
                  "python_host": platform.python_version(), "host": platform.platform(),
                  "start_delay_s": START_DELAY_S, "drain_policy": {"quiet_s": DRAIN_QUIET_S, "max_s": DRAIN_MAX_S},
                  "monitor_interval_s": "about 1 (docker stats stream)"}
    events: list = []
    monitor = ResourceMonitor(stack.project, out_dir / "resources.csv")
    log(f"run {spec.run_id} ({spec.total} msgs)")
    try:
        for arch in ("rest", "mqtt"):   # leftovers from an interrupted run
            Stack(arch, {}).compose("down", "-v", "--remove-orphans", check=False, timeout=120)
        delete_run(f"{spec.arch}/{spec.run_id}")
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        stack.compose("up", "-d", "--wait", *LONG_RUNNING[spec.arch], timeout=240)
        events.append({"event": "stack_ready", "host_wall_ns": time.time_ns()})
        if spec.netem:
            meta["netem"] = {"profile": spec.netem, "args": NETEM[spec.netem], "applied": {}}
            for service in LONG_RUNNING[spec.arch]:
                meta["netem"]["applied"][service] = apply_netem(stack.container_id(service), NETEM[spec.netem])
        meta["clock_offset"] = clock_offset_ns(stack.container_id("alert"))
        monitor.start()

        stack.compose("up", "-d", "--no-deps", "sensor-simulator", timeout=120)
        sim_started = time.time()
        simulator = stack.container_id("sensor-simulator")
        if spec.netem:
            meta["netem"]["applied"]["sensor-simulator"] = apply_netem(simulator, NETEM[spec.netem])
        workload_start = sim_started + START_DELAY_S + 0.5   # approximate; exact start is in the summary
        events.append({"event": "simulator_started", "host_wall_ns": int(sim_started * 1e9)})

        if spec.fault:
            inject_fault(stack, spec, workload_start, events)

        wait_timeout = spec.duration_s + START_DELAY_S + 300
        exit_code = docker("wait", simulator, timeout=wait_timeout).stdout.strip()
        events.append({"event": "simulator_exited", "exit_code": exit_code, "host_wall_ns": time.time_ns()})
        meta["drain"] = drain(stack, spec.total)
        events.append({"event": "drained", "host_wall_ns": time.time_ns()})
        meta["service_stats"] = {svc: service_stats(stack.container_id(svc)) for svc in ("processing", "alert")}
        monitor.stop()

        stack.compose("stop", "-t", "15", timeout=180)
        (out_dir / "logs.txt").write_text(stack.compose("logs", "--no-color", "--timestamps",
                                                        timeout=120, check=False).stdout, encoding="utf-8")
        meta["status"] = "complete" if exit_code == "0" else f"simulator exit {exit_code}"
    except Exception as exc:  # record the failure and move on to the next run
        meta["status"] = "failed"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        log(f"FAILED {spec.run_id}: {meta['error']}")
    finally:
        monitor.stop()
        stack.compose("down", "-v", "--remove-orphans", check=False, timeout=180)
        try:
            export_to(f"{spec.arch}/{spec.run_id}", out_dir)
            delete_run(f"{spec.arch}/{spec.run_id}")
        except subprocess.CalledProcessError as exc:
            meta.setdefault("error", f"export failed: {exc}")
            meta["status"] = "failed"
        meta["events"] = events
        meta["resource_samples"] = monitor.samples
        meta["finished_host_wall_ns"] = time.time_ns()
        out_dir.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log(f"  -> {meta['status']} (drain {meta.get('drain', {}).get('reason', '-')})")
    return meta


def expand_campaign(config: dict) -> list[RunSpec]:
    defaults = config["defaults"]
    runs: list[RunSpec] = []
    for exp in config["experiments"]:
        base = {**defaults, **{k: v for k, v in exp.items() if k not in ("id", "matrix", "fault")}}
        matrix = exp["matrix"]
        keys = list(matrix)
        combos = [{}]
        for key in keys:
            combos = [{**c, key: v} for c in combos for v in matrix[key]]
        exp_runs = []
        for combo in combos:
            params = {**base, **combo}
            if params.get("netem") == "none":
                params["netem"] = None
            fault = None
            if "outage_s" in params:
                fault = {"kind": "outage", "service": params.pop("target"), "start_s": params["fault_start_s"],
                         "duration_s": params.pop("outage_s"), "signal": "SIGKILL"}
            elif "broker_mode" in params:
                fault = {"kind": "broker", "mode": params.pop("broker_mode"), "start_s": params["fault_start_s"],
                         "duration_s": params.pop("broker_down_s")}
            if fault:
                params["duration_s"] = fault["start_s"] + fault["duration_s"] + params.get("tail_s", 30)
            for rep in range(1, params["repetitions"] + 1):
                exp_runs.append(RunSpec(
                    campaign=config["name"], experiment=exp["id"], profile=params["profile"],
                    rate=params["rate"], duration_s=params["duration_s"], repetition=rep,
                    seed=params.get("seed", 42), sensor_count=params.get("sensor_count", 5),
                    warmup_s=params.get("warmup_s", 5), netem=params.get("netem"), fault=fault))
        random.Random(config.get("order_seed", 1)).shuffle(exp_runs)   # counterbalance order
        runs.extend(exp_runs)
    return runs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--campaign", type=Path)
    parser.add_argument("--only", help="comma-separated experiment ids, e.g. E1,E3")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--profile", choices=sorted(PROFILES))
    parser.add_argument("--rate", type=float)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--netem", choices=sorted(NETEM))
    parser.add_argument("--outage", help="service:start_s:duration_s, e.g. alert:20:10")
    parser.add_argument("--broker", help="mode:start_s:duration_s, e.g. abrupt:20:10")
    parser.add_argument("--name", default="adhoc")
    args = parser.parse_args()

    if args.campaign:
        config = json.loads(args.campaign.read_text())
        runs = expand_campaign(config)
        if args.only:
            wanted = set(args.only.split(","))
            runs = [r for r in runs if r.experiment in wanted]
    elif args.profile and args.rate:
        fault = None
        if args.outage:
            service, start, dur = args.outage.split(":")
            fault = {"kind": "outage", "service": service, "start_s": float(start), "duration_s": float(dur),
                     "signal": "SIGKILL"}
        elif args.broker:
            mode, start, dur = args.broker.split(":")
            fault = {"kind": "broker", "mode": mode, "start_s": float(start), "duration_s": float(dur)}
        runs = [RunSpec(args.name, "adhoc", args.profile, args.rate, args.duration, rep, netem=args.netem,
                        fault=fault) for rep in range(1, args.repetitions + 1)]
    else:
        parser.error("give --campaign, or --profile and --rate")

    total_s = sum(r.estimated_s() for r in runs)
    log(f"{len(runs)} runs, estimated {total_s / 3600:.1f} h")
    if args.dry_run:
        for r in runs:
            print(f"  {r.run_id}  ({r.duration_s:.0f}s)")
        return

    global _CAMPAIGN_GIT
    ensure_results_volume()
    _CAMPAIGN_GIT = git_info()
    for arch in ("rest", "mqtt"):
        log(f"building {arch} image")
        Stack(arch, {}).compose("build", timeout=900)
    env_info = {**environment_info(), "images": image_ids(), "git": _CAMPAIGN_GIT}
    (RESULTS_ROOT / runs[0].campaign).mkdir(parents=True, exist_ok=True)
    (RESULTS_ROOT / runs[0].campaign / "environment.json").write_text(json.dumps(env_info, indent=2))
    done = failed = 0
    started = time.time()
    for i, spec in enumerate(runs, 1):
        log(f"[{i}/{len(runs)}] elapsed {(time.time() - started) / 60:.0f} min")
        meta = run_one(spec)
        if meta.get("status") == "complete":
            done += 1
        else:
            failed += 1
    log(f"campaign finished: {done} complete, {failed} not complete, {(time.time() - started) / 3600:.2f} h")


if __name__ == "__main__":
    main()
