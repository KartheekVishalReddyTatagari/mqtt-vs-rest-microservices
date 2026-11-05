"""Processing Service (MQTT version).

Subscribes to sensors/+/readings, applies the same shared threshold logic as
the REST version, and publishes every result to processed/readings.

Acknowledge after forwarding: with QoS 1/2 the incoming message is
acknowledged only once the broker has accepted the outgoing message (PUBACK
for QoS 1, PUBCOMP for QoS 2). If this service dies in between, the broker
redelivers the incoming message after the restart: at-least-once end to end,
so duplicates are possible and are counted at the Alert Service. The two
broker exchanges are not one atomic transaction.

Management endpoints (/health, /ready, /stats) on MGMT_PORT, outside the
measured data path.
"""

import logging
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from common import logic
from common.config import env_float, env_int, env_str
from common.logsetup import setup_logging
from common.messages import InvalidMessage, ProcessedEvent, Reading, decode, encode
from common.results import ProcessingRecorder, write_json
from mqtt_services import mgmt
from mqtt_services.mqttconf import (PROCESSED_TOPIC, QOS_ACK_NAME, READINGS_SUBSCRIPTION, MqttSettings,
                                    make_client, start, subscribe_options)
from mqtt_services.runtime import ConnectionState, wait_for_shutdown

log = logging.getLogger("processing")


def main() -> None:
    setup_logging("processing")
    settings = MqttSettings.from_env()
    threshold = env_float("THRESHOLD", 30.0)
    results_dir = Path(env_str("RESULTS_DIR", "results-local"))
    recorder = ProcessingRecorder(results_dir)
    state = ConnectionState()
    # outgoing mid -> (incoming mid, incoming qos, event); filled and drained on paho's thread
    pending: dict[int, tuple[int, int, ProcessedEvent]] = {}
    lock = threading.Lock()
    client = make_client("processing-service", settings, manual_ack=True)

    def on_connect(client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("connect refused: %s", reason_code)
            return
        state.connected = True
        state.connects += 1
        state.session_resumed += int(flags.session_present)
        client.subscribe(READINGS_SUBSCRIPTION, options=subscribe_options(settings))
        log.info("connected (session_present=%s), subscribing to %s at QoS %d",
                 flags.session_present, READINGS_SUBSCRIPTION, settings.qos)

    def on_subscribe(client, userdata, mid, reason_codes, properties) -> None:
        state.subscribed = all(not rc.is_failure for rc in reason_codes)

    def on_disconnect(client, userdata, flags, reason_code, properties) -> None:
        state.connected = state.subscribed = False
        state.disconnects += 1
        log.warning("disconnected: %s", reason_code)

    def on_message(client, userdata, message: mqtt.MQTTMessage) -> None:
        received = time.monotonic_ns()
        try:
            reading = Reading.from_dict(decode(message.payload))
        except InvalidMessage as exc:
            recorder.reject(str(exc))
            client.ack(message.mid, message.qos)   # never redeliver a malformed message
            return
        event = logic.process(reading, threshold, received)
        info = client.publish(PROCESSED_TOPIC, encode(event.to_dict()), qos=settings.qos)
        if settings.qos == 0 and info.rc != mqtt.MQTT_ERR_SUCCESS:
            recorder.record(event, False, 1, mqtt.error_string(info.rc), time.monotonic_ns())
            return
        # on_publish for this mid runs later on this same thread, so registering here is race-free
        with lock:
            pending[info.mid] = (message.mid, message.qos, event)

    def on_publish(client, userdata, mid, reason_code, properties) -> None:
        with lock:
            entry = pending.pop(mid, None)
        if entry is None:
            return
        in_mid, in_qos, event = entry
        ok = not reason_code.is_failure
        recorder.record(event, ok, 1, QOS_ACK_NAME[settings.qos] if ok else str(reason_code),
                        time.monotonic_ns())
        if in_qos > 0:
            client.ack(in_mid, in_qos)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.on_publish = on_publish

    mgmt.serve(env_int("MGMT_PORT", 8000), state.ready,
               lambda: {**recorder.stats(), **state.as_dict(), "pending_forwards": len(pending)})
    log.info("broker %s:%d, threshold=%.2f, qos=%d", settings.host, settings.port, threshold, settings.qos)
    start(client, settings)

    wait_for_shutdown()
    client.disconnect()
    client.loop_stop()
    stats = recorder.stats()
    recorder.close()
    write_json(results_dir / "processing_summary.json",
               {"architecture": "mqtt", **stats, **state.as_dict(), "mqtt": settings.as_dict()})
    log.info("stopped: %s", stats)


if __name__ == "__main__":
    main()
