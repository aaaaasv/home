"""How the journal of air alert levels reads to a model that answers questions about it."""

AIR_ALERT_FACTS_TITLE = (
    "Тривоги в нашому районі (зміни рівня за журналом; світло в передпокої бот піднімає лише на початку "
    "червоного рівня і лише якщо воно не горіло):"
)
AIR_ALERT_FACTS_LEVELS = {
    "none": "відбій",
    "yellow": "жовтий рівень — попередження про загрозу",
    "red": "червоний рівень — тривога",
}
AIR_ALERT_FACTS_TRANSITIONS = {
    "raised": "початок червоної тривоги",
    "cleared": "кінець червоної тривоги",
    "unchanged": "",
}
AIR_ALERT_FACTS_SOURCES = {"socket": "від сокета", "poll": "від опитування"}
