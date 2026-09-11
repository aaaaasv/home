"""What the Pi says about its own health."""


SYSTEM_HEALTH_ALERT_TITLE = "🩺 <b>Raspberry Pi</b>"
SYSTEM_HEALTH_UNDERVOLTAGE = "⚡ Просідає живлення — перевір блок і кабель"
SYSTEM_HEALTH_TEMPERATURE = "🌡 Перегрівається — {temperature}°"
SYSTEM_HEALTH_DISK = "💾 Диск заповнено на {percent}%"

PI_STATUS_TITLE = "🩺 <b>Raspberry Pi</b>"
PI_STATUS_TEMPERATURE = "🌡 {temperature}°"
PI_STATUS_POWER_OK = "⚡ живлення в нормі"
PI_STATUS_POWER_LOW = "⚡ просідає живлення"
PI_STATUS_DISK = "💾 диск: {percent}%"
PI_STATUS_UNAVAILABLE = "🩺 Дані Pi зараз недоступні."

# the media server's disks, watched over the same http agent that serves its battery. this is the rarest push
# in the house — a healthy drive never triggers it — so it names the disk and says what was found, nothing more
MEDIA_SERVER_DISK_TITLE = "💽 <b>Медіасервер</b>"
MEDIA_SERVER_DISK_FAILED = "❌ {model} — SMART каже, що диск помирає"
MEDIA_SERVER_DISK_REALLOCATED = "⚠️ {model} — перерозподілених секторів: {value}"
MEDIA_SERVER_DISK_PENDING = "⚠️ {model} — секторів в очікуванні: {value}"
MEDIA_SERVER_DISK_UNCORRECTABLE = "⚠️ {model} — невиправних помилок: {value}"
MEDIA_SERVER_DISK_WORN = "⌛ {model} — витрачено {value}% ресурсу"
MEDIA_SERVER_DISK_SPARE = "⌛ {model} — резервних блоків лишилось {value}%"
