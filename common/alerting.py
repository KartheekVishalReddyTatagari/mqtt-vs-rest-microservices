"""What the Alert Service does with each event, shared by both versions."""

import logging
from pathlib import Path

from common.messages import ProcessedEvent
from common.results import RECEIVED_COLUMNS, CsvLog

log = logging.getLogger("alert")


class AlertSink:
    """Records every received event and counts alerts.

    Duplicates and losses are worked out afterwards from the CSVs (join on
    msg_id), so no set of seen ids is kept in memory. Keeping one would grow
    memory over a run and distort the resource measurements (RQ3).
    """

    def __init__(self, results_dir: Path) -> None:
        self._log = CsvLog(results_dir / "received.csv", RECEIVED_COLUMNS)
        self.received = 0
        self.alerts = 0

    def on_event(self, event: ProcessedEvent, recv_ts_ns: int) -> None:
        self.received += 1
        if event.is_alert:
            self.alerts += 1
            log.debug("ALERT %s value=%.2f > %.2f (seq %d)",
                      event.sensor_id, event.value, event.threshold, event.seq)
        latency_ms = (recv_ts_ns - event.sent_ts_ns) / 1e6
        self._log.write([
            event.msg_id, event.seq, event.sensor_id, event.value, int(event.is_alert),
            event.sent_ts_ns, event.processed_ts_ns, recv_ts_ns, f"{latency_ms:.3f}",
        ])

    def stats(self) -> dict[str, int]:
        return {"received": self.received, "alerts": self.alerts}

    def close(self) -> None:
        self._log.close()
