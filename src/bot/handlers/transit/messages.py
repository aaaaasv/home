"""What the transit arrival card says."""


# 🚌 транспорт — the on-demand "next bus" card. transit is not usually empty, so it never pushes: /bus opens a
# self-editing card that refreshes for a short window, then freezes with a 🔄 to reopen it
TRANSIT_BUTTON_REFRESH = "🔄 Оновити"
# shown at once when 🔄 is tapped, while the feed is polled — a status banner, not a blocking wait
TRANSIT_REFRESHING = "🔄 дивлюсь…"
# the placeholder the card is born as, before the first arrival estimate lands
TRANSIT_LOOKING = "🚌 дивлюсь, де транспорт…"
# during an air raid gps is jammed, so positions are noise — say so instead of showing a wrong eta
TRANSIT_AIR_RAID = "🚨 тривога — GPS заглушено, даних нема"
TRANSIT_FEED_DOWN = "⚠️ трекінг транспорту зараз не працює"
TRANSIT_NEAREST_PREFIX = "найближчий: "
# the closest vehicle carries its distance too; the rest show only their eta, and a route with none is invisible
TRANSIT_ARRIVAL_NEAREST = "{emoji} {route} за ~{eta} хв"
TRANSIT_ARRIVAL_DISTANCE = " (~{distance} км)"
TRANSIT_ARRIVAL_ETA = "{emoji} {route} ~{eta} хв"
TRANSIT_ARRIVAL_INVISIBLE = "{emoji} {route} поки не видно"
# a quiet footer: live while the card still refreshes itself, frozen once its window closes
TRANSIT_FOOTER_LIVE = "<i>оновлюється · станом на {time}</i>"
TRANSIT_FOOTER_FROZEN = "<i>станом на {time} · 🔄 щоб оновити</i>"
