# every module's topic name as the family reads it. the TOPIC_TITLE defaults in config.py must spell the same,
# because a topic that was deleted is recreated under exactly that name
MODULE_TITLES = {
    "plants": "🪴 рослини",
    "shopping": "🛒 шо треба",
    "places": "📍 куди сходити",
    "chores": "📋 справи",
    "weather": "❄️ клімат",
    "power": "⚡ світло",
    "transit": "🚌 транспорт",
    "assistant": "🤖 спитати",
    "system": "🩺 сервіс",
}

# what each module's topic answers to, keyed by the module's own MODULE_NAME — the one text that /help, /start
# and the full welcome are all built from
MODULE_HELP = {
    "plants": (
        "/list — усі рослини\n"
        "/add — додати рослину\n"
        "/today — що треба зробити сьогодні\n"
        "/history — останні дії\n"
        "або просто напиши питання про рослину — «чому жовтіє листя Тігла» — і я відповім з історії її поливів"
    ),
    "shopping": (
        "просто напиши, що купити\n"
        "/list — список покупок\n"
        "/add — додати покупку\n"
        "/later — покупка на колись\n"
        "/track — стежити за ціною (лінк hotline)"
    ),
    "places": "напиши місце, куди хочеться\n/list — список місць",
    "chores": "напиши, що треба зробити (з датою — «до 31.07»)\n/list — список справ",
    "weather": "/climate — клімат удома по кімнатах\n/ac — кондиціонер\nщоранку — погода",
    "power": (
        "/eco — EcoFlow Delta 2: заряд і керування\n"
        "/reserve — резерв живлення: скільки тримає кожен шар\n"
        "/conserve — режим зберігання станції\n"
        "графік відключень зʼявляється сам, коли є"
    ),
    "transit": "/bus або /транспорт — коли наступний 3 / 9К / 69 з нашої зупинки",
    "assistant": (
        "просто напиши питання про дім — метро, рослини, «коли вчора була тривога», "
        "«о котрій ми вчора прийшли», «чому вночі горіло світло»"
    ),
    "system": "/pi — стан Raspberry Pi\nпро розряджену батарею датчика напишу сам",
}

# the commands each module's own router answers to. wrong_topic reads this to tell «ця команда з іншого топіка»
# from «тут такої команди немає», so it has to move together with the routers
MODULE_COMMANDS = {
    "plants": ("list", "add", "today", "history"),
    "shopping": ("list", "add", "later", "track"),
    "places": ("list",),
    "chores": ("list",),
    "weather": ("climate", "ac"),
    "power": ("eco", "reserve", "conserve"),
    "transit": ("bus", "транспорт"),
    "system": ("pi",),
}


def render_module_help(module_name: str) -> str:
    return f"<b>{MODULE_TITLES[module_name]}</b>\n{MODULE_HELP[module_name]}"


WELCOME = (
    "🏠 <b>Домашній бот</b>\n\n"
    "Кожен розділ — у своєму топіку, і команди там означають своє. "
    "У будь-якому топіку /help покаже, що вміє саме він.\n\n"
    + "\n".join(f"<blockquote expandable>{render_module_help(module_name)}</blockquote>" for module_name in MODULE_HELP)
    + "\n\n/cancel — скасувати поточну дію"
)
WRONG_TOPIC = "Ця команда працює в іншому топіку:\n\n" + "\n".join(
    f"<b>{MODULE_TITLES[module_name]}</b> — " + ", ".join(f"/{command}" for command in commands)
    for module_name, commands in MODULE_COMMANDS.items()
)
# said inside a module's own topic where the command does not exist — pointing to another topic would be true
# and useless there, so the topic's own help follows
NO_SUCH_COMMAND_HERE = "У цьому топіку команди /{command} немає.\n\n{topic_help}\n\n/{command} працює тут: {places}."

# /help and /start show only the current topic's commands when sent inside a module topic (resolved via the
# forum_topics table); in General they fall back to the full WELCOME
TOPIC_HELP = {module_name: render_module_help(module_name) for module_name in MODULE_HELP}
ONLY_IN_THE_GROUP = "Я працюю в сімейній групі — кожен розділ у своєму топіку. Пиши команди там."
STALE_BUTTON = "Ця кнопка вже застара 🙃 Напиши /help — там усе, що вміє цей топік."
PRIVATE_WELCOME = "🏠 <b>Домашній бот</b>\n\nЯ працюю в сімейній групі — кожен розділ у своєму топіку. Пиши команди там."

# item and place menus share the same edit/remove/back verbs
BACK_BUTTON = "← Назад"

# the error router is the last-resort net under every module, so its wording must fit any of them: it once said
# «не знаходжу цю рослину» to someone whose shopping item had just been bought from under them
NOT_FOUND = "Не знаходжу цього запису 🤔"
ALREADY_EXISTS = "Такий запис уже є."
CONFLICT = "Так не вийде — стан змінився."
INVALID_INPUT = "Некоректні дані."
UNEXPECTED_ERROR = "Щось пішло не так 😕 Спробуй ще раз."
