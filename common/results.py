"""Measurement output: CSV logs and JSON summaries.

Each CSV row is flushed immediately. That costs a little, but the cost is the
same in both versions, and it means rows are not lost when a container is
killed during a crash test.
"""

import csv
import json
import threading
from pathlib import Path
from typing import Any, Sequence

SENT_COLUMNS = [
    "msg_id", "seq", "sensor_id", "value", "sent_ts_ns",
    "status", "attempts", "detail", "done_ts_ns",
]

RECEIVED_COLUMNS = [
    "msg_id", "seq", "sensor_id", "value", "is_alert",
    "sent_ts_ns", "processed_ts_ns", "recv_ts_ns", "latency_ms",
]


class CsvLog:
    def __init__(self, path: Path, columns: Sequence[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not path.exists() or path.stat().st_size == 0
        # Append, so a service restarted mid-run (crash tests) keeps earlier rows.
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
