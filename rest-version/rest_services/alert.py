"""Alert Service (REST version).

POST /events  record the delivery (duplicates flagged), count alerts once
              per msg_id
GET  /health  process is alive
GET  /ready   service can accept work
GET  /stats   counters and clock info

A duplicate delivery is still answered 204: it was received successfully,
and the business handling is idempotent.
"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response

from common.alerting import AlertSink
from common.clock import clock_info
from common.config import env_str
from common.logsetup import setup_logging
from common.messages import InvalidMessage, ProcessedEvent, decode
from common.results import write_json

setup_logging("alert")
log = logging.getLogger("alert")

RESULTS_DIR = Path(env_str("RESULTS_DIR", "results-local"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.sink = AlertSink(RESULTS_DIR)
    app.state.ready = True
    log.info("writing results to %s", RESULTS_DIR)
    yield
    app.state.ready = False
    stats = app.state.sink.stats()
    app.state.sink.close()
    write_json(RESULTS_DIR / "alert_summary.json", {"architecture": "rest", **stats})
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
    return {**app.state.sink.stats(), "clock": clock_info()}


@app.post("/events")
async def events(request: Request) -> Response:
    recv_mono_ns = time.monotonic_ns()
    recv_wall_ns = time.time_ns()
    try:
        event = ProcessedEvent.from_dict(decode(await request.body()))
    except InvalidMessage as exc:
        app.state.sink.reject(str(exc))
        return Response(status_code=422, content=str(exc))
    app.state.sink.on_event(event, recv_mono_ns, recv_wall_ns)
    return Response(status_code=204)
