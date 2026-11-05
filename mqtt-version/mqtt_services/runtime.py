"""Process lifecycle for the long-running MQTT services (Processing, Alert).

Waits for SIGTERM/SIGINT, then disconnects cleanly so the summary can be
written. A SIGKILL (docker kill) skips this, as a real crash would.
"""

import signal
import threading


def wait_for_shutdown() -> None:
    stop = threading.Event()

    def handle(signum, frame) -> None:
        stop.set()

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    while not stop.wait(0.5):
        pass


class ConnectionState:
    """Connection and subscription state, updated from paho's network thread."""

    def __init__(self) -> None:
        self.connected = False
        self.subscribed = False
        self.connects = 0
        self.disconnects = 0
        self.session_resumed = 0

    def ready(self) -> bool:
        return self.connected and self.subscribed

    def as_dict(self) -> dict:
        return {"connected": self.connected, "subscribed": self.subscribed, "connects": self.connects,
                "disconnects": self.disconnects, "session_resumed": self.session_resumed}
