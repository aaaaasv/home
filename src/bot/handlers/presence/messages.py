"""What presence says when the house empties."""


PRESENCE_EVERYONE_LEFT_AC_ON = "🏠 Здається, всі пішли, а кондиціонер працює"

PRESENCE_FACTS_TITLE = (
    "Хто приходив і йшов (за журналом Wi-Fi роутера). Телефон у різних мережах Wi-Fi має різні адреси, тож «зник "
    "і за кілька секунд зайшов» майже завжди один і той самий телефон, який перемкнувся між діапазонами:"
)
PRESENCE_FACTS_EVENTS = {"joined": "зайшов у Wi-Fi", "left": "зник із Wi-Fi"}
# what the welcome light decided about a join, keyed by the outcome the arrival rule wrote down
PRESENCE_FACTS_OUTCOMES = {
    "raised": "підсвітку в передпокої увімкнув",
    "hop": "підсвітку не вмикав: телефон був поза мережею лише кілька хвилин",
    "daylight": "підсвітку не вмикав: надворі було світло",
    "somebody_home": "підсвітку не вмикав: хтось уже був удома",
    "light_on": "підсвітку не вмикав: світло вже горіло",
    "no_departure": "підсвітку не вмикав: вихід із дому не було зафіксовано",
    "router_silent": "підсвітку не вмикав: роутер не відповів",
    "never_empty": "підсвітку не вмикав: у квартирі весь цей час хтось лишався",
}
