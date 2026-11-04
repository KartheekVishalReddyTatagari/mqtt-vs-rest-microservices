"""Sensor Simulator (REST version).

Replays the deterministic workload trace open-loop (common/scheduler.py),
POSTing each reading to the Processing Service. Writes trace.csv, sent.csv
and simulator_summary.json, then exits.

In sent.csv, done_mono_ns is when the HTTP response arrived: the REST
acknowledgement. It is reported separately and is NOT the end-to-end
measurement, which ends when the Alert Service receives the message.
"""

import asyncio
import logging
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from common.clock import clock_info
from common.config import env_float, env_int, env_str
from common.logsetup import setup_logging
from common.messages import SCHEMA_VERSION, encode
from common.results import SENT_COLUMNS, CsvLog, write_json
from common.scheduler import run_open_loop
from common.workload import TraceItem, WorkloadSpec, build_reading, generate_trace, write_trace
from rest_services.http_retry import RetryPolicy, make_client, post

log = logging.getLogger("simulator")


async def wait_until_ready(client: httpx.AsyncClient, url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if (await client.get(url)).is_success:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise TimeoutError(f"{url} not ready after {timeout_s}s")
        await asyncio.sleep(0.5)


async def main() -> None:
    setup_logging("sensor-simulator")
    run_id = env_str("RUN_ID", "dev")
    results_dir = Path(env_str("RESULTS_DIR", "results-local"))
    target_url = env_str("TARGET_URL", "http://127.0.0.1:8001/readings")
    ready_url = env_str("TARGET_READY_URL", target_url.rsplit("/", 1)[0] + "/ready")
    timeout_s = env_float("REQUEST_TIMEOUT_S", 30.0)
    max_in_flight = env_int("MAX_IN_FLIGHT", 1000)
    missed_deadline_ms = env_float("MISSED_DEADLINE_MS", 10.0)
    spec = WorkloadSpec.from_env()
    policy = RetryPolicy.from_env()

    trace = generate_trace(spec)
    write_trace(results_dir / "trace.csv", trace)
    sent_log = CsvLog(results_dir / "sent.csv", SENT_COLUMNS)

    async with make_client(timeout_s) as client:

        async def dispatch(item: TraceItem, scheduled: int, sent: int) -> bool:
            reading = build_reading(run_id, item, spec.unit, event_ts_ns=time.time_ns(), sent_mono_ns=sent)
            result = await post(client, target_url, encode(reading.to_dict()), policy)
            sent_log.write([
                run_id, reading.msg_id, item.sensor_id, item.seq, item.index, item.value,
                scheduled, sent, f"{(sent - scheduled) / 1e6:.3f}", reading.event_ts_ns,
                "ok" if result.ok else "failed", result.attempts, result.detail, time.monotonic_ns(),
            ])
            return result.ok

        log.info("waiting for %s", ready_url)
        await wait_until_ready(client, ready_url, env_float("STARTUP_TIMEOUT_S", 60.0))
        log.info("run %s: replaying trace %s, %d messages at %.1f msg/s, retry=%s",
                 run_id, spec.trace_id, spec.total, spec.rate, policy.enabled)
        started_wall_ns = time.time_ns()
        stats = await run_open_loop(trace, spec.rate, dispatch, max_in_flight)
        finished_wall_ns = time.time_ns()

    sent_log.close()
    producer = stats.summary(missed_deadline_ms)
    write_json(results_dir / "simulator_summary.json", {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "architecture": "rest",
        "trace_id": spec.trace_id,
        "workload": {**asdict(spec), "total": spec.total},
        "transport": {**policy.as_dict(), "request_timeout_s": timeout_s, "max_in_flight": max_in_flight},
        "expected_alerts": sum(item.is_spike for item in trace),
        "producer": producer,
        "started_wall_ns": started_wall_ns,
        "finished_wall_ns": finished_wall_ns,
        "clock": clock_info(),
    })
    log.info("done: scheduled=%d ok=%d failed=%d rate=%s missed_deadlines=%d",
             producer["scheduled"], producer["ok"], producer["failed"],
             producer["achieved_dispatch_rate"], producer["missed_deadlines"])


if __name__ == "__main__":
    asyncio.run(main())
