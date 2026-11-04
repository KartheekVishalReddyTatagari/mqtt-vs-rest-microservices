"""Sensor Simulator (REST version).

Generates readings at a fixed rate and POSTs each one to the Processing
Service. Runs for a fixed number of messages, writes sent.csv and
simulator_summary.json, then exits.

Load is open-loop: message N is sent at start + N / RATE whether or not
earlier requests have finished. A closed loop (wait for each response before
sending the next) would quietly lower the send rate whenever the system slows
down, which hides latency ("coordinated omission") and would make REST and
MQTT receive different loads.
"""

import asyncio
import logging
import time
from pathlib import Path

import httpx

from common.config import env_float, env_int, env_str
from common.generator import ReadingGenerator, stamp
from common.logsetup import setup_logging
from common.messages import Reading, encode
from common.results import SENT_COLUMNS, CsvLog, write_json
from services.http_retry import RetryPolicy, make_client, post

log = logging.getLogger("simulator")


async def wait_until_healthy(client: httpx.AsyncClient, url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if (await client.get(url)).is_success:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise TimeoutError(f"{url} not healthy after {timeout_s}s")
        await asyncio.sleep(0.5)


async def send_one(client, url, reading: Reading, policy, sent_log: CsvLog, counts: dict) -> None:
    result = await post(client, url, encode(reading.to_dict()), policy)
    counts["ok" if result.ok else "failed"] += 1
    sent_log.write([
        reading.msg_id, reading.seq, reading.sensor_id, reading.value, reading.sent_ts_ns,
        "ok" if result.ok else "failed", result.attempts, result.detail, time.time_ns(),
    ])


async def main() -> None:
    setup_logging("sensor-simulator")
    run_id = env_str("RUN_ID", "dev")
    results_dir = Path(env_str("RESULTS_DIR", "results-local"))
    target_url = env_str("TARGET_URL", "http://localhost:8001/readings")
    health_url = env_str("TARGET_HEALTH_URL", target_url.rsplit("/", 1)[0] + "/health")
    rate = env_float("RATE", 10.0)
    duration_s = env_float("DURATION_S", 10.0)
    total = int(rate * duration_s)
    seed = env_int("SEED", 42)
    sensor_count = env_int("SENSOR_COUNT", 5)
    threshold = env_float("THRESHOLD", 30.0)
    spike_probability = env_float("SPIKE_PROBABILITY", 0.02)
    policy = RetryPolicy.from_env()

    generator = ReadingGenerator(seed, sensor_count, threshold, spike_probability)
    sent_log = CsvLog(results_dir / "sent.csv", SENT_COLUMNS)
    counts = {"ok": 0, "failed": 0}
    in_flight: set[asyncio.Task] = set()

    async with make_client() as client:
        log.info("waiting for %s", health_url)
        await wait_until_healthy(client, health_url, env_float("STARTUP_TIMEOUT_S", 60.0))
        log.info("sending %d messages at %.1f msg/s to %s (retry=%s)",
                 total, rate, target_url, policy.enabled)

        start = time.perf_counter()
        next_progress = start + 5.0
        for seq in range(total):
            delay = start + seq / rate - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)
            reading = stamp(generator.next_reading())
            task = asyncio.create_task(send_one(client, target_url, reading, policy, sent_log, counts))
            in_flight.add(task)
            task.add_done_callback(in_flight.discard)
            if time.perf_counter() >= next_progress:
                log.info("progress: %d/%d sent, ok=%d failed=%d in_flight=%d",
                         seq + 1, total, counts["ok"], counts["failed"], len(in_flight))
                next_progress += 5.0
        send_elapsed = time.perf_counter() - start

        if in_flight:
            await asyncio.gather(*in_flight)
        total_elapsed = time.perf_counter() - start

    sent_log.close()
    summary = {
        "run_id": run_id,
        "transport": "rest",
        "config": {
            "rate": rate, "duration_s": duration_s, "total": total, "seed": seed,
            "sensor_count": sensor_count, "threshold": threshold,
            "spike_probability": spike_probability,
            "retry_enabled": policy.enabled, "max_retries": policy.max_retries,
            "retry_backoff_s": policy.backoff_s, "retry_backoff_max_s": policy.backoff_max_s,
            "request_timeout_s": env_float("REQUEST_TIMEOUT_S", 5.0),
        },
        "generated": total,
        "ok": counts["ok"],
        "failed": counts["failed"],
        "expected_alerts": generator.expected_alerts,
        "send_elapsed_s": round(send_elapsed, 3),
        "achieved_rate": round(total / send_elapsed, 2) if send_elapsed > 0 else None,
        "total_elapsed_s": round(total_elapsed, 3),
    }
    write_json(results_dir / "simulator_summary.json", summary)
    log.info("done: %s", {k: summary[k] for k in ("generated", "ok", "failed", "expected_alerts", "achieved_rate")})


if __name__ == "__main__":
    asyncio.run(main())
