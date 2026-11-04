"""Open-loop dispatch scheduler, shared by both Sensor Simulators.

Message i is due at start + i / rate, whatever happened to earlier messages.
A closed loop (wait for each reply before sending the next) would quietly
lower the send rate whenever the system slows down, which hides latency
("coordinated omission") and gives REST and MQTT different loads.

The number of messages in flight is bounded (max_in_flight). When the bound
is reached the scheduler waits, and the wait shows up as dispatch lag
(actual send time minus scheduled send time). Lag, missed deadlines and peak
in-flight count are reported, so producer saturation is visible instead of
silently lowering the rate.
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from common.workload import TraceItem

log = logging.getLogger("scheduler")

# dispatch(item, scheduled_mono_ns, sent_mono_ns) -> True if the message was delivered/acknowledged
Dispatch = Callable[[TraceItem, int, int], Awaitable[bool]]


@dataclass
class ProducerStats:
    scheduled: int = 0
    dispatched: int = 0
    ok: int = 0
    failed: int = 0
    in_flight: int = 0
    max_in_flight: int = 0
    first_sent_mono_ns: int = 0
    last_sent_mono_ns: int = 0
    lags_ms: list[float] = field(default_factory=list)

    def summary(self, missed_deadline_ms: float) -> dict:
        lags = sorted(self.lags_ms)
        span_s = (self.last_sent_mono_ns - self.first_sent_mono_ns) / 1e9
        return {
            "scheduled": self.scheduled,
            "dispatched": self.dispatched,
            "ok": self.ok,
            "failed": self.failed,
            "achieved_dispatch_rate": round((self.dispatched - 1) / span_s, 2) if span_s > 0 else None,
            "max_in_flight": self.max_in_flight,
            "dispatch_lag_ms": {
                "p50": _pct(lags, 0.50), "p99": _pct(lags, 0.99),
                "max": round(lags[-1], 3) if lags else None,
                "mean": round(statistics.fmean(lags), 3) if lags else None,
            },
            "missed_deadline_ms": missed_deadline_ms,
            "missed_deadlines": sum(1 for x in lags if x > missed_deadline_ms),
        }


def _pct(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    return round(sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))], 3)


async def run_open_loop(items: list[TraceItem], rate: float, dispatch: Dispatch,
                        max_in_flight: int, progress_every_s: float = 5.0) -> ProducerStats:
    stats = ProducerStats()
    slots = asyncio.Semaphore(max_in_flight)
    tasks: set[asyncio.Task] = set()

    async def run_one(item: TraceItem, scheduled: int) -> None:
        sent = time.monotonic_ns()
        stats.dispatched += 1
        stats.in_flight += 1
        stats.max_in_flight = max(stats.max_in_flight, stats.in_flight)
        stats.lags_ms.append((sent - scheduled) / 1e6)
        if not stats.first_sent_mono_ns:
            stats.first_sent_mono_ns = sent
        stats.last_sent_mono_ns = sent
        try:
            ok = await dispatch(item, scheduled, sent)
        except Exception:  # a transport bug must not stop the run; count it as failed
            log.exception("dispatch raised for %s seq=%d", item.sensor_id, item.seq)
            ok = False
        finally:
            stats.in_flight -= 1
            slots.release()
        if ok:
            stats.ok += 1
        else:
            stats.failed += 1

    start = time.monotonic_ns()
    next_progress = start + int(progress_every_s * 1e9)
    for item in items:
        scheduled = start + round(item.index * 1e9 / rate)
        delay = (scheduled - time.monotonic_ns()) / 1e9
        # Always yield at least once, so started tasks run even when behind schedule.
        await asyncio.sleep(max(delay, 0))
        await slots.acquire()
        stats.scheduled += 1
        task = asyncio.create_task(run_one(item, scheduled))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        now = time.monotonic_ns()
        if now >= next_progress:
            log.info("progress: %d/%d scheduled, ok=%d failed=%d in_flight=%d",
                     stats.scheduled, len(items), stats.ok, stats.failed, stats.in_flight)
            next_progress = now + int(progress_every_s * 1e9)

    if tasks:
        await asyncio.gather(*tasks)
    return stats
