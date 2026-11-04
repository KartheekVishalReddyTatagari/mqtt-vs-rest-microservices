# REST version

```
Sensor Simulator --POST /readings--> Processing Service --POST /events--> Alert Service
```

| Service | File | Endpoints |
|---|---|---|
| Sensor Simulator | `rest_services/sensor_simulator.py` | client only; replays the trace, then exits |
| Processing Service | `rest_services/processing.py` | `POST /readings`, `GET /health`, `GET /ready`, `GET /stats` |
| Alert Service | `rest_services/alert.py` | `POST /events`, `GET /health`, `GET /ready`, `GET /stats` |

Business logic, message contract, workload, scheduler and result recording come
from the shared `../common/` package. See `../docs/architecture.md` for the
measurement design.

## Run with Docker

From this folder:

```bash
docker compose up --build --abort-on-container-exit --exit-code-from sensor-simulator
```

With settings, always with a new `RUN_ID` (PowerShell):

```powershell
$env:RUN_ID="rate100"; $env:RATE="100"; $env:DURATION_S="30"
docker compose up --build --abort-on-container-exit --exit-code-from sensor-simulator
```

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `RUN_ID` | `dev` | Results folder and message ids. New one for every run (CSVs are appended to) |
| `RATE` | `10` | Messages per second (open loop) |
| `DURATION_S` | `10` | Run length; total messages = RATE x DURATION_S |
| `SEED` | `42` | Same seed = same trace in both versions |
| `SENSOR_COUNT` | `5` | Simulated sensors (round-robin) |
| `SPIKE_PROBABILITY` | `0.02` | Share of readings above the threshold |
| `THRESHOLD` | `30` | Alert threshold (deg C), strictly greater |
| `MAX_IN_FLIGHT` | `1000` | Bound on concurrent requests from the simulator |
| `MISSED_DEADLINE_MS` | `10` | Dispatch lag above this counts as a missed deadline |
| `REQUEST_TIMEOUT_S` | `5` | Timeout for Processing -> Alert |
| `SIM_REQUEST_TIMEOUT_S` | `30` | Timeout for Simulator -> Processing; keep above Processing's timeout plus retries |
| `RETRY_ENABLED` | `false` | Retry transient failures (both hops) |
| `MAX_RETRIES` | `5` | Retries after the first attempt |
| `RETRY_BACKOFF_S` / `RETRY_BACKOFF_MAX_S` | `0.1` / `2` | Exponential backoff cap per attempt; actual wait is random in [0, cap] |

## Output

`../results/raw/rest/<RUN_ID>/`: `trace.csv`, `sent.csv`, `processing.csv`,
`received.csv`, `rejected_<service>.csv`, and `simulator_summary.json`,
`processing_summary.json`, `alert_summary.json`. Columns are described in
`../docs/architecture.md`, section 7. Service summaries are written on clean
shutdown.

## Behaviour worth knowing for the experiments

- **Synchronous chain.** The simulator gets 204 only after the Alert Service has
  accepted the event. If the Alert Service is down, Processing answers 502.
- **Retry amplification.** With retries on both hops, one message can cause up to
  (1 + MAX_RETRIES)^2 calls to the Alert Service during an outage.
- **Ack is not delivery.** `done_mono_ns` in `sent.csv` is the HTTP response time.
  End-to-end latency is measured at the Alert Service.
