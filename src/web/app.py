"""A small read-mostly web surface for the household, served on the LAN.

Plain HTTP by IP on purpose: DNS is an extra dependency in a path whose whole point is that tapping a pot
works, and HTTPS with an internal CA greets every guest phone with a certificate warning. The token is a
capability — whoever holds the tag can water that plant — so it is scoped to actions, never to reading.
"""

import logging
import secrets
from pathlib import Path

from aiohttp import web

from src.common.constants import CareTaskType
from src.common.exceptions import DomainError
from src.common.household_calendar import HouseholdCalendar
from src.modules.plant_care.commands import RecordCareEventCommand
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase
from src.modules.plant_care.use_cases.retrieve_plant_sheet import RetrievePlantSheetUseCase
from src.web.rendering import render_plant_sheet

logger = logging.getLogger(__name__)


def build_web_app(uow_factory, household_calendar: HouseholdCalendar, settings) -> web.Application:
    application = web.Application()

    def photo_url(photo_id: int) -> str:
        return f"/photo/{photo_id}"

    async def plant_sheet(request: web.Request) -> web.Response:
        plant_id = int(request.match_info["plant_id"])
        try:
            sheet = await RetrievePlantSheetUseCase(uow=uow_factory(), household_calendar=household_calendar)(plant_id)
        except DomainError:
            raise web.HTTPNotFound(text="Немає такої рослини")
        can_act = bool(settings.WEB_ACTION_TOKEN) and _token_matches(request, settings)
        body = render_plant_sheet(sheet, photo_url, settings.BOT_DISPLAY_NAME, can_act)
        return web.Response(text=body, content_type="text/html", charset="utf-8")

    async def plant_photo(request: web.Request) -> web.FileResponse:
        photo_id = int(request.match_info["photo_id"])
        async with uow_factory() as uow:
            photo = await uow.plant_photos.retrieve(photo_id)
        if photo is None or not photo.local_path:
            raise web.HTTPNotFound()
        path = Path(photo.local_path)
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    async def record_watering(request: web.Request) -> web.Response:
        if not _token_matches(request, settings):
            raise web.HTTPForbidden(text="Потрібен ключ")
        plant_id = int(request.match_info["plant_id"])
        actor = settings.web_actor
        try:
            await RecordCareEventUseCase(
                uow=uow_factory(),
                actor=actor,
                household_calendar=household_calendar,
                recent_care_guard_hours=settings.RECENT_CARE_GUARD_HOURS,
            )(
                RecordCareEventCommand(
                    plant_id=plant_id,
                    task_type=CareTaskType.WATERING,
                    performed_at=household_calendar.now(),
                    force=True,
                )
            )
        except DomainError as error:
            logger.warning("Web watering refused for plant %s: %s", plant_id, error)
        raise web.HTTPFound(f"/p/{plant_id}?{request.query_string}")

    application.router.add_get("/p/{plant_id:\\d+}", plant_sheet)
    application.router.add_post("/p/{plant_id:\\d+}/water", record_watering)
    application.router.add_get("/photo/{photo_id:\\d+}", plant_photo)
    return application


def _token_matches(request: web.Request, settings) -> bool:
    expected = settings.WEB_ACTION_TOKEN
    # compare_digest so a wrong key cannot be found one character at a time
    return bool(expected) and secrets.compare_digest(request.query.get("k", ""), expected)


async def start_web_app(application: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(application, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=port).start()  # noqa: S104
    logger.info("Serving the household web sheets on port %s", port)
    return runner
