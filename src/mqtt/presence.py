"""The router's Wi-Fi events on the broker — a phone joining is how the flat learns somebody is at the door.

The events come from `presence-syslog` on the host, which turns the router's syslog into one message per
association. The router pushes the moment its radio sees the phone, so this path costs nothing in latency —
which is the entire reason it exists rather than a faster poll.
"""
from src.mqtt.surface import MqttContext, MqttSurface

PRESENCE_TOPIC = "presence/wifi"


def register_listeners(surface: MqttSurface, context: MqttContext) -> None:
    """Follow the arrivals only when something is waiting to act on them."""
    if context.handle_presence_event is None:
        return

    surface.listen_to(PRESENCE_TOPIC, context.handle_presence_event)
