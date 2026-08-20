"""A small read-mostly web surface for the household, served on the LAN.

Plain HTTP on purpose: no public certificate authority will issue for `garden.lan`, and an internal CA
greets every guest phone with a warning instead. Reading is open to anyone on the network, which is the
point, and the one action that spends water asks for a confirming tap rather than a secret.
"""

import logging
from pathlib import Path

from aiohttp import web

from src.common.constants import CareTaskType
from src.common.exceptions import DomainError
from src.common.household_calendar import HouseholdCalendar
from src.modules.plant_care.commands import RecordCareEventCommand
from src.modules.plant_care.use_cases.record_care_event import RecordCareEventUseCase
from src.modules.plant_care.use_cases.retrieve_drawer import RetrieveDrawerUseCase
from src.modules.plant_care.use_cases.retrieve_plant_sheet import RetrievePlantSheetUseCase
from src.web.rendering import ACTIONABLE_TASKS as WEB_ACTIONABLE_TASKS
from src.web.rendering import render_drawer, render_plant_sheet

logger = logging.getLogger(__name__)


def build_web_app(uow_factory, household_calendar: HouseholdCalendar, settings) -> web.Application:
    application = web.Application()

    def photo_url(photo_id: int) -> str:
        return f"/photo/{photo_id}"

    async def drawer(request: web.Request) -> web.Response:
        entries = await RetrieveDrawerUseCase(uow=uow_factory(), household_calendar=household_calendar)()
        body = render_drawer(entries, photo_url, settings.BOT_DISPLAY_NAME)
        return web.Response(text=body, content_type="text/html", charset="utf-8")

    async def plant_sheet(request: web.Request) -> web.Response:
        reference = request.match_info["reference"]
        try:
            sheet = await RetrievePlantSheetUseCase(uow=uow_factory(), household_calendar=household_calendar)(reference)
        except DomainError:
            raise web.HTTPNotFound(text="Немає такої рослини")
        entries = await RetrieveDrawerUseCase(uow=uow_factory(), household_calendar=household_calendar)()
        body = render_plant_sheet(sheet, photo_url, settings.BOT_DISPLAY_NAME, entries)
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

    async def record_care(request: web.Request) -> web.Response:
        reference = request.match_info["reference"]
        try:
            task_type = CareTaskType(request.match_info["task"])
        except ValueError:
            raise web.HTTPNotFound()
        if task_type not in WEB_ACTIONABLE_TASKS:
            raise web.HTTPNotFound()
        async with uow_factory() as uow:
            plant = await uow.plants.retrieve_active_by_slug(reference)
            if plant is None and reference.isdigit():
                plant = await uow.plants.retrieve_active(int(reference))
        if plant is None:
            raise web.HTTPNotFound()
        try:
            await RecordCareEventUseCase(
                uow=uow_factory(),
                actor=settings.web_actor,
                household_calendar=household_calendar,
                recent_care_guard_hours=settings.RECENT_CARE_GUARD_HOURS,
            )(
                RecordCareEventCommand(
                    plant_id=plant.id,
                    task_type=task_type,
                    performed_at=household_calendar.now(),
                    force=True,
                )
            )
        except DomainError as error:
            logger.warning("Web %s refused for plant %s: %s", task_type.value, plant.id, error)
        raise web.HTTPFound(f"/p/{reference}")

    application.router.add_get("/", drawer)
    application.router.add_get("/p/{reference:[a-z0-9-]+}", plant_sheet)
    application.router.add_post("/p/{reference:[a-z0-9-]+}/care/{task:[a-z]+}", record_care)
    application.router.add_get("/photo/{photo_id:\\d+}", plant_photo)
    return application


async def start_web_app(application: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(application, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=port).start()  # noqa: S104
    logger.info("Serving the household web sheets on port %s", port)
    return runner
