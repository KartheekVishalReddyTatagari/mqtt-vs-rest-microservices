# REST version

```
Sensor Simulator --POST /readings--> Processing Service --POST /events--> Alert Service
```

| Service | File | Endpoints |
|---|---|---|
| Sensor Simulator | `services/sensor_simulator.py` | client only; runs a fixed number of messages, then exits |
| Processing Service | `services/processing.py` | `POST /readings`, `GET /health` |
| Alert Service | `services/alert.py` | `POST /events`, `GET /stats`, `GET /health` |

The threshold logic, message format, reading generator and result logging come
from the shared `../common/` package, which the MQTT version will use too.

## Run with Docker

From this folder:

```bash
docker compose up --build --abort-on-container-exit --exit-code-from sensor-simulator
```

Override settings per run, always with a new `RUN_ID`:

```bash
RUN_ID=rate100 RATE=100 DURATION_S=30 docker compose up --build --abort-on-container-exit --exit-code-from sensor-simulator
```

In PowerShell, set the variables first: `$env:RUN_ID="rate100"; $env:RATE="100"`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `RUN_ID` | `dev` | Results folder name. Use a new one for every run (CSVs are appended to). |
| `RATE` | `10` | Messages per second (open-loop) |
| `DURATION_S` | `10` | Run length; total messages = RATE x DURATION_S |
| `SEED` | `42` | Same seed gives the same messages in both versions |
| `SENSOR_COUNT` | `5` | Number of simulated sensors |
| `SPIKE_PROBABILITY` | `0.02` | Share of readings above the threshold |
| `THRESHOLD` | `30` | Alert threshold (deg C) |
| `REQUEST_TIMEOUT_S` | `5` | Timeout for Processing -> Alert |
| `SIM_REQUEST_TIMEOUT_S` | `30` | Timeout for Simulator -> Processing. Keep it above Processing's timeout plus retries |
| `RETRY_ENABLED` | `false` | Retry on connection errors, timeouts and 5xx (both hops) |
| `MAX_RETRIES` | `5` | Retries after the first attempt |
| `RETRY_BACKOFF_S` / `RETRY_BACKOFF_MAX_S` | `0.1` / `2` | Exponential backoff, capped |

## Output

`../results/raw/rest/<RUN_ID>/`

| File | Written by | Contents |
|---|---|---|
| `sent.csv` | Simulator | One row per message: msg_id, seq, sent time, status ok/failed, attempts, HTTP status or error |
| `received.csv` | Alert | One row per received event: msg_id, seq, is_alert, sent/processed/received times, latency_ms |
| `simulator_summary.json` | Simulator | Config, counts, expected alerts, achieved rate |
| `alert_summary.json` | Alert | Received and alert counts (written on clean shutdown) |

Loss = msg_ids in `sent.csv` missing from `received.csv`. Duplicates = msg_ids
appearing more than once in `received.csv`.

## Behaviour worth knowing for the experiments

- **Synchronous chain.** The simulator only gets a success once the Alert Service
  has accepted the event. If the Alert Service is down, Processing answers 502 and
  the message is lost unless retried.
- **Retry amplification.** With retries on both hops, one message can cause
  (1 + MAX_RETRIES)^2 calls to the Alert Service during an outage.
- **Open-loop load.** Messages go out on schedule regardless of earlier responses,
  so a slow system shows up as higher latency, not as a lower send rate.
