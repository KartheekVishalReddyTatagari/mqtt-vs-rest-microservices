"""Deterministic workload: the trace both versions replay.

A WorkloadSpec (seed, sensors, rate, duration, ...) fully determines the
trace: which sensor sends at each step, its per-sensor sequence number and
its value. REST and MQTT runs with the same spec therefore replay exactly the
same logical workload. The trace is also written to trace.csv in each run's
results folder, and trace_id (a hash of the spec) identifies it in metadata.

Sensors take turns (round-robin), so with N sensors message i comes from
sensor i % N with per-sensor seq i // N.

Normal values are drawn around base_mean and capped just below the threshold.
With probability spike_probability a value is a spike above the threshold, so
the number of expected alerts equals the number of spikes.
"""

import csv
import hashlib
import json
import random
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from common.config import env_float, env_int
from common.messages import SCHEMA_VERSION, Reading

MSG_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/mqtt-vs-rest-microservices")


@dataclass(frozen=True)
class WorkloadSpec:
    seed: int
    sensor_count: int
    rate: float              # messages per second, all sensors together
    duration_s: float
    threshold: float
    spike_probability: float
    base_mean: float = 22.0
    base_std: float = 1.5
    unit: str = "C"

    def __post_init__(self) -> None:
        if self.sensor_count < 1:
            raise ValueError("sensor_count must be >= 1")
        if self.rate <= 0 or self.duration_s <= 0:
            raise ValueError("rate and duration_s must be > 0")
        if not 0.0 <= self.spike_probability <= 1.0:
            raise ValueError("spike_probability must be between 0 and 1")

    @property
    def total(self) -> int:
        return int(self.rate * self.duration_s)

    @property
    def trace_id(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]

    @classmethod
    def from_env(cls) -> "WorkloadSpec":
        return cls(
            seed=env_int("SEED", 42),
            sensor_count=env_int("SENSOR_COUNT", 5),
            rate=env_float("RATE", 10.0),
            duration_s=env_float("DURATION_S", 10.0),
            threshold=env_float("THRESHOLD", 30.0),
            spike_probability=env_float("SPIKE_PROBABILITY", 0.02),
        )


@dataclass(frozen=True, slots=True)
class TraceItem:
    index: int        # position in the global send order
    sensor_id: str
    seq: int          # per-sensor sequence number
    value: float
    is_spike: bool


def sensor_name(i: int) -> str:
    return f"sensor-{i + 1:03d}"


def generate_trace(spec: WorkloadSpec) -> list[TraceItem]:
    rng = random.Random(spec.seed)
    names = [sensor_name(i) for i in range(spec.sensor_count)]
    items = []
    for index in range(spec.total):
        if rng.random() < spec.spike_probability:
            value, spike = spec.threshold + rng.uniform(1.0, 10.0), True
        else:
            value, spike = min(rng.gauss(spec.base_mean, spec.base_std), spec.threshold - 0.01), False
        items.append(TraceItem(
            index=index,
            sensor_id=names[index % spec.sensor_count],
            seq=index // spec.sensor_count,
            value=round(value, 2),
            is_spike=spike,
        ))
    return items


def write_trace(path: Path, items: list[TraceItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "sensor_id", "seq", "value", "is_spike"])
        for item in items:
            writer.writerow([item.index, item.sensor_id, item.seq, item.value, int(item.is_spike)])


def make_msg_id(run_id: str, sensor_id: str, seq: int) -> str:
    """Stable id for one logical message: the same on every retry or redelivery."""
    return str(uuid.uuid5(MSG_ID_NAMESPACE, f"{run_id}/{sensor_id}/{seq}"))


def build_reading(run_id: str, item: TraceItem, unit: str, event_ts_ns: int, sent_mono_ns: int) -> Reading:
    return Reading(
        schema_version=SCHEMA_VERSION,
        run_id=run_id,
        msg_id=make_msg_id(run_id, item.sensor_id, item.seq),
        sensor_id=item.sensor_id,
        seq=item.seq,
        event_ts_ns=event_ts_ns,
        sent_mono_ns=sent_mono_ns,
        value=item.value,
        unit=unit,
    )
