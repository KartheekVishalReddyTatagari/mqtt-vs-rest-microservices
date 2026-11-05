"""Aggregate run-level metrics per configuration and compare architectures.

Statistics are computed on RUN-LEVEL values (one p95 per run, not every
message pooled), because messages within a run are not independent
repetitions (plan, section 6.1).

With n = 3 runs per group, a two-sided Mann-Whitney U test cannot reach
p < 0.05 (its smallest possible p is 0.1). Welch's t-test is reported too,
but the emphasis is on effect sizes and confidence intervals.
"""

import numpy as np
import pandas as pd
from scipy import stats

STEADY_KEYS = ["profile", "arch", "qos", "rate", "netem"]
FAULT_KEYS = ["experiment", "profile", "arch", "qos", "rate", "fault_target", "fault_mode", "outage_s"]

SUMMARY_METRICS = [
    "lat_p50_ms", "lat_p95_ms", "lat_p99_ms", "lat_mean_ms", "lat_max_ms", "throughput_msg_s",
    "delivery_ratio", "lost", "duplicates", "out_of_order", "achieved_dispatch_rate", "missed_deadlines",
    "dispatch_lag_p99_ms", "ack_p50_ms", "ack_p95_ms", "processing_ms_p50", "downstream_ms_p50",
    "cpu_system_pct", "mem_system_mib", "cpu_processing_pct", "cpu_alert_pct", "cpu_broker_pct",
    "cpu_sensor_simulator_pct", "mem_processing_mib", "mem_alert_mib", "mem_broker_mib",
    "lost_during_outage", "sent_during_outage", "recovery_s", "backlog_drain_s", "backlog_max_latency_ms",
    "fault_unavailable_s", "sim_attempts_total", "proc_attempts_total",
]


def describe(values: pd.Series) -> dict:
    v = values.dropna().astype(float)
    n = len(v)
    if n == 0:
        return {"n": 0}
    mean = v.mean()
    sd = v.std(ddof=1) if n > 1 else float("nan")
    half = stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n) if n > 1 else float("nan")
    return {"n": n, "mean": mean, "sd": sd, "median": v.median(), "q1": v.quantile(0.25), "q3": v.quantile(0.75),
            "ci95_low": mean - half, "ci95_high": mean + half, "min": v.min(), "max": v.max()}


def summarise(runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    steady = runs[runs["fault_kind"].isna()]
    faults = runs[runs["fault_kind"].notna()]
    for keys, frame in ((STEADY_KEYS, steady), (FAULT_KEYS, faults)):
        if not len(frame):
            continue
        for key, group in frame.groupby(keys, dropna=False):
            base = dict(zip(keys, key))
            for metric in SUMMARY_METRICS:
                if metric in group and group[metric].notna().any():
                    rows.append({**base, "metric": metric, **describe(group[metric])})
    return pd.DataFrame(rows)


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """P(a > b) - P(a < b): -1..1, robust effect size for small samples."""
    greater = sum((x > y) for x in a for y in b)
    smaller = sum((x < y) for x in a for y in b)
    return (greater - smaller) / (len(a) * len(b))


def compare(runs: pd.DataFrame, a_profile: str = "rest", b_profile: str = "mqtt-q1",
            metrics: tuple = ("lat_p50_ms", "lat_p95_ms", "lat_p99_ms", "throughput_msg_s",
                              "cpu_system_pct", "mem_system_mib", "delivery_ratio")) -> pd.DataFrame:
    """REST vs MQTT at every steady-state (rate, netem) condition both ran."""
    steady = runs[runs["fault_kind"].isna()]
    rows = []
    for (rate, netem), group in steady.groupby(["rate", "netem"]):
        a = group[group["profile"] == a_profile]
        b = group[group["profile"] == b_profile]
        if len(a) < 2 or len(b) < 2:
            continue
        for metric in metrics:
            x, y = a[metric].dropna().to_numpy(float), b[metric].dropna().to_numpy(float)
            if len(x) < 2 or len(y) < 2:
                continue
            pooled = np.sqrt(((len(x) - 1) * x.var(ddof=1) + (len(y) - 1) * y.var(ddof=1)) / (len(x) + len(y) - 2))
            rows.append({
                "rate": rate, "netem": netem, "metric": metric, "a": a_profile, "b": b_profile,
                "n_a": len(x), "n_b": len(y), "mean_a": x.mean(), "mean_b": y.mean(),
                "diff_b_minus_a": y.mean() - x.mean(),
                "ratio_b_over_a": y.mean() / x.mean() if x.mean() else float("nan"),
                "welch_p": stats.ttest_ind(y, x, equal_var=False).pvalue if (x.std() + y.std()) > 0 else float("nan"),
                "mannwhitney_p": stats.mannwhitneyu(y, x, alternative="two-sided").pvalue,
                "cohens_d": (y.mean() - x.mean()) / pooled if pooled > 0 else float("nan"),
                "cliffs_delta": cliffs_delta(y, x),
            })
    return pd.DataFrame(rows)


def compare_faults(runs: pd.DataFrame) -> pd.DataFrame:
    """Delivery and recovery per profile for each outage condition (E3)."""
    faults = runs[runs["experiment"] == "E3"]
    if not len(faults):
        return pd.DataFrame()
    cols = ["delivery_ratio", "lost", "lost_during_outage", "duplicates", "recovery_s", "backlog_drain_s",
            "backlog_max_latency_ms", "lat_max_ms"]
    present = [c for c in cols if c in faults]
    table = faults.groupby(["fault_target", "outage_s", "profile"])[present].agg(["mean", "min", "max"])
    table.columns = [f"{m}_{s}" for m, s in table.columns]
    return table.reset_index()
