"""Processing Service (REST version).

POST /readings  receive a reading, check it against the threshold, then POST
                the result to the Alert Service and wait for its answer.
GET  /health    healthcheck

The call to the Alert Service is synchronous: the simulator's request only
succeeds once the Alert Service has accepted the event. If the Alert Service
is down, this service answers 502 and the reading is lost unless the
simulator retries. That tight coupling is what RQ2 measures.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from common import logic
from common.config import env_float, env_str
from common.logsetup import setup_logging
from common.messages import InvalidMessage, Reading, decode, encode
from services.http_retry import RetryPolicy, make_client, post

setup_logging("processing")
log = logging.getLogger("processing")

THRESHOLD = env_float("THRESHOLD", 30.0)
ALERT_URL = env_str("ALERT_URL", "http://localhost:8002/events")
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
    app.state.client = make_client()
    log.info("forwarding to %s, threshold=%.2f, retry=%s", ALERT_URL, THRESHOLD, POLICY.enabled)
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/readings")
async def readings(request: Request) -> Response:
    try:
        reading = Reading.from_dict(decode(await request.body()))
    except InvalidMessage as exc:
        return Response(status_code=422, content=str(exc))

    event = logic.process(reading, THRESHOLD)
    result = await post(app.state.client, ALERT_URL, encode(event.to_dict()), POLICY)
    if not result.ok:
        _note_failure(result.detail)
        return Response(status_code=502, content=f"alert service: {result.detail}")
    return Response(status_code=204)
