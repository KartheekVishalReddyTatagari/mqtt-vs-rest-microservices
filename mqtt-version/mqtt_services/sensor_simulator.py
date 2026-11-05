"""Sensor Simulator (MQTT version).

Replays the same deterministic trace with the same open-loop scheduler as
the REST simulator, publishing each reading to sensors/<sensor_id>/readings.

In sent.csv, done_mono_ns is the protocol acknowledgement: the broker's
PUBACK (QoS 1) or PUBCOMP (QoS 2), or the moment the packet was written
(QoS 0). It means the BROKER has the message, not that the Alert Service
does, and is never used as end-to-end latency.

Messages still unacknowledged after ACK_TIMEOUT_S are recorded as
"ack_timeout" (they may still be delivered later; received.csv decides).
"""

import asyncio
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path

import paho.mqtt.client as mqtt

from common import aio
from common.clock import clock_info
from common.config import env_float, env_int, env_str
from common.logsetup import setup_logging
from common.messages import SCHEMA_VERSION, encode
from common.results import SENT_COLUMNS, CsvLog, write_json
from common.scheduler import run_open_loop
from common.workload import TraceItem, WorkloadSpec, build_reading, generate_trace, write_trace
from mqtt_services.mqttconf import QOS_ACK_NAME, MqttSettings, make_client, readings_topic, start

log = logging.getLogger("simulator")


async def main() -> None:
    setup_logging("sensor-simulator")
    run_id = env_str("RUN_ID", "dev")
    results_dir = Path(env_str("RESULTS_DIR", "results-local"))
    max_in_flight = env_int("MAX_IN_FLIGHT", 1000)
    missed_deadline_ms = env_float("MISSED_DEADLINE_MS", 10.0)
    ack_timeout_s = env_float("ACK_TIMEOUT_S", 120.0)
    settings = MqttSettings.from_env()
    spec = WorkloadSpec.from_env()

    trace = generate_trace(spec)
    write_trace(results_dir / "trace.csv", trace)
    sent_log = CsvLog(results_dir / "sent.csv", SENT_COLUMNS)

    loop = asyncio.get_running_loop()
    connected = asyncio.Event()
    lock = threading.Lock()
    waiting: dict[int, asyncio.Future] = {}   # mid -> future, resolved by on_publish
    early: dict[int, tuple[bool, str]] = {}    # acks that arrived before the mid was registered
    client = make_client("sensor-simulator", settings)

    def on_connect(client, userdata, flags, reason_code, properties) -> None:
        if not reason_code.is_failure:
            loop.call_soon_threadsafe(connected.set)

    def on_publish(client, userdata, mid, reason_code, properties) -> None:
        result = (not reason_code.is_failure,
                  QOS_ACK_NAME[settings.qos] if not reason_code.is_failure else str(reason_code))
        with lock:
            future = waiting.pop(mid, None)
            if future is None:
                early[mid] = result
                return
        loop.call_soon_threadsafe(lambda: future.done() or future.set_result(result))

    client.on_connect = on_connect
    client.on_publish = on_publish
    start(client, settings)
    log.info("waiting for broker %s:%d", settings.host, settings.port)
    await asyncio.wait_for(connected.wait(), env_float("STARTUP_TIMEOUT_S", 60.0))
    # Pause before the first message so the runner can apply netem to this container.
    await asyncio.sleep(env_float("START_DELAY_S", 0.0))

    async def dispatch(item: TraceItem, scheduled: int, sent: int) -> bool:
        reading = build_reading(run_id, item, spec.unit, event_ts_ns=time.time_ns(), sent_mono_ns=sent)
        info = client.publish(readings_topic(item.sensor_id), encode(reading.to_dict()), qos=settings.qos)
        if settings.qos == 0 and info.rc != mqtt.MQTT_ERR_SUCCESS:
            ok, detail = False, mqtt.error_string(info.rc)   # QoS 0 while disconnected: dropped
        else:
            future = loop.create_future()
            with lock:
                result = early.pop(info.mid, None)
                if result is None:
                    waiting[info.mid] = future
            if result is None:
                try:
                    result = await asyncio.wait_for(future, ack_timeout_s)
                except asyncio.TimeoutError:
                    with lock:
                        waiting.pop(info.mid, None)
                    result = (False, "ack_timeout")
            ok, detail = result
        sent_log.write([
            run_id, reading.msg_id, item.sensor_id, item.seq, item.index, item.value,
            scheduled, sent, f"{(sent - scheduled) / 1e6:.3f}", reading.event_ts_ns,
            "ok" if ok else "failed", 1, detail, time.monotonic_ns(),
        ])
        return ok

    log.info("run %s: replaying trace %s, %d messages at %.1f msg/s, qos=%d",
             run_id, spec.trace_id, spec.total, spec.rate, settings.qos)
    started_wall_ns = time.time_ns()
    stats = await run_open_loop(trace, spec.rate, dispatch, max_in_flight)
    finished_wall_ns = time.time_ns()
    client.disconnect()
    client.loop_stop()

    sent_log.close()
    producer = stats.summary(missed_deadline_ms)
    write_json(results_dir / "simulator_summary.json", {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "architecture": "mqtt",
        "trace_id": spec.trace_id,
        "workload": {**asdict(spec), "total": spec.total},
        "transport": {**settings.as_dict(), "max_in_flight": max_in_flight, "ack_timeout_s": ack_timeout_s},
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
    aio.run(main())
