"""HTTP management endpoints for the MQTT services: /health, /ready, /stats.

Used only by Docker healthchecks and the experiment runner, never by the
measured data path, which is MQTT end to end. Runs on a daemon thread with
the standard library server, so it adds no dependency.
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable

from common.clock import clock_info

log = logging.getLogger("mgmt")


def serve(port: int, is_ready: Callable[[], bool], stats: Callable[[], dict]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (stdlib name)
            if self.path == "/health":
                self._send(200, {"status": "alive"})
            elif self.path == "/ready":
                ready = is_ready()
                self._send(200 if ready else 503, {"ready": ready})
            elif self.path == "/stats":
                self._send(200, {**stats(), "clock": clock_info()})
            else:
                self._send(404, {"error": "not found"})

        def _send(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:  # silence per-request logging
            pass

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, name="mgmt-http", daemon=True).start()
    log.info("management endpoints on port %d", port)
    return server
