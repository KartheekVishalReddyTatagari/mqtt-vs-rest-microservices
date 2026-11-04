import pytest

from common import logic
from common.messages import InvalidMessage, ProcessedEvent, Reading, decode, encode
from common.workload import TraceItem, build_reading


def make_reading(value=25.0, seq=3):
    item = TraceItem(index=0, sensor_id="sensor-001", seq=seq, value=value, is_spike=False)
    return build_reading("run-x", item, "C", event_ts_ns=1, sent_mono_ns=2)


def test_reading_round_trip():
    reading = make_reading()
    assert Reading.from_dict(decode(encode(reading.to_dict()))) == reading


def test_processed_event_round_trip():
    event = logic.process(make_reading(), 30.0, received_mono_ns=5)
    assert ProcessedEvent.from_dict(decode(encode(event.to_dict()))) == event


@pytest.mark.parametrize("change", [
    {"msg_id": None},          # removed below
    {"schema_version": 2},
    {"seq": -1},
    {"value": "warm"},
    {"value": float("nan")},
    {"run_id": ""},
])
def test_malformed_reading_is_rejected(change):
    data = make_reading().to_dict()
    for key, value in change.items():
        if value is None:
            del data[key]
        else:
            data[key] = value
    with pytest.raises(InvalidMessage):
        Reading.from_dict(data)


@pytest.mark.parametrize("body", [b"not json", b"[1, 2]", b"\xff\xfe"])
def test_bad_body_is_rejected(body):
    with pytest.raises(InvalidMessage):
        decode(body)


def test_processed_event_requires_boolean_alert_flag():
    data = logic.process(make_reading(), 30.0, 5).to_dict()
    data["is_alert"] = "yes"
    with pytest.raises(InvalidMessage):
        ProcessedEvent.from_dict(data)


@pytest.mark.parametrize("value,expected", [(29.99, False), (30.0, False), (30.01, True)])
def test_threshold_is_strictly_greater(value, expected):
    assert logic.process(make_reading(value=value), 30.0, 0).is_alert is expected


def test_processing_keeps_identity_and_timestamps():
    reading = make_reading()
    event = logic.process(reading, 30.0, received_mono_ns=5)
    assert (event.msg_id, event.seq, event.sent_mono_ns) == (reading.msg_id, reading.seq, reading.sent_mono_ns)
    assert event.processing_received_mono_ns == 5
    assert event.processing_completed_mono_ns >= 5
