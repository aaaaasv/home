"""What the air conditioner card says."""

from src.modules.air_conditioner.domain import AirConditionerFanSpeed, AirConditionerMode

AIR_CONDITIONER_TITLE = "❄️ <b>Кондиціонер</b> — {room}"
# a verb phrase says what the machine is doing, so nobody has to work out which number is the target
AIR_CONDITIONER_STATE_LINES: dict[AirConditionerMode, str] = {
    AirConditionerMode.COOL: "охолоджує до {target}°",
    AirConditionerMode.DRY: "осушує повітря · {target}°",
    # fan moves air and ignores the setpoint, so naming a target here would be a small lie
    AirConditionerMode.FAN: "вентиляція · без охолодження",
    AirConditionerMode.AUTO: "авто · {target}°",
    AirConditionerMode.HEAT: "гріє до {target}°",
}
AIR_CONDITIONER_STATE_OFF = "вимкнено · було {target}°"
AIR_CONDITIONER_ROOM_TEMPERATURE = "у кімнаті {temperature}°"
AIR_CONDITIONER_ROOM_TEMPERATURE_WITH_HUMIDITY = "у кімнаті {temperature}° · вологість {humidity}%"
AIR_CONDITIONER_OPEN_WINDOWS_INSTEAD = "🪟 надворі сухіше — краще відчинити вікна"
AIR_CONDITIONER_ALREADY_OFF = "Вже вимкнено"
AIR_CONDITIONER_TURNED_OFF = "🌬 Кондиціонер вимкнено"
AIR_CONDITIONER_CARD_EXPIRED = "Готово, але ця картка застаріла — надішли /ac"
AIR_CONDITIONER_WORKING = "⏳ виконую…"
AIR_CONDITIONER_LONG_RUN = "❄️ Кондиціонер працює вже {hours} год"
AIR_CONDITIONER_LONG_RUN_WITH_ROOM = "❄️ Кондиціонер працює вже {hours} год · у кімнаті {temperature}°"
AIR_CONDITIONER_UPDATED_AT = "<i>оновлено {time}</i>"
AIR_CONDITIONER_UNREACHABLE = "❄️ Кондиціонер не відповідає. Перевір, чи він під напругою."
AIR_CONDITIONER_MODE_LABELS: dict[AirConditionerMode, str] = {
    AirConditionerMode.AUTO: "авто",
    AirConditionerMode.COOL: "холод",
    AirConditionerMode.DRY: "осушення",
    AirConditionerMode.FAN: "вентиляція",
    AirConditionerMode.HEAT: "тепло",
}
# the icons the family already reads off the physical remote; the active mode swaps its icon for a tick,
# because a middle dot is not visibly "selected" at button size on a phone
AIR_CONDITIONER_MODE_ICONS: dict[AirConditionerMode, str] = {
    AirConditionerMode.COOL: "❄️",
    AirConditionerMode.DRY: "💧",
    AirConditionerMode.FAN: "💨",
}
AIR_CONDITIONER_ACTIVE_MODE_MARKER = "✓"
AIR_CONDITIONER_BUTTON_TURN_ON = "Увімкнути"
AIR_CONDITIONER_BUTTON_TURN_OFF = "Вимкнути"
AIR_CONDITIONER_BUTTON_WARMER = "+1°"
AIR_CONDITIONER_BUTTON_COOLER = "−1°"
AIR_CONDITIONER_BUTTON_REFRESH = "↻"
AIR_CONDITIONER_FAN_SPEED_LABELS: dict[AirConditionerFanSpeed, str] = {
    AirConditionerFanSpeed.AUTO: "авто",
    AirConditionerFanSpeed.LOW: "низька",
    AirConditionerFanSpeed.MEDIUM: "середня",
    AirConditionerFanSpeed.HIGH: "висока",
}
AIR_CONDITIONER_BUTTON_FAN = "🌀 обдув: {speed}"
# each toggle shows its own icon when off and the shared tick when on, so "on" reads the same as a picked mode
AIR_CONDITIONER_BUTTON_TURBO = "турбо"
AIR_CONDITIONER_BUTTON_TURBO_ICON = "🚀"
AIR_CONDITIONER_BUTTON_QUIET = "тихо"
AIR_CONDITIONER_BUTTON_QUIET_ICON = "🔇"
AIR_CONDITIONER_BUTTON_XFAN = "просушка"
AIR_CONDITIONER_BUTTON_XFAN_ICON = "💧"
# surfaced in the card text only while active, because each of these visibly changes how the unit behaves
AIR_CONDITIONER_BADGE_TURBO = "🚀 турбо"
AIR_CONDITIONER_BADGE_QUIET = "🔇 тихо"
AIR_CONDITIONER_BADGE_XFAN = "💧 просушка"
