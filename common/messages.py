"""Message contract and wire format, identical in both versions.

Reading:        Sensor Simulator -> Processing Service
ProcessedEvent: Processing Service -> Alert Service

Both travel as compact JSON. See docs/architecture.md for the field rules.

Timestamps
- *_mono_ns: time.monotonic_ns(). Used for every elapsed-time measurement.
  All containers run on one Linux kernel and share its monotonic clock, so a
  value taken in one container can be subtracted from one taken in another.
  (Checked at runtime: every service reports its wall-minus-monotonic offset.)
- event_ts_ns: wall clock (time.time_ns()), for human-readable logs and for
  lining up results with fault-injection times recorded by the runner.
"""

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA_VERSION = 1


class InvalidMessage(ValueError):
    """Raised when an incoming message is malformed."""


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def decode(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidMessage(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidMessage("message must be a JSON object")
    return data


def _reading_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate the fields shared by Reading and ProcessedEvent."""
    try:
        fields = {
            "schema_version": int(data["schema_version"]),
            "run_id": str(data["run_id"]),
            "msg_id": str(data["msg_id"]),
            "sensor_id": str(data["sensor_id"]),
            "seq": int(data["seq"]),
            "event_ts_ns": int(data["event_ts_ns"]),
            "sent_mono_ns": int(data["sent_mono_ns"]),
            "value": float(data["value"]),
            "unit": str(data["unit"]),
        }
    except KeyError as exc:
        raise InvalidMessage(f"missing field {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise InvalidMessage(f"bad field type: {exc}") from exc
    if fields["schema_version"] != SCHEMA_VERSION:
        raise InvalidMessage(f"unsupported schema_version {fields['schema_version']}")
    if not fields["run_id"] or not fields["msg_id"] or not fields["sensor_id"]:
        raise InvalidMessage("run_id, msg_id and sensor_id must not be empty")
    if fields["seq"] < 0:
        raise InvalidMessage("seq must be >= 0")
    if not math.isfinite(fields["value"]):
        raise InvalidMessage("value must be a finite number")
    return fields


@dataclass(frozen=True, slots=True)
class Reading:
    schema_version: int
    run_id: str
    msg_id: str
    sensor_id: str
    seq: int            # per-sensor sequence number, starts at 0
    event_ts_ns: int    # wall clock when the reading was generated
    sent_mono_ns: int   # monotonic, first dispatch attempt; unchanged on retries
    value: float
    unit: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reading":
        return cls(**_reading_fields(data))


@dataclass(frozen=True, slots=True)
class ProcessedEvent:
    schema_version: int
    run_id: str
    msg_id: str
    sensor_id: str
    seq: int
    event_ts_ns: int
    sent_mono_ns: int
    value: float
    unit: str
    is_alert: bool
    threshold: float
    processing_received_mono_ns: int
    processing_completed_mono_ns: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessedEvent":
        fields = _reading_fields(data)
        try:
            is_alert = data["is_alert"]
            if not isinstance(is_alert, bool):
                raise TypeError("is_alert must be a boolean")
            fields.update(
                is_alert=is_alert,
                threshold=float(data["threshold"]),
                processing_received_mono_ns=int(data["processing_received_mono_ns"]),
                processing_completed_mono_ns=int(data["processing_completed_mono_ns"]),
            )
        except KeyError as exc:
            raise InvalidMessage(f"missing field {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise InvalidMessage(f"bad field type: {exc}") from exc
        return cls(**fields)
