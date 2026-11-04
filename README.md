# MQTT for Microservices

Research project, M.Sc. Applied Computer Science, SRH Hochschule.
Student: Kartheek Vishal Reddy. Supervisor: Prof. Peter Dillinger.

We compare **REST (HTTP)** and **MQTT (via a Mosquitto broker)** as the way microservices talk to each other.
The same small system is built twice, then both versions are tested under the same conditions.

## The system (same in both versions)

```
[Sensor Simulator] --> [Processing Service] --> [Alert Service]
```

- **Sensor Simulator**: generates fake sensor readings (e.g. temperature)
- **Processing Service**: checks readings against a threshold
- **Alert Service**: logs and receives alerts

REST version: each service calls the next one with HTTP POST.
MQTT version: each service publishes to a topic on the Mosquitto broker, and the next one subscribes.

## Research questions

1. Latency: REST vs MQTT, normal and degraded network
2. Resilience: what happens when a service crashes or goes down
3. Resource usage: CPU and memory
4. MQTT QoS levels (0, 1, 2): reliability vs overhead

## Repository layout

| Folder | Contents |
|---|---|
| `docs/` | Exposé, `architecture.md` (measurement design), literature |
| `common/` | Code shared by both versions: message contract, workload trace, open-loop scheduler, threshold logic, result recording |
| `rest-version/` | Services that communicate over REST (see its README for how to run) |
| `tests/` | Unit tests and end-to-end acceptance checks (`pytest`) |
| `mqtt-version/` | Services that communicate over MQTT, plus broker config |
| `experiments/` | Scripts for load, latency injection, crash tests |
| `results/` | Collected data and charts |

## Tech stack

- Python 3 (FastAPI for REST, paho-mqtt for MQTT)
- Eclipse Mosquitto broker
- Docker and Docker Compose

## Tests

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
```

The end-to-end tests start the REST services as local processes, so they run
without Docker.

## Timeline

- Weeks 1-2: literature review, setup, REST version
- Weeks 3-4: MQTT version
- Weeks 5-6: experiments and data collection
- Final weeks: analysis and write-up
