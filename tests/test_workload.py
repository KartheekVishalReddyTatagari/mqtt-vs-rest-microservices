from collections import defaultdict
from dataclasses import replace

import pytest

from common.workload import WorkloadSpec, generate_trace, make_msg_id

SPEC = WorkloadSpec(seed=7, sensor_count=4, rate=100, duration_s=5, threshold=30, spike_probability=0.05)


def test_same_spec_gives_same_trace():
    assert generate_trace(SPEC) == generate_trace(SPEC)


def test_different_seed_gives_different_trace():
    assert generate_trace(SPEC) != generate_trace(replace(SPEC, seed=8))


def test_trace_length_and_round_robin_sensors():
    trace = generate_trace(SPEC)
    assert len(trace) == SPEC.total == 500
    assert [t.sensor_id for t in trace[:5]] == ["sensor-001", "sensor-002", "sensor-003", "sensor-004", "sensor-001"]


def test_per_sensor_sequence_numbers_are_contiguous():
    per_sensor = defaultdict(list)
    for item in generate_trace(SPEC):
        per_sensor[item.sensor_id].append(item.seq)
    for seqs in per_sensor.values():
        assert seqs == list(range(len(seqs)))


def test_alerts_equal_spikes():
    trace = generate_trace(SPEC)
    assert all((t.value > SPEC.threshold) == t.is_spike for t in trace)
    assert sum(t.is_spike for t in trace) > 0


def test_msg_id_is_stable_and_unique():
    assert make_msg_id("r1", "sensor-001", 0) == make_msg_id("r1", "sensor-001", 0)
    assert make_msg_id("r1", "sensor-001", 0) != make_msg_id("r2", "sensor-001", 0)
    ids = {make_msg_id("r1", t.sensor_id, t.seq) for t in generate_trace(SPEC)}
    assert len(ids) == SPEC.total


def test_trace_id_changes_with_spec():
    assert SPEC.trace_id == WorkloadSpec(**SPEC.__dict__).trace_id
    assert SPEC.trace_id != replace(SPEC, rate=200).trace_id


@pytest.mark.parametrize("bad", [{"sensor_count": 0}, {"rate": 0}, {"spike_probability": 1.5}])
def test_invalid_spec_is_refused(bad):
    with pytest.raises(ValueError):
        replace(SPEC, **bad)
