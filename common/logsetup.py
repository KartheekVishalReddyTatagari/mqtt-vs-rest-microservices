import logging

from common.config import env_str


def setup_logging(service: str) -> None:
    logging.basicConfig(
        level=env_str("LOG_LEVEL", "INFO").upper(),
        format=f"%(asctime)s {service} %(levelname)s %(message)s",
    )
    # httpx logs every request at INFO. Per-message logging would add I/O cost
    # to every message and distort the latency and CPU measurements.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
