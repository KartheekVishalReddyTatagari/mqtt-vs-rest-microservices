# Architecture and measurement design

How the two versions are built and what exactly is measured. This file holds the
design decisions frozen before the benchmark campaign; the Methodology chapter
of the report can be written from it.

## 1. Logical workflow (same in both versions)

1. **Sensor Simulator** replays a deterministic workload trace open-loop.
2. **Processing Service** validates each reading, applies the threshold rule
   (`value > threshold` means alert) and forwards **every** reading, not only alerts.
3. **Alert Service** records every delivery, flags duplicates, and counts each
   alert once per `msg_id`.

All business logic, validation, the message format and the result recording live
in `common/`. The two versions differ only in transport.

## 2. Data paths

**REST:** direct, synchronous request-response.

```
Sensor Simulator --POST /readings--> Processing Service --POST /events--> Alert Service
                 <------ 204 / 502 ---------------------- <---- 204 ---------
```

Processing answers the simulator only after the Alert Service has answered, so
an Alert outage propagates back to the simulator as 502.

**MQTT:** broker-mediated publish/subscribe (MQTT 5.0, Mosquitto 2.0.20, paho-mqtt 2.2.0).

```
Sensor Simulator --publish sensors/{sensor_id}/readings--> Mosquitto --> Processing Service
Processing Service --publish processed/readings--> Mosquitto --> Alert Service
```

Stable client ids, persistent sessions (`clean_start=False`, session expiry 300 s),
retain off, the same QoS on every publish and subscription. Processing acknowledges
an incoming message only after the broker accepted its forward; Alert acknowledges
only after recording. A fresh broker per run (its volume is removed) means no
session leaks from one run into the next.

**Transport fairness.** Both stacks disable Nagle's algorithm (`TCP_NODELAY`):
asyncio/aiohttp do it by default, paho-mqtt does not, so the MQTT clients set it
explicitly. Without it, QoS 1 p95 latency was 11.5 ms instead of 2.1 ms. Both
stacks use one Python 3.12 base image and uvloop where an event loop is used.

## 3. Message contract (schema_version 1)

```json
{ "schema_version": 1, "run_id": "E1-rest-100-r01", "msg_id": "uuid",
  "sensor_id": "sensor-001", "seq": 42, "event_ts_ns": 1730000000000000000,
  "sent_mono_ns": 1234567890123, "value": 31.7, "unit": "C" }
```

| Field | Rule |
|---|---|
| `schema_version` | Must be 1; anything else is rejected |
| `run_id` | Unique per run; isolates results and any late redeliveries from earlier runs |
| `msg_id` | `uuid5(run_id/sensor_id/seq)`: the same on every retry or redelivery |
| `sensor_id`, `seq` | `seq` counts per sensor from 0; gaps reveal losses |
| `event_ts_ns` | Wall clock at generation; for logs and lining up with fault times |
| `sent_mono_ns` | Monotonic time of the **first** dispatch attempt; kept unchanged on retries |

The processed event adds `is_alert`, `threshold`, `processing_received_mono_ns` and
`processing_completed_mono_ns`.

Malformed messages are rejected (HTTP 422 in REST) and written to
`rejected_<service>.csv`. That covers missing fields, wrong types, wrong schema
version, a non-finite value, a negative `seq` and empty ids.

## 4. Timestamps and derived metrics

| Timestamp | Taken | Where |
|---|---|---|
| `sent_mono_ns` | right before the first HTTP request / MQTT publish | Simulator |
| `processing_received_mono_ns` | on entry to the handler / message callback | Processing |
| `processing_completed_mono_ns` | after the threshold logic, before forwarding | Processing |
| `alert_received_mono_ns` | on entry to the handler / message callback | Alert |

```
End-to-end latency = alert_received_mono_ns       - sent_mono_ns
Processing time    = processing_completed_mono_ns - processing_received_mono_ns
Downstream time    = alert_received_mono_ns       - processing_completed_mono_ns
```

**End-to-end ends at the Alert Service's first receipt of a msg_id.** The HTTP
response time and the MQTT PUBACK time are recorded separately (`done_mono_ns`
in `sent.csv`). They are protocol acknowledgements, not delivery, and are never
compared as if they were the same event.

**Shared clock.** Containers on one Linux kernel share `CLOCK_MONOTONIC`, so
timestamps from different containers can be subtracted. This is checked, not
assumed: every service reports `wall_minus_mono_ns` in `/stats`, and the
offsets must agree within a few milliseconds. Monotonic values from different
hosts (e.g. the Windows host and a container) are never subtracted.

