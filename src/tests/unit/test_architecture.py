import ast
import importlib
import pathlib
import unittest

from src.bot.reminders import JOB_REGISTRARS

HANDLERS_ROOT = pathlib.Path("src/bot/handlers")
DELIVERY_ROOT = pathlib.Path("src/bot")
DOMAIN_ROOT = pathlib.Path("src/modules")

# the composition root is allowed to know every module — that is its whole job. every other shared delivery file
# must stay module-blind, or adding a module means editing it and the four god-files grow back
COMPOSITION_ROOT = {"application.py", "dependencies.py", "reminders.py", "scheduling.py"}

# everything that reaches outside the process: the delivery framework, the scheduler, the database, and the http
# and protobuf clients. a domain module importing any of them can no longer be tested or replaced without it, and
# a vendor changing its payload shape starts reaching into the domain
INFRASTRUCTURE_LIBRARIES = {"aiogram", "apscheduler", "sqlalchemy", "alembic", "aiohttp", "google"}


def imported_root_packages(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    packages: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            packages.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            packages.add(node.module.split(".")[0])
    return packages


def imported_handler_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src.bot.handlers."):
            modules.add(node.module.split(".")[3])
        elif isinstance(node, ast.Import):
            modules.update(
                alias.name.split(".")[3] for alias in node.names if alias.name.startswith("src.bot.handlers.")
            )
    return modules


class SchedulingTestCase(unittest.TestCase):
    """
    Keeps the scheduler an assembly point rather than a place where a module's cadence can quietly settle.

    a jobs.py that nobody collects is a feature that silently never runs, which is exactly how a scheduled
    module dies unnoticed.
    """

    def test_every_module_that_schedules_work_is_collected_by_the_scheduler(self):
        modules_with_jobs = sorted(path.parent.name for path in HANDLERS_ROOT.glob("*/jobs.py"))

        registrars = {
            getattr(importlib.import_module(f"src.bot.handlers.{module}.jobs"), "register_jobs", None)
            for module in modules_with_jobs
        }

        self.assertEqual(registrars, set(JOB_REGISTRARS))

    def test_no_module_schedules_work_outside_its_own_jobs_file(self):
        schedulers = sorted(
            str(path)
            for path in HANDLERS_ROOT.rglob("*.py")
            if path.name != "jobs.py" and "add_job" in path.read_text()
        )

        self.assertEqual(schedulers, [])


class BehaviourCoverageTestCase(unittest.TestCase):
    """
    Keeps at least one test driving updates through the real dispatcher.

    the delivery layer went months with none, and the cost was invisible: a handler could take a parameter
    nothing injects and 652 tests stayed green while the flow was dead in the group.
    """

    def test_some_test_drives_an_update_through_the_dispatcher(self):
        drivers = sorted(
            str(path) for path in pathlib.Path("src/tests").rglob("*.py") if "feed_update" in path.read_text()
        )

        self.assertNotEqual(drivers, [])


class LayerBoundariesTestCase(unittest.TestCase):
    """
    Guards the two rules that would let the delivery layer collapse back into cross-module god-files.

    both regressions are invisible in review: one import in a shared file is how src/bot/errors.py came to answer
    «не знаходжу цю рослину» to someone whose shopping item had gone.
    """

    def test_no_shared_delivery_file_outside_the_composition_root_knows_a_module(self):
        offenders = {
            path.name: sorted(imported_handler_modules(path))
            for path in sorted(DELIVERY_ROOT.glob("*.py"))
            if path.name not in COMPOSITION_ROOT and imported_handler_modules(path)
        }

        self.assertEqual(offenders, {})

    def test_no_shared_delivery_service_knows_a_module(self):
        offenders = {
            path.name: sorted(imported_handler_modules(path))
            for path in sorted((DELIVERY_ROOT / "services").glob("*.py"))
            if imported_handler_modules(path)
        }

        self.assertEqual(offenders, {})

    def test_no_domain_module_reaches_outside_the_process(self):
        offenders = {
            str(path): sorted(imported_root_packages(path) & INFRASTRUCTURE_LIBRARIES)
            for path in sorted(DOMAIN_ROOT.rglob("*.py"))
            if imported_root_packages(path) & INFRASTRUCTURE_LIBRARIES
        }

        self.assertEqual(offenders, {})
