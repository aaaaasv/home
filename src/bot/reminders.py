"""The scheduler assembly: each module registers its own work, this file only collects it."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.bot.handlers.air_conditioner import jobs as air_conditioner_jobs
from src.bot.handlers.chores import jobs as chores_jobs
from src.bot.handlers.plants import jobs as plants_jobs
from src.bot.handlers.power import jobs as power_jobs
from src.bot.handlers.presence import jobs as presence_jobs
from src.bot.handlers.shopping import jobs as shopping_jobs
from src.bot.handlers.system import jobs as system_jobs
from src.bot.handlers.transit import jobs as transit_jobs
from src.bot.handlers.weather import jobs as weather_jobs
from src.bot.scheduling import JobRegistrar, SchedulerContext

# one line per module, the same shape as the router list in application.py: a module's triggers, its cadence and the
# flags that switch it on all live in its own jobs.py, so adding a module never edits the body of this file
JOB_REGISTRARS: tuple[JobRegistrar, ...] = (
    plants_jobs.register_jobs,
    weather_jobs.register_jobs,
    air_conditioner_jobs.register_jobs,
    power_jobs.register_jobs,
    transit_jobs.register_jobs,
    system_jobs.register_jobs,
    presence_jobs.register_jobs,
    shopping_jobs.register_jobs,
    chores_jobs.register_jobs,
)


def build_scheduler(context: SchedulerContext) -> AsyncIOScheduler:
    """Collect every module's scheduled work into one scheduler."""
    scheduler = AsyncIOScheduler(timezone=context.settings.timezone)
    for register_jobs in JOB_REGISTRARS:
        register_jobs(scheduler, context)
    return scheduler