## 5. Workload generation

- `WorkloadSpec` (seed, sensors, rate, duration, threshold, spike probability)
  fully determines the trace; `trace_id` is a hash of it. Each run writes its
  `trace.csv`.
- Sensors take turns (round-robin). Normal values are capped below the threshold
  and spikes are above it, so **expected alerts = number of spikes**.
- **Open loop.** Message *i* is due at `start + i / rate`. In-flight messages are
  bounded (`MAX_IN_FLIGHT`). When the bound is hit the scheduler waits, and that
  wait shows up as dispatch lag.
- **Producer health** in `simulator_summary.json`: scheduled, dispatched, ok,
  failed, achieved dispatch rate, peak in-flight, dispatch-lag p50/p99/max, and
  missed deadlines (lag > `MISSED_DEADLINE_MS`). A configured rate is never
  taken as proof that the rate was achieved.

## 6. Delivery semantics

| Mechanism | Behaviour | Treatment |
|---|---|---|
| REST, no retry | One attempt; failure means loss | Baseline (`RETRY_ENABLED=false`) |
| REST, retry | Up to `MAX_RETRIES`; exponential backoff with full jitter, capped; same body (same `msg_id`) every attempt; retries transport errors and 429/500/502/503/504 only | Every attempt is recorded (`detail` = e.g. `ConnectError;503;204`) |
| MQTT QoS 0 | At most once; publish while disconnected drops the message; nothing queued for an offline subscriber | Performance baseline |
| MQTT QoS 1 | At least once; broker queues for offline subscribers; manual ack after forwarding/recording; duplicates possible | Main resilience condition |
| MQTT QoS 2 | Exactly once *per MQTT exchange*; paho keeps PUBREC state in memory only, so a process restart between PUBREC and PUBREL can lose the message | QoS study; not end-to-end exactly-once |

With retries on both REST hops, one message can cause up to (1 + MAX_RETRIES)²
calls to the Alert Service during an outage. This is reported as retry
amplification.

**Idempotency.** The Alert Service keeps the set of `msg_id`s it has seen in this
run. A redelivery is answered normally, logged with `duplicate=1` and not
counted again as an alert. The set takes about 12 MB per 120,000 messages; both
versions pay this cost equally.

## 7. Result files (per run)

| File | Writer | One row per |
|---|---|---|
| `trace.csv` | Simulator | trace item |
| `sent.csv` | Simulator | logical message: schedule, dispatch, lag, status, attempts, ack time |
| `processing.csv` | Processing | message received: received/completed/forwarded times, forward outcome |
| `received.csv` | Alert | delivery, duplicates included |
| `rejected_<service>.csv` | that service | rejected malformed message |
| `*_summary.json` | each service | counters; the simulator's also holds the spec, transport config and producer health |

Each service writes only its own files; no two containers append to one CSV.
Rows are flushed immediately, so a killed container loses nothing it already
recorded. Files live on the Docker volume `mqtt-vs-rest-results` (native Linux
storage); writing through the Windows file share instead cost milliseconds per
row and capped throughput at a few hundred messages per second.
`experiments/export_results.py` copies a run to `results/raw/`.

## 8. Service endpoints

`GET /health` (process alive), `GET /ready` (can accept work; used by the Compose
healthchecks), `GET /stats` (counters and clock info). The MQTT services will
expose the same endpoints over HTTP for orchestration only; they are not part of
the measured data path.

## 9. Frozen decisions

| Decision | Baseline |
|---|---|
| Comparison | Direct synchronous REST vs broker-mediated MQTT 5.0 (Mosquitto) |
| Processing | Forward every reading; alerts are flagged, not filtered |
| End-to-end completion | Alert Service's first receipt of a unique `msg_id` |
| Time source | Monotonic for elapsed time; wall clock for logs and fault alignment; same-kernel check at runtime |
| Workload | Seeded deterministic trace, open-loop replay, bounded in-flight, producer metrics |
| REST reliability | No-retry baseline, plus bounded retry with jitter and a stable `msg_id` |
| MQTT reliability | QoS 1 main condition; QoS 0 and 2 in the QoS study |
| Network impairment | Same `tc netem` rule on every container's interface (see the report's limitations); the MQTT path has 4 hops vs REST's 2, an inherent property of the broker architecture |
| Repetitions | 5 per configuration; 10 for E1 if time allows |
| Out of scope | Fan-out, dead-letter handling, payload-size variation, dashboard, TLS, clustering |
