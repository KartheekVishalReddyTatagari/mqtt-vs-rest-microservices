"""Business logic of the Processing Service, shared by both versions."""

import time

from common.messages import ProcessedEvent, Reading


def process(reading: Reading, threshold: float, received_mono_ns: int) -> ProcessedEvent:
    """Check a reading against the threshold (strictly greater = alert).

    Every reading is forwarded, not only alerts, so end-to-end latency and
    delivery can be measured for every message. The Alert Service acts on
    is_alert.
    """
    is_alert = reading.value > threshold
    return ProcessedEvent(
        schema_version=reading.schema_version,
        run_id=reading.run_id,
        msg_id=reading.msg_id,
        sensor_id=reading.sensor_id,
        seq=reading.seq,
        event_ts_ns=reading.event_ts_ns,
        sent_mono_ns=reading.sent_mono_ns,
        value=reading.value,
        unit=reading.unit,
        is_alert=is_alert,
        threshold=threshold,
        processing_received_mono_ns=received_mono_ns,
        processing_completed_mono_ns=time.monotonic_ns(),
    )
