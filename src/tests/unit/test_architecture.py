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

# aiogram is the delivery framework, apscheduler schedules delivery, sqlalchemy is the database. a domain module
# that imports one of them can no longer be tested or replaced without it
DELIVERY_AND_STORAGE_LIBRARIES = {"aiogram", "apscheduler", "sqlalchemy", "alembic"}


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

    def test_no_domain_module_imports_the_delivery_framework_or_the_database(self):
        offenders = {
            str(path): sorted(imported_root_packages(path) & DELIVERY_AND_STORAGE_LIBRARIES)
            for path in sorted(DOMAIN_ROOT.rglob("*.py"))
            if imported_root_packages(path) & DELIVERY_AND_STORAGE_LIBRARIES
        }

        self.assertEqual(offenders, {})
