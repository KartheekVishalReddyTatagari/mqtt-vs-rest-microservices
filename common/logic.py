"""Business logic of the Processing Service, shared by both versions."""

import time

from common.messages import ProcessedEvent, Reading


def process(reading: Reading, threshold: float) -> ProcessedEvent:
    """Check a reading against the threshold.

    Every reading is forwarded (not only alerts), so end-to-end latency can be
    measured for every message. The Alert Service acts on `is_alert`.
    """
    return ProcessedEvent(
        msg_id=reading.msg_id,
        seq=reading.seq,
        sensor_id=reading.sensor_id,
        value=reading.value,
        unit=reading.unit,
        sent_ts_ns=reading.sent_ts_ns,
        is_alert=reading.value > threshold,
        threshold=threshold,
        processed_ts_ns=time.time_ns(),
    )
