"""Alert Service (REST version).

POST /events  receive a processed event, record its end-to-end latency in
              received.csv, count alerts
GET  /stats   messages received and alerts so far
GET  /health  healthcheck
"""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response

from common.alerting import AlertSink
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
    log.info("writing results to %s", RESULTS_DIR)
    yield
    stats = app.state.sink.stats()
    app.state.sink.close()
    write_json(RESULTS_DIR / "alert_summary.json", {"transport": "rest", **stats})
    log.info("stopped: %s", stats)


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/stats")
async def stats() -> dict:
    return app.state.sink.stats()


@app.post("/events")
async def events(request: Request) -> Response:
    recv_ts_ns = time.time_ns()
    try:
        event = ProcessedEvent.from_dict(decode(await request.body()))
    except InvalidMessage as exc:
        return Response(status_code=422, content=str(exc))
    app.state.sink.on_event(event, recv_ts_ns)
    return Response(status_code=204)
