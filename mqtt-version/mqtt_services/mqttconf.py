"""MQTT settings, topics and client construction, shared by the three MQTT services.

Protocol MQTT 5.0. Every service uses a stable client id and a persistent
session (clean_start=False, session expiry SESSION_EXPIRY_S), so the broker
keeps its subscriptions and queues QoS 1/2 messages while it is offline.
Each run starts with a fresh broker (the runner removes the broker volume),
so no session survives from one run into the next.

Delivery behaviour of paho-mqtt 2.2.0 that matters for the results:
- QoS 0: publish() while disconnected returns MQTT_ERR_NO_CONN and the
  message is dropped.
- QoS 1/2: publish() while disconnected keeps the message in the client's
  in-memory queue and sends it after reconnecting.
- Receiving QoS 1 with manual_ack=True: PUBACK is sent only when the
  application calls ack(), so a crash before that means redelivery.
- Receiving QoS 2: paho sends PUBREC before the application sees the message
  and keeps that state only in memory. A process restart between PUBREC and
  PUBREL loses the message (paho acknowledges the unknown PUBREL to avoid
  hanging). QoS 2 is exactly-once per MQTT exchange, not across a crash.
"""

import socket
from dataclasses import asdict, dataclass

import paho.mqtt
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties
from paho.mqtt.subscribeoptions import SubscribeOptions

from common.config import env_float, env_int, env_str

READINGS_SUBSCRIPTION = "sensors/+/readings"
PROCESSED_TOPIC = "processed/readings"
QOS_ACK_NAME = {0: "sent", 1: "puback", 2: "pubcomp"}


def readings_topic(sensor_id: str) -> str:
    return f"sensors/{sensor_id}/readings"


@dataclass(frozen=True)
class MqttSettings:
    host: str
    port: int
    qos: int
    keepalive_s: int
    session_expiry_s: int
    max_inflight: int

    @classmethod
    def from_env(cls) -> "MqttSettings":
        qos = env_int("MQTT_QOS", 1)
        if qos not in (0, 1, 2):
            raise ValueError("MQTT_QOS must be 0, 1 or 2")
        return cls(
            host=env_str("MQTT_HOST", "127.0.0.1"),
            port=env_int("MQTT_PORT", 1883),
            qos=qos,
            keepalive_s=env_int("MQTT_KEEPALIVE_S", 10),
            session_expiry_s=env_int("SESSION_EXPIRY_S", 300),
            max_inflight=env_int("MQTT_MAX_INFLIGHT", 100),
        )

    def as_dict(self) -> dict:
        return {"protocol": "MQTT 5.0", "client": f"paho-mqtt {paho.mqtt.__version__}", **asdict(self),
                "clean_start": False, "retain": False, "tcp_nodelay": True}


def make_client(client_id: str, settings: MqttSettings, manual_ack: bool = False) -> mqtt.Client:
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=client_id,
        protocol=mqtt.MQTTv5,
        manual_ack=manual_ack,
    )
    client.max_inflight_messages_set(settings.max_inflight)
    client.max_queued_messages_set(0)          # unlimited client-side queue while disconnected
    client.reconnect_delay_set(min_delay=1, max_delay=2)
    client.on_socket_open = _set_nodelay
    return client


def _set_nodelay(client: mqtt.Client, userdata, sock) -> None:
    """Disable Nagle's algorithm, as asyncio/aiohttp do for the REST stack.

    paho-mqtt leaves Nagle on. Small packets (PUBACK, PUBREC, ...) then wait
    for earlier data to be acknowledged, which added ~10 ms to QoS 1/2 p95
    latency in testing and would have biased the comparison against MQTT.
    """
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except (OSError, AttributeError):
        pass


def start(client: mqtt.Client, settings: MqttSettings) -> None:
    """Connect in the background; paho retries until the broker answers."""
    properties = Properties(PacketTypes.CONNECT)
    properties.SessionExpiryInterval = settings.session_expiry_s
    client.connect_async(settings.host, settings.port, keepalive=settings.keepalive_s,
                         clean_start=False, properties=properties)
    client.loop_start()


def subscribe_options(settings: MqttSettings) -> SubscribeOptions:
    return SubscribeOptions(qos=settings.qos)
