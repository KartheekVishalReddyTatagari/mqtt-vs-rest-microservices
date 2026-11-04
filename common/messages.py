"""Message types and the wire format, identical in both versions.

Reading:        Sensor Simulator -> Processing Service
ProcessedEvent: Processing Service -> Alert Service

Both are sent as compact JSON. Timestamps are integer nanoseconds from
time.time_ns(); all containers run on one host and share its clock, so a
timestamp taken in one service can be compared with one taken in another.
"""

import json
from dataclasses import asdict, dataclass
from typing import Any


class InvalidMessage(ValueError):
    """Raised when an incoming message is missing fields or has bad types."""


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


@dataclass(frozen=True, slots=True)
class Reading:
    msg_id: str
    seq: int
    sensor_id: str
    value: float
    unit: str
    sent_ts_ns: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Reading":
        try:
            return cls(
                msg_id=str(data["msg_id"]),
                seq=int(data["seq"]),
                sensor_id=str(data["sensor_id"]),
                value=float(data["value"]),
                unit=str(data["unit"]),
                sent_ts_ns=int(data["sent_ts_ns"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidMessage(f"bad reading: {exc!r}") from exc


@dataclass(frozen=True, slots=True)
class ProcessedEvent:
    msg_id: str
    seq: int
    sensor_id: str
    value: float
    unit: str
    sent_ts_ns: int
    is_alert: bool
    threshold: float
    processed_ts_ns: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessedEvent":
        try:
            return cls(
                msg_id=str(data["msg_id"]),
                seq=int(data["seq"]),
                sensor_id=str(data["sensor_id"]),
                value=float(data["value"]),
                unit=str(data["unit"]),
                sent_ts_ns=int(data["sent_ts_ns"]),
                is_alert=bool(data["is_alert"]),
                threshold=float(data["threshold"]),
                processed_ts_ns=int(data["processed_ts_ns"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidMessage(f"bad processed event: {exc!r}") from exc
