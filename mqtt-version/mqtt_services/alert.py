"""Alert Service (MQTT version).

Subscribes to processed/readings and hands every message to the shared
AlertSink (duplicates flagged, alerts counted once per msg_id). With QoS 1/2
the message is acknowledged only after it has been recorded.

Management endpoints (/health, /ready, /stats) on MGMT_PORT.
"""

import logging
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from common.alerting import AlertSink
from common.config import env_int, env_str
from common.logsetup import setup_logging
from common.messages import InvalidMessage, ProcessedEvent, decode
from common.results import write_json
from mqtt_services import mgmt
from mqtt_services.mqttconf import PROCESSED_TOPIC, MqttSettings, make_client, start, subscribe_options
from mqtt_services.runtime import ConnectionState, wait_for_shutdown

log = logging.getLogger("alert")


def main() -> None:
    setup_logging("alert")
    settings = MqttSettings.from_env()
    results_dir = Path(env_str("RESULTS_DIR", "results-local"))
    sink = AlertSink(results_dir)
    state = ConnectionState()
    client = make_client("alert-service", settings, manual_ack=True)

    def on_connect(client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.warning("connect refused: %s", reason_code)
            return
        state.connected = True
        state.connects += 1
        state.session_resumed += int(flags.session_present)
        client.subscribe(PROCESSED_TOPIC, options=subscribe_options(settings))
        log.info("connected (session_present=%s), subscribing to %s at QoS %d",
                 flags.session_present, PROCESSED_TOPIC, settings.qos)

    def on_subscribe(client, userdata, mid, reason_codes, properties) -> None:
        state.subscribed = all(not rc.is_failure for rc in reason_codes)

    def on_disconnect(client, userdata, flags, reason_code, properties) -> None:
        state.connected = state.subscribed = False
        state.disconnects += 1
        log.warning("disconnected: %s", reason_code)

    def on_message(client, userdata, message: mqtt.MQTTMessage) -> None:
        recv_mono_ns = time.monotonic_ns()
        recv_wall_ns = time.time_ns()
        try:
            event = ProcessedEvent.from_dict(decode(message.payload))
        except InvalidMessage as exc:
            sink.reject(str(exc))
        else:
            sink.on_event(event, recv_mono_ns, recv_wall_ns)
        client.ack(message.mid, message.qos)   # after recording; no-op for QoS 0

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    mgmt.serve(env_int("MGMT_PORT", 8000), state.ready, lambda: {**sink.stats(), **state.as_dict()})
    log.info("broker %s:%d, qos=%d, writing results to %s", settings.host, settings.port, settings.qos, results_dir)
    start(client, settings)

    wait_for_shutdown()
    client.disconnect()
    client.loop_stop()
    stats = sink.stats()
    sink.close()
    write_json(results_dir / "alert_summary.json",
               {"architecture": "mqtt", **stats, **state.as_dict(), "mqtt": settings.as_dict()})
    log.info("stopped: %s", stats)


if __name__ == "__main__":
    main()
