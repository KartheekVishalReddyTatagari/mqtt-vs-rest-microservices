import asyncio
import time

from common.scheduler import run_open_loop
from common.workload import WorkloadSpec, generate_trace


def test_open_loop_keeps_rate_even_when_dispatch_is_slow():
    trace = generate_trace(WorkloadSpec(seed=1, sensor_count=2, rate=200, duration_s=0.5,
                                        threshold=30, spike_probability=0))

    async def slow_dispatch(item, scheduled, sent):
        await asyncio.sleep(0.1)   # far slower than the 5 ms send interval
        return True

    start = time.monotonic()
    stats = asyncio.run(run_open_loop(trace, 200, slow_dispatch, max_in_flight=1000))
    elapsed = time.monotonic() - start
    assert stats.ok == stats.dispatched == len(trace) == 100
    assert stats.max_in_flight > 1          # sends did not wait for replies
    assert elapsed < 1.0                    # closed loop would take 100 x 0.1 s = 10 s


def test_in_flight_bound_shows_up_as_dispatch_lag():
    trace = generate_trace(WorkloadSpec(seed=1, sensor_count=1, rate=100, duration_s=0.2,
                                        threshold=30, spike_probability=0))

    async def slow_dispatch(item, scheduled, sent):
        await asyncio.sleep(0.05)
        return item.index % 2 == 0

    stats = asyncio.run(run_open_loop(trace, 100, slow_dispatch, max_in_flight=1))
    summary = stats.summary(missed_deadline_ms=10)
    assert stats.max_in_flight == 1
    assert summary["missed_deadlines"] > 0  # saturation is visible, not hidden
    assert (stats.ok, stats.failed) == (10, 10)


def test_dispatch_exception_counts_as_failure():
    trace = generate_trace(WorkloadSpec(seed=1, sensor_count=1, rate=1000, duration_s=0.005,
                                        threshold=30, spike_probability=0))

    async def broken(item, scheduled, sent):
        raise RuntimeError("boom")

    stats = asyncio.run(run_open_loop(trace, 1000, broken, max_in_flight=10))
    assert stats.failed == len(trace) and stats.ok == 0
