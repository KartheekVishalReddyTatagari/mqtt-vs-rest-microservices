import socket

import pytest

from mqtt_services.mqttconf import (READINGS_SUBSCRIPTION, MqttSettings, _set_nodelay, make_client,
                                    readings_topic)


def test_topics_match_the_subscription():
    assert readings_topic("sensor-007") == "sensors/sensor-007/readings"
    assert READINGS_SUBSCRIPTION == "sensors/+/readings"


def test_qos_must_be_0_1_or_2(monkeypatch):
    monkeypatch.setenv("MQTT_QOS", "3")
    with pytest.raises(ValueError):
        MqttSettings.from_env()


def test_settings_record_the_session_and_socket_choices(monkeypatch):
    monkeypatch.setenv("MQTT_QOS", "2")
    described = MqttSettings.from_env().as_dict()
    assert described["qos"] == 2 and described["protocol"] == "MQTT 5.0"
    assert described["clean_start"] is False and described["tcp_nodelay"] is True


def test_client_disables_nagle_on_its_socket():
    client = make_client("test", MqttSettings("localhost", 1883, 1, 10, 300, 100))
    assert client.on_socket_open is _set_nodelay
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _set_nodelay(client, None, sock)
        assert sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) != 0
    finally:
        sock.close()
