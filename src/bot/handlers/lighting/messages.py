"""What the strip says when it is driven from the group instead of from the phone's home app."""

# /light — the strip's own card. the two automatic users of the strip (a red alert, somebody coming home)
# leave nothing to tap, and apple home is the only hand on it: on the night of 13/14.10 the home app could
# not be reached and the night ended with the strip pulled out of its socket
LIGHT_STRIP_ON = "💡 <b>Стрічка</b> — {percent}%"
LIGHT_STRIP_OFF = "🌑 <b>Стрічка</b> — не горить"
LIGHT_STRIP_UNREACHABLE = "🌑 Стрічка не відповідає — служба на Pi не піднялась"
LIGHT_STRIP_BUTTON_OFF = "Погасити"
LIGHT_STRIP_BUTTON_LEVEL = "{percent}%"
LIGHT_STRIP_CARD_EXPIRED = "Зробив, але ця картка застаріла — надішли /light"
