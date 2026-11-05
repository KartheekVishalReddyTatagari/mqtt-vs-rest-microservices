# MQTT version

```
Sensor Simulator --publish sensors/<id>/readings--> Mosquitto --> Processing Service
Processing Service --publish processed/readings--> Mosquitto --> Alert Service
```

| Service | File | Notes |
|---|---|---|
| Mosquitto 2.0.20 | `mosquitto/mosquitto.conf` | persistence on, queue limits raised, TCP_NODELAY |
| Sensor Simulator | `mqtt_services/sensor_simulator.py` | same trace and open-loop scheduler as REST; waits for PUBACK/PUBCOMP |
| Processing Service | `mqtt_services/processing.py` | acknowledges an incoming message only after its forward is accepted |
| Alert Service | `mqtt_services/alert.py` | acknowledges only after recording |

All three use MQTT 5.0 (paho-mqtt 2.2.0), stable client ids and persistent
sessions (`clean_start=False`, session expiry 300 s). Processing and Alert also
serve `/health`, `/ready`, `/stats` over HTTP on port 8000 for orchestration
only. Business logic, message contract, workload, scheduler and result
recording come from the shared `../common/` package.

## Run

```bash
docker volume create mqtt-vs-rest-results
docker compose up --build --abort-on-container-exit --exit-code-from sensor-simulator
docker compose down -v
```

`down -v` deletes the broker's stored sessions (so the next run starts clean),
never the results volume, which is external.

## Settings (in addition to the workload settings in ../rest-version/README.md)

| Variable | Default | Meaning |
|---|---|---|
| `MQTT_QOS` | `1` | QoS for every publish and subscription (0, 1 or 2) |
| `SESSION_EXPIRY_S` | `300` | How long the broker keeps an offline client's session and queue |
| `MQTT_KEEPALIVE_S` | `10` | Keepalive; a dead client is noticed within 1.5 x this |
| `MQTT_MAX_INFLIGHT` | `100` | Client-side unacknowledged QoS 1/2 messages |
| `ACK_TIMEOUT_S` | `120` | Simulator gives up waiting for a broker ack after this (recorded as `ack_timeout`) |

## Delivery behaviour (verified)

| Case | Outcome |
|---|---|
| QoS 1, Alert Service killed for ~6 s at 200 msg/s | 4000/4000 delivered; broker queued the backlog |
| QoS 0, same | 2708/4000 delivered; the simulator still saw 4000 broker acks |
| QoS 1, Processing killed for ~6 s | 4000/4000 delivered |

QoS 2 caveat: paho sends PUBREC before the application sees a message and keeps
that state only in memory, so a process restart in between can lose it. QoS 2
is exactly-once per MQTT exchange, not end to end across a crash.
