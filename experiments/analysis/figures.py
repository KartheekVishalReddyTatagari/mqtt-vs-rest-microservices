"""Figures for the report, one or more per research question.

Conventions (kept identical across every figure so a colour always means the same thing):
- colour = configuration: REST blue, MQTT QoS 1 orange, MQTT QoS 0 aqua,
  REST + retry yellow, MQTT QoS 2 magenta (fixed palette order, never cycled)
- a point = mean over repetitions; whiskers = min..max over repetitions
- one y-axis per panel; different measures go in separate panels
- thin marks, recessive grid, text in neutral ink, never in the series colour
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

COLORS = {"rest": "#2a78d6", "mqtt-q1": "#eb6834", "mqtt-q0": "#1baf7a", "rest-retry": "#eda100",
          "mqtt-q2": "#e87ba4"}
LABELS = {"rest": "REST", "mqtt-q1": "MQTT QoS 1", "mqtt-q0": "MQTT QoS 0", "rest-retry": "REST + retry",
          "mqtt-q2": "MQTT QoS 2"}
ORDER = ["rest", "rest-retry", "mqtt-q0", "mqtt-q1", "mqtt-q2"]
NETEM_LABELS = {"none": "no impairment", "delay50": "50 ms delay", "delay100": "100 ms delay",
                "loss1": "1% loss", "loss5": "5% loss", "delay50-loss1": "50 ms + 1% loss"}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.size": 9.5, "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK,
    "axes.edgecolor": AXIS, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6,
    "legend.frameon": False, "legend.fontsize": 9, "lines.linewidth": 1.8, "lines.markersize": 6,
})


def _save(fig, out: Path, name: str) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return path


def _dot_whisker(ax, x, group: pd.DataFrame, metric: str, profile: str, offset: float = 0.0, line=True):
    stats = group.groupby("x")[metric].agg(["mean", "min", "max"])
    if x is not None:
        stats = stats.reindex(x)
    stats = stats.dropna()
    if not len(stats):
        return
    xs = np.array([x.index(v) for v in stats.index], float) + offset if not line else stats.index.to_numpy(float)
    ax.errorbar(xs, stats["mean"], yerr=[stats["mean"] - stats["min"], stats["max"] - stats["mean"]],
                fmt="-o" if line else "o", color=COLORS[profile], ecolor=COLORS[profile], elinewidth=1,
                capsize=2.5, markeredgecolor=SURFACE, markeredgewidth=1.2, label=LABELS[profile], ms=7)


def _legend(fig, profiles):
    handles = [plt.Line2D([], [], color=COLORS[p], marker="o", ls="-", ms=6, label=LABELS[p]) for p in profiles]
    fig.legend(handles=handles, loc="upper center", ncol=len(handles), bbox_to_anchor=(0.5, 1.02))


def latency_vs_rate(runs: pd.DataFrame, out: Path) -> Path | None:
    e1 = runs[(runs["experiment"] == "E1")].assign(x=lambda d: d["rate"])
    if not len(e1):
        return None
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2), sharex=True)
    for ax, (metric, title) in zip(axes, [("lat_p50_ms", "Median latency (p50)"), ("lat_p95_ms", "p95 latency"),
                                          ("lat_p99_ms", "p99 latency")]):
        for profile in ("rest", "mqtt-q1"):
            _dot_whisker(ax, None, e1[e1["profile"] == profile], metric, profile)
        ax.set_xscale("log")
        ax.set_xticks([10, 100, 500, 1000], ["10", "100", "500", "1000"])
        ax.set_title(title, loc="left")
        ax.set_xlabel("offered load (msg/s)")
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel("end-to-end latency (ms)")
    _legend(fig, ["rest", "mqtt-q1"])
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, out, "fig1_latency_vs_rate")


def latency_cdf(message_latencies: dict, out: Path) -> Path | None:
    """message_latencies: {rate: {profile: np.ndarray of ms}} pooled over repetitions."""
    if not message_latencies:
        return None
    rates = sorted(message_latencies)
    fig, axes = plt.subplots(1, len(rates), figsize=(3.4 * len(rates), 3.1), sharey=True)
    axes = np.atleast_1d(axes)
    for ax, rate in zip(axes, rates):
        for profile, values in message_latencies[rate].items():
            v = np.sort(values)
            ax.plot(v, np.arange(1, len(v) + 1) / len(v), color=COLORS[profile], label=LABELS[profile])
        ax.set_xscale("log")
        ax.set_title(f"{rate:g} msg/s", loc="left")
        ax.set_xlabel("end-to-end latency (ms, log scale)")
        ax.grid(True, axis="x", color=GRID, linewidth=0.6)
    axes[0].set_ylabel("share of messages at or below")
    _legend(fig, [p for p in ("rest", "mqtt-q1") if any(p in message_latencies[r] for r in rates)])
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return _save(fig, out, "fig2_latency_cdf")


def network_conditions(runs: pd.DataFrame, out: Path) -> Path | None:
    e2 = runs[(runs["fault_kind"].isna()) & (runs["rate"] == 100) & (runs["profile"].isin(["rest", "mqtt-q1"]))]
    e2 = e2[(e2["experiment"] == "E2") | ((e2["experiment"] == "E1") & (e2["netem"] == "none"))]
    if not len(e2[e2["experiment"] == "E2"]):
        return None
    conditions = [c for c in NETEM_LABELS if c in set(e2["netem"])]
    e2 = e2.assign(x=e2["netem"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4), sharex=True)
    for ax, (metric, title) in zip(axes, [("lat_p50_ms", "Median latency (p50)"), ("lat_p99_ms", "p99 latency")]):
        for i, profile in enumerate(("rest", "mqtt-q1")):
            _dot_whisker(ax, conditions, e2[e2["profile"] == profile], metric, profile, offset=-0.12 + 0.24 * i,
                         line=False)
        ax.set_xticks(range(len(conditions)), [NETEM_LABELS[c] for c in conditions], rotation=20, ha="right")
        ax.set_title(title, loc="left")
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel("end-to-end latency (ms)")
    _legend(fig, ["rest", "mqtt-q1"])
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    return _save(fig, out, "fig3_network_conditions")


def outage_delivery(runs: pd.DataFrame, out: Path) -> Path | None:
    e3 = runs[runs["experiment"] == "E3"]
    if not len(e3):
        return None
    targets = [t for t in ("alert", "processing") if t in set(e3["fault_target"])]
    outages = sorted(e3["outage_s"].dropna().unique())
    profiles = [p for p in ORDER if p in set(e3["profile"])]
    fig, axes = plt.subplots(1, len(targets), figsize=(5 * len(targets), 3.4), sharey=True)
    axes = np.atleast_1d(axes)
    width = 0.8 / len(profiles)
    for ax, target in zip(axes, targets):
        sub = e3[e3["fault_target"] == target]
        for i, profile in enumerate(profiles):
            stats = (sub[sub["profile"] == profile].groupby("outage_s")["delivery_ratio"]
                     .agg(["mean", "min", "max"]).reindex(outages) * 100)
            xs = np.arange(len(outages)) - 0.4 + width * (i + 0.5)
            ax.bar(xs, stats["mean"], width=width - 0.03, color=COLORS[profile], label=LABELS[profile])
            ax.errorbar(xs, stats["mean"], yerr=[stats["mean"] - stats["min"], stats["max"] - stats["mean"]],
                        fmt="none", ecolor=INK2, elinewidth=0.9, capsize=2)
        ax.set_xticks(range(len(outages)), [f"{o:g} s outage" for o in outages])
        ax.set_title(f"{target.capitalize()} Service killed", loc="left")
        ax.set_ylim(0, 105)
    axes[0].set_ylabel("messages delivered (%)")
    _legend(fig, profiles)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return _save(fig, out, "fig4_outage_delivery")


def outage_timelines(timelines: dict, events: dict, out: Path, name: str, title: str) -> Path | None:
    """timelines: {profile: DataFrame(t, delivered_per_s)}; events: {profile: {service_down, ready}}."""
    if not timelines:
        return None
    profiles = [p for p in ORDER if p in timelines]
    fig, axes = plt.subplots(len(profiles), 1, figsize=(8, 1.45 * len(profiles) + 0.6), sharex=True, sharey=True)
    axes = np.atleast_1d(axes)
    for ax, profile in zip(axes, profiles):
        tl = timelines[profile]
        ev = events.get(profile, {})
        if ev.get("service_down") is not None and ev.get("ready") is not None:
            ax.axvspan(ev["service_down"], ev["ready"], color=GRID, alpha=0.8, lw=0)
        ax.bar(tl["t"], tl["delivered_per_s"], width=0.9, color=COLORS[profile], align="edge")
        ax.text(0.005, 0.92, LABELS[profile], transform=ax.transAxes, va="top", fontsize=9, color=INK,
                fontweight="bold")
    axes[-1].set_xlabel("seconds since the first message (grey band = service down until ready again)")
    fig.supylabel("delivered per second", fontsize=9.5, color=INK2)
    fig.suptitle(title, x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return _save(fig, out, name)


def resources(runs: pd.DataFrame, out: Path, metric_prefix: str = "cpu", unit: str = "CPU (% of one core)",
              name: str = "fig6_cpu") -> Path | None:
    e1 = runs[runs["experiment"] == "E1"].assign(x=lambda d: d["rate"])
    if not len(e1):
        return None
    panels = [("processing", "Processing Service"), ("alert", "Alert Service"), ("broker", "Mosquitto broker"),
              ("system", "System total (excl. simulator)")]
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.1), sharex=True)
    for ax, (service, title) in zip(axes, panels):
        metric = f"{metric_prefix}_{service}_pct" if metric_prefix == "cpu" else f"{metric_prefix}_{service}_mib"
        for profile in ("rest", "mqtt-q1"):
            group = e1[e1["profile"] == profile]
            if metric in group and group[metric].notna().any():
                _dot_whisker(ax, None, group, metric, profile)
        ax.set_xscale("log")
        ax.set_xticks([10, 100, 500, 1000], ["10", "100", "500", "1000"])
        ax.set_title(title, loc="left")
        ax.set_xlabel("offered load (msg/s)")
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel(unit)
    _legend(fig, ["rest", "mqtt-q1"])
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    return _save(fig, out, name)


def qos_runs(runs: pd.DataFrame) -> pd.DataFrame:
    """Steady MQTT runs for the QoS study: E5's own runs, plus runs from other experiments
    only for a (profile, rate, netem) that E5 did not measure itself (the reduced campaign
    reused QoS 1 from E1 and E2)."""
    steady = runs[runs["fault_kind"].isna() & runs["profile"].str.startswith("mqtt")]
    config = steady["profile"] + "|" + steady["rate"].astype(str) + "|" + steady["netem"]
    cond = steady["rate"].astype(str) + "|" + steady["netem"]
    in_e5 = steady["experiment"] == "E5"
    reuse = ~in_e5 & ~config.isin(set(config[in_e5])) & cond.isin(set(cond[in_e5]))
    return steady[in_e5 | reuse]


def qos_tradeoff(runs: pd.DataFrame, out: Path) -> Path | None:
    steady = qos_runs(runs)
    conds = [(r, n) for r in (100, 1000) for n in ("none", "loss1")
             if len(steady[(steady["rate"] == r) & (steady["netem"] == n)])]
    if not conds:
        return None
    qos_profiles = ["mqtt-q0", "mqtt-q1", "mqtt-q2"]
    fig, axes = plt.subplots(2, len(conds), figsize=(3.1 * len(conds), 5.2), sharex=True)
    axes = np.atleast_2d(axes)
    for col, (rate, netem) in enumerate(conds):
        sub = steady[(steady["rate"] == rate) & (steady["netem"] == netem)].assign(x=lambda d: d["profile"])
        for row, (metric, label) in enumerate([("lat_p99_ms", "p99 latency (ms)"),
                                               ("cpu_system_pct", "system CPU (% of one core)")]):
            ax = axes[row, col]
            for i, profile in enumerate(qos_profiles):
                _dot_whisker(ax, qos_profiles, sub[sub["profile"] == profile], metric, profile, offset=0, line=False)
            ax.set_xticks(range(3), ["QoS 0", "QoS 1", "QoS 2"])
            ax.set_ylim(bottom=0)
            if col == 0:
                ax.set_ylabel(label)
            if row == 0:
                ax.set_title(f"{rate} msg/s, {NETEM_LABELS[netem]}", loc="left")
    _legend(fig, qos_profiles)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _save(fig, out, "fig8_qos_tradeoff")
