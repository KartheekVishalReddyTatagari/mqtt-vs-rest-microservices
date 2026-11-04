import csv

from common import logic
from common.alerting import AlertSink
from common.workload import TraceItem, build_reading


def event(seq, value):
    item = TraceItem(index=seq, sensor_id="sensor-001", seq=seq, value=value, is_spike=value > 30)
    return logic.process(build_reading("run-x", item, "C", 0, 1_000_000), 30.0, 2_000_000)


def test_duplicates_are_flagged_and_alerts_counted_once(tmp_path):
    sink = AlertSink(tmp_path)
    alert, normal = event(0, 35.0), event(1, 20.0)
    assert sink.on_event(alert, 3_000_000, 1) is False
    assert sink.on_event(alert, 4_000_000, 2) is True   # redelivery
    assert sink.on_event(normal, 5_000_000, 3) is False
    sink.reject("bad")
    assert sink.stats() == {"deliveries": 3, "unique": 2, "duplicates": 1, "alerts": 1, "rejected": 1}
    sink.close()

    rows = list(csv.DictReader(open(tmp_path / "received.csv")))
    assert [r["duplicate"] for r in rows] == ["0", "1", "0"]   # raw duplicate preserved
    assert rows[0]["latency_ms"] == "2.000"
    assert len(list(csv.DictReader(open(tmp_path / "rejected_alert.csv")))) == 1


def test_restart_appends_instead_of_overwriting(tmp_path):
    first = AlertSink(tmp_path)
    first.on_event(event(0, 20.0), 1, 1)
    first.close()
    second = AlertSink(tmp_path)
    second.on_event(event(1, 20.0), 1, 1)
    second.close()
    rows = list(csv.DictReader(open(tmp_path / "received.csv")))
    assert [r["seq"] for r in rows] == ["0", "1"]
