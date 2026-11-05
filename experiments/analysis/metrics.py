"""Per-run metrics, following the definitions in docs/architecture.md and the plan (section 6).

Time base: every timestamp is converted to seconds since the run's first
dispatch (t0 = min sent_mono_ns). Container clocks share one monotonic clock;
fault events, recorded on the host, are mapped onto it with the measured
host-to-container wall-clock offset and the containers' wall-minus-monotonic
offset.

Definitions
- latency: Alert Service FIRST arrival of a msg_id minus its first dispatch
  (duplicates excluded); messages in the warm-up window are excluded for the
  steady-state experiments (E1, E2, E5)
- delivery ratio: unique msg_ids received / messages scheduled
- duplicates: deliveries beyond the first per msg_id
- throughput: unique messages received per second over the measured window
- ack latency: protocol acknowledgement (HTTP response / PUBACK / PUBCOMP)
  minus dispatch, reported separately, never as delivery
- recovery time: from the restarted service being ready until delivery runs at
  >= 95% of the pre-fault rate for 10 consecutive seconds (plan, section 6)
- backlog drain time: from readiness until the last message dispatched during
  the outage has arrived
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

STEADY_STATE = {"E1", "E2", "E5"}


@dataclass
class Run:
    folder: Path
    meta: dict
    sim: dict
    sent: pd.DataFrame
    processing: pd.DataFrame
    received: pd.DataFrame
    resources: pd.DataFrame

    @property
    def spec(self) -> dict:
        return self.meta["spec"]


def load_run(folder: Path) -> Run | None:
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        return None
    meta = json.loads(meta_path.read_text())
    if meta.get("status") != "complete":
        return None

    def csv(name: str) -> pd.DataFrame:
        path = folder / name
        return pd.read_csv(path) if path.exists() and path.stat().st_size else pd.DataFrame()

    return Run(folder, meta, json.loads((folder / "simulator_summary.json").read_text()),
               csv("sent.csv"), csv("processing.csv"), csv("received.csv"), csv("resources.csv"))


def discover(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.rglob("meta.json"))


def _pct(series: pd.Series, q: float) -> float:
    return float(np.percentile(series, q)) if len(series) else float("nan")


def _event_rel_s(run: Run, event: dict, t0_mono: int) -> float | None:
    if event.get("host_wall_ns") is None:
        return None
    container_wall = event["host_wall_ns"] + run.meta["clock_offset"]["offset_ns"]
    mono = container_wall - run.sim["clock"]["wall_minus_mono_ns"]
    return (mono - t0_mono) / 1e9


def config_of(run: Run) -> dict:
    spec = run.spec
    profile = spec["profile"]
    fault = spec.get("fault") or {}
    return {
        "run_id": run.meta["run_id"],
        "experiment": spec["experiment"],
        "profile": profile,
        "arch": "rest" if profile.startswith("rest") else "mqtt",
        "qos": int(profile[-1]) if profile.startswith("mqtt") else None,
        "retry": profile == "rest-retry",
        "rate": spec["rate"],
        "duration_s": spec["duration_s"],
        "netem": spec.get("netem") or "none",
        "fault_kind": fault.get("kind"),
        "fault_target": fault.get("service") or ("broker" if fault.get("kind") == "broker" else None),
        "fault_mode": fault.get("mode") or fault.get("signal"),
        "outage_s": fault.get("duration_s"),
        "repetition": spec["repetition"],
    }


def run_metrics(run: Run) -> dict:
    cfg = config_of(run)
    spec = run.spec
    sent, rec = run.sent, run.received
    t0 = int(sent["sent_mono_ns"].min())
    scheduled = len(sent)
    warmup_index = int(spec["warmup_s"] * spec["rate"]) if cfg["experiment"] in STEADY_STATE else 0

    first = (rec.sort_values("alert_received_mono_ns").drop_duplicates("msg_id", keep="first")
             if len(rec) else rec)
    index_of = sent.set_index("msg_id")["index"]
    if len(first):
        first = first.assign(index=first["msg_id"].map(index_of))
        measured = first[first["index"] >= warmup_index]
    else:
        measured = first
    lat = measured["latency_ms"] if len(measured) else pd.Series(dtype=float)

    out = dict(cfg)
    out.update({
        "scheduled": scheduled,
        "unique_received": len(first),
        "deliveries": len(rec),
        "duplicates": len(rec) - len(first),
        "lost": scheduled - len(first),
        "delivery_ratio": len(first) / scheduled if scheduled else float("nan"),
        "sender_ok": int((sent["status"] == "ok").sum()),
        "sender_failed": int((sent["status"] != "ok").sum()),
        "alerts": int(first["is_alert"].sum()) if len(first) else 0,
        "expected_alerts": run.sim["expected_alerts"],
        "lat_p50_ms": _pct(lat, 50), "lat_p95_ms": _pct(lat, 95), "lat_p99_ms": _pct(lat, 99),
        "lat_mean_ms": float(lat.mean()) if len(lat) else float("nan"),
        "lat_std_ms": float(lat.std()) if len(lat) > 1 else float("nan"),
        "lat_max_ms": float(lat.max()) if len(lat) else float("nan"),
        "achieved_dispatch_rate": run.sim["producer"]["achieved_dispatch_rate"],
        "dispatch_lag_p99_ms": run.sim["producer"]["dispatch_lag_ms"]["p99"],
        "missed_deadlines": run.sim["producer"]["missed_deadlines"],
    })

    if len(measured) > 1:
        t = (measured["alert_received_mono_ns"] - t0) / 1e9
        span = t.max() - t.min()
        out["throughput_msg_s"] = (len(measured) - 1) / span if span > 0 else float("nan")
        out["processing_ms_p50"] = _pct((measured["processing_completed_mono_ns"]
                                         - measured["processing_received_mono_ns"]) / 1e6, 50)
        out["downstream_ms_p50"] = _pct((measured["alert_received_mono_ns"]
                                         - measured["processing_completed_mono_ns"]) / 1e6, 50)
    ack = (sent["done_mono_ns"] - sent["sent_mono_ns"]) / 1e6
    out["ack_p50_ms"], out["ack_p95_ms"] = _pct(ack, 50), _pct(ack, 95)

    # per-sensor sequence gaps and out-of-order arrivals
    if len(first):
        gaps = 0
        out_of_order = 0
        for _, group in rec.sort_values("alert_received_mono_ns").groupby("sensor_id"):
            seqs = group.drop_duplicates("msg_id")["seq"].to_numpy()
            expected = int(sent[sent["sensor_id"] == group["sensor_id"].iat[0]]["seq"].max()) + 1
            gaps += expected - len(np.unique(seqs))
            out_of_order += int((seqs[1:] < np.maximum.accumulate(seqs)[:-1]).sum())
        out["seq_gaps"], out["out_of_order"] = gaps, out_of_order

    # HTTP attempts (retry amplification) for REST
    if cfg["arch"] == "rest" and len(run.processing):
        out["sim_attempts_total"] = int(sent["attempts"].sum())
        out["proc_attempts_total"] = int(run.processing["attempts"].sum())
        out["proc_requests"] = len(run.processing)

    out.update(_resource_metrics(run))
    if cfg["fault_kind"]:
        out.update(_fault_metrics(run, first, t0))
    return out


def _resource_metrics(run: Run) -> dict:
    res = run.resources
    if not len(res):
        return {}
    events = {e["event"]: e["host_wall_ns"] for e in run.meta["events"] if e.get("host_wall_ns")}
    start = events.get("simulator_started", 0) + int(run.meta.get("start_delay_s", 3) * 1e9) + int(5e9)
    end = events.get("simulator_exited", np.iinfo(np.int64).max)
    window = res[(res["wall_ns"] >= start) & (res["wall_ns"] <= end)].copy()
    window["cpu_pct"] = pd.to_numeric(window["cpu_pct"], errors="coerce")
    window["mem_mib"] = pd.to_numeric(window["mem_mib"], errors="coerce")
    out: dict = {"resource_samples": len(window)}
    cpu_app = mem_app = 0.0
    for service, group in window.groupby("service"):
        key = service.replace("-", "_")
        cpu, mem = float(group["cpu_pct"].mean()), float(group["mem_mib"].mean())
        out[f"cpu_{key}_pct"], out[f"mem_{key}_mib"] = cpu, mem
        if service != "sensor-simulator":
            cpu_app += cpu
            mem_app += mem
    # System = the architecture under test (Processing + Alert [+ broker]), excluding the load generator.
    # Summing per-service means, not per-instant sums: docker stats sometimes delivers two samples
    # for one container within a second, which would double-count a per-second sum.
    out["cpu_system_pct"], out["mem_system_mib"] = cpu_app, mem_app
    return out


def _fault_metrics(run: Run, first: pd.DataFrame, t0: int) -> dict:
    events = {e["event"]: e for e in run.meta["events"]}
    down = _event_rel_s(run, events["service_down"], t0)
    ready = _event_rel_s(run, events["ready"], t0) if events.get("ready", {}).get("host_wall_ns") else None
    out = {"fault_down_s": down, "fault_ready_s": ready,
           "fault_unavailable_s": (ready - down) if ready is not None else None}
    sent_rel = (run.sent["sent_mono_ns"] - t0) / 1e9
    during = run.sent[(sent_rel >= down) & (sent_rel < (ready if ready is not None else sent_rel.max()))]
    got = set(first["msg_id"]) if len(first) else set()
    out["sent_during_outage"] = len(during)
    out["lost_during_outage"] = int((~during["msg_id"].isin(got)).sum())
    if not len(first):
        return out
    recv_rel = (first["alert_received_mono_ns"] - t0) / 1e9
    per_second = recv_rel.astype(int).value_counts().sort_index()
    pre = per_second[(per_second.index >= max(1, int(down) - 15)) & (per_second.index < int(down))]
    baseline = float(pre.mean()) if len(pre) else float("nan")
    out["pre_fault_rate"] = baseline
    if ready is not None and baseline == baseline:
        seconds = np.arange(int(np.ceil(ready)), int(recv_rel.max()) + 1)
        counts = per_second.reindex(seconds, fill_value=0).to_numpy()
        ok = counts >= 0.95 * baseline
        recovery = None
        for i in range(len(ok) - 9):
            if ok[i:i + 10].all():
                recovery = float(seconds[i] - ready)
                break
        out["recovery_s"] = max(recovery, 0.0) if recovery is not None else None
        late = first[first["msg_id"].isin(during["msg_id"])]
        if len(late):
            last_arrival = ((late["alert_received_mono_ns"].max() - t0) / 1e9)
            out["backlog_drain_s"] = max(0.0, last_arrival - ready)
            out["backlog_max_latency_ms"] = float(late["latency_ms"].max())
    return out


def timeline(run: Run, bin_s: float = 1.0) -> pd.DataFrame:
    """Per-second delivered count and p95 latency, for timeline figures."""
    rec = run.received
    t0 = int(run.sent["sent_mono_ns"].min())
    first = rec.sort_values("alert_received_mono_ns").drop_duplicates("msg_id")
    t = ((first["alert_received_mono_ns"] - t0) / 1e9 // bin_s) * bin_s
    grouped = first.assign(t=t).groupby("t")
    return pd.DataFrame({"delivered_per_s": grouped.size() / bin_s,
                         "lat_p95_ms": grouped["latency_ms"].quantile(0.95)}).reset_index()


def fault_events_rel(run: Run) -> dict:
    t0 = int(run.sent["sent_mono_ns"].min())
    return {e["event"]: _event_rel_s(run, e, t0) for e in run.meta["events"]
            if e["event"] in ("service_down", "restart", "ready")}
