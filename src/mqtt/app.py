"""The mqtt assembly: each module registers what it publishes and listens to, this file only collects it."""
from src.mqtt import air_conditioner, power, room_climate
from src.mqtt.surface import ListenerRegistrar, MqttContext, MqttSurface

# one line per module, the same shape as JOB_REGISTRARS: what a module exposes on the broker, and the flag
# that switches it on, live in its own file — adding one never edits the body of this file
LISTENER_REGISTRARS: tuple[ListenerRegistrar, ...] = (
    air_conditioner.register_listeners,
    power.register_listeners,
    room_climate.register_listeners,
)


def build_mqtt_surface(context: MqttContext) -> MqttSurface:
    """Collect everything the modules expose onto one broker connection."""
    settings = context.settings
    surface = MqttSurface(
        host=settings.MQTT_HOST,
        port=settings.MQTT_PORT,
        topic_prefix=settings.MQTT_TOPIC_PREFIX,
        username=settings.MQTT_USERNAME,
        password=settings.MQTT_PASSWORD,
    )
    for register_listeners in LISTENER_REGISTRARS:
        register_listeners(surface, context)
    return surface
