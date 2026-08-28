from aiogram import Router

from src.bot.handlers.plants import add_plant, ask, care, edit_plant, photos, plant_list, schedules

PLANTS_MODULE_NAME = "plants"

router = Router(name="plants")
router.include_routers(
    add_plant.router,
    plant_list.router,
    care.router,
    photos.router,
    schedules.router,
    edit_plant.router,
    # last: it takes any text no flow claimed
    ask.router,
)
