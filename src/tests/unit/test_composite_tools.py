import unittest

from src.bot.services.composite_tools import CompositeTools


class StubToolset:
    def __init__(self, names: list[str]):
        self.names = names
        self.calls: list[tuple[str, dict]] = []

    @property
    def definitions(self) -> list[dict]:
        return [{"name": name} for name in self.names]

    async def run(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return f"{name} answered"


class CompositeToolsTestCase(unittest.IsolatedAsyncioTestCase):
    """One toolbox out of several, so a module can offer the assistant tools without the assistant importing it."""

    def test_definitions_offers_every_toolsets_tools_in_the_order_they_were_composed(self):
        tools = CompositeTools([StubToolset(["grid_log"]), StubToolset(["update_plant_card"])])

        self.assertEqual(tools.definitions, [{"name": "grid_log"}, {"name": "update_plant_card"}])

    async def test_run_sends_the_call_to_the_toolset_that_offers_that_tool(self):
        household, plants = StubToolset(["grid_log"]), StubToolset(["update_plant_card"])
        tools = CompositeTools([household, plants])

        answer = await tools.run("update_plant_card", {"plant": "Принцеса"})

        self.assertEqual(answer, "update_plant_card answered")
        self.assertEqual(household.calls, [])
        self.assertEqual(plants.calls, [("update_plant_card", {"plant": "Принцеса"})])

    async def test_run_with_a_tool_no_toolset_offers_says_so_rather_than_raising(self):
        tools = CompositeTools([StubToolset(["grid_log"])])

        self.assertEqual(await tools.run("open_the_window", {}), "Такого інструмента немає.")
