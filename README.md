# MQTT for Microservices

Research project, M.Sc. Applied Computer Science, SRH Hochschule.
Student: Kartheek Vishal Reddy. Supervisor: Prof. Peter Dillinger.

We compare **REST (HTTP)** and **MQTT (via a Mosquitto broker)** as the way microservices talk to each other.
The same small system is built twice, then both versions are tested under the same conditions.

## The system (same in both versions)

```
[Sensor Simulator] --> [Processing Service] --> [Alert Service]
```

- **Sensor Simulator**: replays a deterministic trace of temperature readings at a fixed rate (open loop)
- **Processing Service**: checks each reading against a threshold and forwards every reading
- **Alert Service**: records every delivery (latency, duplicates) and counts alerts

REST version: each service calls the next one with HTTP POST (FastAPI, aiohttp).
MQTT version: each service publishes to a topic on the Mosquitto broker and the next one subscribes (MQTT 5.0, paho-mqtt).
Everything except the transport is shared code in `common/`. Design and measurement rules: `docs/architecture.md`.

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
| `rest-version/` | Services that communicate over REST (see its README) |
| `mqtt-version/` | Services that communicate over MQTT, plus the Mosquitto config (see its README) |
| `experiments/` | Runner, resource monitor, campaign configs (`config/`), analysis pipeline (`analysis/`) |
| `tests/` | Unit tests and end-to-end acceptance checks (`pytest`) |
| `results/` | `raw/` run data (not in git), `processed/` tables and `summary.md`, `figures/` |

## Tech stack

- Python 3.12 in the containers (FastAPI + uvicorn + aiohttp for REST, paho-mqtt 2.2.0 for MQTT)
- Eclipse Mosquitto 2.0.20
- Docker and Docker Compose
- pandas, SciPy and matplotlib for the analysis

## Running the experiments

Requires Docker Desktop (with WSL 2 on Windows).

```bash
# whole campaign; finished runs are skipped if it is restarted
python experiments/runner.py --campaign experiments/config/campaign-reduced.json   # ~3.5 h
python experiments/runner.py --campaign experiments/config/campaign-full.json      # ~13 h, plan-compliant

# a single configuration
python experiments/runner.py --profile mqtt-q1 --rate 500 --duration 120 --repetitions 10 --outage alert:30:10

# list the runs and the estimated time without running anything
python experiments/runner.py --campaign experiments/config/campaign-full.json --dry-run
```

Profiles: `rest`, `rest-retry`, `mqtt-q0`, `mqtt-q1`, `mqtt-q2`. Network profiles: `delay50`,
`delay100`, `loss1`, `loss5`, `delay50-loss1`. Each run is written to
`results/raw/<campaign>/<experiment>/<run id>/` with a `meta.json` describing it completely.

## Analysis

```bash
python experiments/analysis/report.py results/raw/full      # or results/raw/reduced
```

Writes `results/processed/<campaign>/` (run metrics, per-configuration summaries with 95% CIs,
REST-vs-MQTT comparisons, outage table, `summary.md`) and `results/figures/<campaign>/`.
The results of both campaigns are committed; `results/processed/full/summary.md` is the
place to start. The raw run data (about 7 GB) stays out of git.

## Tests

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest              # fast tests, no Docker needed
.venv/Scripts/python -m pytest -m docker    # end-to-end tests against the Docker stacks
```
