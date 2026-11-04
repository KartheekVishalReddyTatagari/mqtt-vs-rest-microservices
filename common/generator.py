"""Deterministic sensor-reading generator.

With the same seed, both versions produce exactly the same sequence of
msg_ids, sensors and values. That makes the equivalence check possible
(same input -> same number of alerts) and keeps runs comparable.

Normal readings are drawn around `base_mean` and capped just below the
threshold. With probability `spike_probability` a reading is a spike above
the threshold. So the expected number of alerts equals the number of spikes,
which `expected_alerts` reports.
"""

import random
import time
import uuid
from dataclasses import replace

from common.messages import Reading


class ReadingGenerator:
    def __init__(
        self,
        seed: int,
        sensor_count: int,
        threshold: float,
        spike_probability: float,
        base_mean: float = 22.0,
        base_std: float = 1.5,
        unit: str = "C",
    ) -> None:
        if sensor_count < 1:
            raise ValueError("sensor_count must be >= 1")
        if not 0.0 <= spike_probability <= 1.0:
            raise ValueError("spike_probability must be between 0 and 1")
        self._rng = random.Random(seed)
        self._sensor_count = sensor_count
        self._threshold = threshold
        self._spike_probability = spike_probability
        self._base_mean = base_mean
        self._base_std = base_std
        self._unit = unit
        self._seq = 0
        self.expected_alerts = 0

    def next_reading(self) -> Reading:
        """Next reading in the sequence. sent_ts_ns is 0 until stamp() is called."""
        rng = self._rng
        msg_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        if rng.random() < self._spike_probability:
            value = self._threshold + rng.uniform(1.0, 10.0)
            self.expected_alerts += 1
        else:
            value = min(rng.gauss(self._base_mean, self._base_std), self._threshold - 0.01)
        reading = Reading(
            msg_id=msg_id,
            seq=self._seq,
            sensor_id=f"s{self._seq % self._sensor_count}",
            value=round(value, 2),
            unit=self._unit,
            sent_ts_ns=0,
        )
        self._seq += 1
        return reading


def stamp(reading: Reading) -> Reading:
    """Set the send timestamp, right before the message goes out."""
    return replace(reading, sent_ts_ns=time.time_ns())
