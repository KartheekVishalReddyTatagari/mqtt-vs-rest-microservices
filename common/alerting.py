"""What the Alert Service does with each event, shared by both versions.

Every delivery is written to received.csv, duplicates included (flagged), so
raw redeliveries stay visible. Business handling is idempotent: an alert is
counted only on the first delivery of a msg_id.

Duplicate detection keeps the msg_ids seen in this run in memory (roughly
100 bytes each, so about 12 MB for 120,000 messages). Both versions do the
same, so it does not bias the resource comparison, but it is included in the
Alert Service's memory figures.
"""

import logging
from pathlib import Path

from common.messages import ProcessedEvent
from common.results import RECEIVED_COLUMNS, CsvLog, RejectLog

log = logging.getLogger("alert")


class AlertSink:
    def __init__(self, results_dir: Path) -> None:
        self._log = CsvLog(results_dir / "received.csv", RECEIVED_COLUMNS)
        self._rejects = RejectLog(results_dir, "alert")
        self._seen: set[str] = set()
        self.deliveries = 0
        self.unique = 0
        self.duplicates = 0
        self.alerts = 0

    def on_event(self, event: ProcessedEvent, recv_mono_ns: int, recv_wall_ns: int) -> bool:
        """Record one delivery. Returns True if it was a duplicate."""
        self.deliveries += 1
        duplicate = event.msg_id in self._seen
        if duplicate:
            self.duplicates += 1
        else:
            self._seen.add(event.msg_id)
            self.unique += 1
            if event.is_alert:
                self.alerts += 1
                log.debug("ALERT %s seq=%d value=%.2f > %.2f",
                          event.sensor_id, event.seq, event.value, event.threshold)
        latency_ms = (recv_mono_ns - event.sent_mono_ns) / 1e6
        self._log.write([
            event.run_id, event.msg_id, event.sensor_id, event.seq, event.value,
            int(event.is_alert), int(duplicate),
            event.sent_mono_ns, event.processing_received_mono_ns, event.processing_completed_mono_ns,
            recv_mono_ns, recv_wall_ns, f"{latency_ms:.3f}",
        ])
        return duplicate

    def reject(self, error: str) -> None:
        self._rejects.reject(error)

    def stats(self) -> dict[str, int]:
        return {
            "deliveries": self.deliveries,
            "unique": self.unique,
            "duplicates": self.duplicates,
            "alerts": self.alerts,
            "rejected": self._rejects.count,
        }

    def close(self) -> None:
        self._log.close()
        self._rejects.close()
