"""Measurement records written by the services, shared by both versions.

Each service writes only its own files, so no two containers ever append to
the same CSV:

  sent.csv                 Sensor Simulator   one row per logical message
  processing.csv           Processing Service one row per message it received
  received.csv             Alert Service      one row per delivery (duplicates kept)
  rejected_<service>.csv   any service        malformed messages it refused

Rows are flushed immediately. That costs a little, but the cost is the same
in both versions, and rows are not lost when a container is killed during a
crash test. Files are appended to, so a service restarted mid-run keeps the
rows it wrote before the crash.
"""

import csv
import json
import threading
import time
from pathlib import Path
from typing import Any, Sequence

from common.messages import ProcessedEvent

SENT_COLUMNS = [
    "run_id", "msg_id", "sensor_id", "seq", "index", "value",
    "scheduled_mono_ns", "sent_mono_ns", "dispatch_lag_ms", "event_ts_ns",
    "status", "attempts", "detail", "done_mono_ns",
]

PROCESSING_COLUMNS = [
    "run_id", "msg_id", "sensor_id", "seq", "status", "attempts", "detail",
    "received_mono_ns", "completed_mono_ns", "forwarded_mono_ns",
]

RECEIVED_COLUMNS = [
    "run_id", "msg_id", "sensor_id", "seq", "value", "is_alert", "duplicate",
    "sent_mono_ns", "processing_received_mono_ns", "processing_completed_mono_ns",
    "alert_received_mono_ns", "alert_received_wall_ns", "latency_ms",
]

REJECTED_COLUMNS = ["service", "received_wall_ns", "error"]


class CsvLog:
    def __init__(self, path: Path, columns: Sequence[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists() or path.stat().st_size == 0
        self._file = open(path, "a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        self._lock = threading.Lock()
        if is_new:
            self._writer.writerow(columns)
            self._file.flush()

    def write(self, row: Sequence[Any]) -> None:
        with self._lock:
            self._writer.writerow(row)
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.close()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class RejectLog:
    def __init__(self, results_dir: Path, service: str) -> None:
        self._service = service
        self._log = CsvLog(results_dir / f"rejected_{service}.csv", REJECTED_COLUMNS)
        self.count = 0

    def reject(self, error: str) -> None:
        self.count += 1
        self._log.write([self._service, time.time_ns(), error])

    def close(self) -> None:
        self._log.close()


class ProcessingRecorder:
    """What the Processing Service records, in either version."""

    def __init__(self, results_dir: Path) -> None:
        self._log = CsvLog(results_dir / "processing.csv", PROCESSING_COLUMNS)
        self._rejects = RejectLog(results_dir, "processing")
        self.received = 0
        self.forwarded = 0
        self.forward_failed = 0

    def record(self, event: ProcessedEvent, ok: bool, attempts: int, detail: str,
               forwarded_mono_ns: int) -> None:
        self.received += 1
        if ok:
            self.forwarded += 1
        else:
            self.forward_failed += 1
        self._log.write([
            event.run_id, event.msg_id, event.sensor_id, event.seq,
            "forwarded" if ok else "forward_failed", attempts, detail,
            event.processing_received_mono_ns, event.processing_completed_mono_ns, forwarded_mono_ns,
        ])

    def reject(self, error: str) -> None:
        self._rejects.reject(error)

    def stats(self) -> dict[str, int]:
        return {
            "received": self.received,
            "forwarded": self.forwarded,
            "forward_failed": self.forward_failed,
            "rejected": self._rejects.count,
        }

    def close(self) -> None:
        self._log.close()
        self._rejects.close()
