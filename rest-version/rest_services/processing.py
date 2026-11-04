"""Processing Service (REST version).

POST /readings  validate, apply the threshold logic, then POST the result to
                the Alert Service and wait for its answer
GET  /health    process is alive
GET  /ready     service can accept work
GET  /stats     counters and clock info

The call to the Alert Service is synchronous: the simulator's request only
succeeds once the Alert Service has accepted the event. If the Alert Service
is down, this service answers 502 and the reading is lost unless the
simulator retries. That tight coupling is what RQ2 measures.
"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response

from common import logic
from common.clock import clock_info
from common.config import env_float, env_str
from common.logsetup import setup_logging
from common.messages import InvalidMessage, Reading, decode, encode
from common.results import ProcessingRecorder, write_json
from rest_services.http_retry import RetryPolicy, make_client, post

setup_logging("processing")
log = logging.getLogger("processing")

THRESHOLD = env_float("THRESHOLD", 30.0)
ALERT_URL = env_str("ALERT_URL", "http://127.0.0.1:8002/events")
RESULTS_DIR = Path(env_str("RESULTS_DIR", "results-local"))
POLICY = RetryPolicy.from_env()

# During an outage every message fails. Logging each one would add I/O cost to
# every message, so failures are summarised at most once per second.
_failures = {"count": 0, "last_log": 0.0}


def _note_failure(detail: str) -> None:
    _failures["count"] += 1
    now = time.monotonic()
    if now - _failures["last_log"] >= 1.0:
        log.warning("alert service unreachable (%s): %d forward(s) failed since last report",
                    detail, _failures["count"])
        _failures["count"] = 0
        _failures["last_log"] = now


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.recorder = ProcessingRecorder(RESULTS_DIR)
    app.state.client = make_client(env_float("REQUEST_TIMEOUT_S", 5.0))
    app.state.ready = True
    log.info("forwarding to %s, threshold=%.2f, retry=%s", ALERT_URL, THRESHOLD, POLICY.enabled)
    yield
    app.state.ready = False
    await app.state.client.aclose()
    stats = app.state.recorder.stats()
    app.state.recorder.close()
    write_json(RESULTS_DIR / "processing_summary.json", {"architecture": "rest", **stats})
    log.info("stopped: %s", stats)


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "alive"}


@app.get("/ready")
async def ready() -> Response:
    ok = getattr(app.state, "ready", False)
    return Response(status_code=200 if ok else 503, content="ready" if ok else "not ready")


@app.get("/stats")
async def stats() -> dict:
    return {**app.state.recorder.stats(), "clock": clock_info()}


@app.post("/readings")
async def readings(request: Request) -> Response:
    received = time.monotonic_ns()
    recorder: ProcessingRecorder = app.state.recorder
    try:
        reading = Reading.from_dict(decode(await request.body()))
    except InvalidMessage as exc:
        recorder.reject(str(exc))
        return Response(status_code=422, content=str(exc))

    event = logic.process(reading, THRESHOLD, received)
    result = await post(app.state.client, ALERT_URL, encode(event.to_dict()), POLICY)
    recorder.record(event, result.ok, result.attempts, result.detail, time.monotonic_ns())
    if not result.ok:
        _note_failure(result.history[-1])
        return Response(status_code=502, content=f"alert service: {result.detail}")
    return Response(status_code=204)
