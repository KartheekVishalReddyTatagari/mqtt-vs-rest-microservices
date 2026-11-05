"""Turn a campaign's raw run folders into tables, figures and a summary.

    python experiments/analysis/report.py results/raw/reduced

Writes
  results/processed/<campaign>/run_metrics.csv      one row per run, every metric
  results/processed/<campaign>/config_summary.csv   per configuration: n, mean, sd, median, IQR, 95% CI
  results/processed/<campaign>/comparisons.csv      REST vs MQTT QoS 1 per condition, with effect sizes
  results/processed/<campaign>/outages.csv          E3 delivery and recovery per condition
  results/figures/<campaign>/fig*.png               one or more figures per research question
  results/processed/<campaign>/summary.md           the key tables in Markdown
Raw data is never modified.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aggregate  # noqa: E402
import figures  # noqa: E402
from metrics import discover, fault_events_rel, load_run, run_metrics, timeline  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


def fmt(x, digits=2) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    return f"{x:,.{digits}f}"


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign_dir", type=Path)
    args = parser.parse_args()
    campaign = args.campaign_dir.name
    processed = REPO / "results" / "processed" / campaign
    fig_dir = REPO / "results" / "figures" / campaign
    processed.mkdir(parents=True, exist_ok=True)

    folders = discover(args.campaign_dir)
    rows, skipped = [], []
    cdf_inputs: dict = {}
    timelines: dict = {}
    broker_timelines: dict = {}
    for folder in folders:
        run = load_run(folder)
        if run is None:
            skipped.append(folder.name)
            continue
        m = run_metrics(run)
        rows.append(m)
        # message-level inputs for the CDF (E1, 100 and 1000 msg/s) and outage timelines (rep 1)
        if m["experiment"] == "E1" and m["rate"] in (100, 1000):
            warm = int(run.spec["warmup_s"] * run.spec["rate"])
            idx = run.sent.set_index("msg_id")["index"]
            first = run.received.drop_duplicates("msg_id")
            lat = first[first["msg_id"].map(idx) >= warm]["latency_ms"].to_numpy()
            cdf_inputs.setdefault(m["rate"], {}).setdefault(m["profile"], []).append(lat)
        if m["experiment"] == "E3" and m["repetition"] == 1:
            key = (m["fault_target"], m["outage_s"])
            timelines.setdefault(key, {})[m["profile"]] = (timeline(run), fault_events_rel(run))
        if m["experiment"] == "E6" and m["repetition"] == 1:
            broker_timelines[m["fault_mode"]] = (timeline(run), fault_events_rel(run))
    runs = pd.DataFrame(rows)
    if runs.empty:
        sys.exit("no complete runs found")
    runs.to_csv(processed / "run_metrics.csv", index=False)
    summary = aggregate.summarise(runs)
    summary.to_csv(processed / "config_summary.csv", index=False)
    comparisons = aggregate.compare(runs)
    comparisons.to_csv(processed / "comparisons.csv", index=False)
    outages = aggregate.compare_faults(runs)
    outages.to_csv(processed / "outages.csv", index=False)

    made = [
        figures.latency_vs_rate(runs, fig_dir),
        figures.latency_cdf({r: {p: np.concatenate(v) for p, v in d.items()} for r, d in cdf_inputs.items()}, fig_dir),
        figures.network_conditions(runs, fig_dir),
        figures.outage_delivery(runs, fig_dir),
        figures.resources(runs, fig_dir, "cpu", "CPU (% of one core)", "fig6_cpu"),
        figures.resources(runs, fig_dir, "mem", "memory (MiB)", "fig7_memory"),
        figures.qos_tradeoff(runs, fig_dir),
    ]
    for (target, outage), per_profile in sorted(timelines.items()):
        made.append(figures.outage_timelines(
            {p: tl for p, (tl, _) in per_profile.items()}, {p: ev for p, (_, ev) in per_profile.items()},
            fig_dir, f"fig5_timeline_{target}_{int(outage)}s",
            f"{target.capitalize()} Service killed for {outage:g} s at 200 msg/s (repetition 1)"))
    if broker_timelines:
        made.append(_broker_figure(broker_timelines, fig_dir))
    made = [p for p in made if p]

    write_summary(runs, comparisons, outages, processed / "summary.md", skipped, made)
    print(f"{len(runs)} runs analysed, {len(skipped)} skipped; {len(made)} figures in {fig_dir}")


def _broker_figure(broker_timelines: dict, fig_dir: Path) -> Path | None:
    import matplotlib.pyplot as plt
    modes = [m for m in ("graceful", "abrupt") if m in broker_timelines]
    fig, axes = plt.subplots(len(modes), 1, figsize=(8, 1.6 * len(modes) + 0.6), sharex=True, sharey=True)
    axes = np.atleast_1d(axes)
    for ax, mode in zip(axes, modes):
        tl, ev = broker_timelines[mode]
        if ev.get("service_down") is not None and ev.get("ready") is not None:
            ax.axvspan(ev["service_down"], ev["ready"], color=figures.GRID, alpha=0.8, lw=0)
        ax.bar(tl["t"], tl["delivered_per_s"], width=0.9, color=figures.COLORS["mqtt-q1"], align="edge")
        label = "graceful stop (SIGTERM)" if mode == "graceful" else "abrupt kill (SIGKILL)"
        ax.text(0.005, 0.92, f"Broker {label}", transform=ax.transAxes, va="top", fontsize=9,
                fontweight="bold", color=figures.INK)
    axes[-1].set_xlabel("seconds since the first message (grey band = broker down until ready again)")
    fig.supylabel("delivered per second", fontsize=9.5, color=figures.INK2)
    fig.suptitle("MQTT QoS 1, broker down for 10 s at 200 msg/s (repetition 1)", x=0.01, ha="left",
                 fontsize=10, fontweight="bold")
    fig.tight_layout()
    return figures._save(fig, fig_dir, "fig9_broker_outage")


def write_summary(runs, comparisons, outages, path: Path, skipped, made) -> None:
    lines = [f"# Results summary ({len(runs)} runs)", ""]
    if skipped:
        lines += [f"Runs not complete and excluded: {len(skipped)} ({', '.join(skipped[:10])})", ""]

    steady = runs[runs["fault_kind"].isna()]
    if len(steady):
        g = steady.groupby(["profile", "rate", "netem"])
        t = g.agg(n=("run_id", "count"), p50=("lat_p50_ms", "mean"), p95=("lat_p95_ms", "mean"),
                  p99=("lat_p99_ms", "mean"), delivered=("delivery_ratio", "mean"),
                  rate_ok=("achieved_dispatch_rate", "mean"), missed=("missed_deadlines", "mean"),
                  cpu=("cpu_system_pct", "mean"), mem=("mem_system_mib", "mean")).reset_index()
        t = t.sort_values(["netem", "rate", "profile"])
        for c in ("p50", "p95", "p99", "rate_ok", "missed", "cpu", "mem"):
            t[c] = t[c].map(lambda v: fmt(v, 1 if c in ("rate_ok", "missed", "cpu", "mem") else 2))
        t["delivered"] = t["delivered"].map(lambda v: f"{v * 100:.2f}%")
        lines += ["## Steady state (E1, E2, E5): means over repetitions", "",
                  "Latency in ms; CPU in % of one core and memory in MiB, summed over Processing, Alert "
                  "and (MQTT) broker.", "", md_table(t), ""]

    if len(comparisons):
        c = comparisons[comparisons["metric"].isin(["lat_p50_ms", "lat_p99_ms", "cpu_system_pct", "mem_system_mib"])]
        c = c[["rate", "netem", "metric", "mean_a", "mean_b", "ratio_b_over_a", "welch_p", "mannwhitney_p",
               "cliffs_delta"]].copy()
        for col in ("mean_a", "mean_b", "ratio_b_over_a"):
            c[col] = c[col].map(lambda v: fmt(v, 2))
        for col in ("welch_p", "mannwhitney_p", "cliffs_delta"):
            c[col] = c[col].map(lambda v: fmt(v, 3))
        lines += ["## REST (a) vs MQTT QoS 1 (b), run-level statistics", "",
                  "Cliff's delta: +1 = every MQTT run higher than every REST run, -1 = every one lower. "
                  "With n = 3 per group the Mann-Whitney test cannot go below p = 0.1.", "", md_table(c), ""]

    if len(outages):
        names = {"delivery_ratio_mean": "delivered", "lost_mean": "lost", "duplicates_mean": "duplicates",
                 "missed_deadlines_mean": "sent_late", "dispatch_lag_p99_ms_mean": "lag_p99_ms",
                 "recovery_s_mean": "recovery_s", "backlog_drain_s_mean": "drain_s",
                 "backlog_max_age_ms_mean": "max_age_ms"}
        o = outages[["fault_target", "outage_s", "profile"] + [c for c in names if c in outages]].rename(columns=names)
        o["delivered"] = o["delivered"].map(lambda v: f"{v * 100:.1f}%")
        for col in o.columns[4:]:
            o[col] = o[col].map(lambda v: fmt(v, 1))
        lines += ["## Outages (E3): means over repetitions", "",
                  "sent_late = readings the producer could not send within 10 ms of their due time; "
                  "recovery and drain are measured from the restart command; max_age = oldest reading due "
                  "during the outage, from its due time to its arrival.", "", md_table(o), ""]

    e6 = runs[runs["experiment"] == "E6"]
    if len(e6):
        b = e6.groupby("fault_mode").agg(n=("run_id", "count"), delivered=("delivery_ratio", "mean"),
                                         lost=("lost", "mean"), duplicates=("duplicates", "mean"),
                                         unavailable_s=("fault_unavailable_s", "mean")).reset_index()
        b["delivered"] = b["delivered"].map(lambda v: f"{v * 100:.2f}%")
        for col in ("lost", "duplicates", "unavailable_s"):
            b[col] = b[col].map(lambda v: fmt(v, 1))
        lines += ["## Broker outage (E6, MQTT QoS 1)", "", md_table(b), ""]

    lines += ["## Figures", ""] + [f"- {Path(p).name}" for p in made]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
