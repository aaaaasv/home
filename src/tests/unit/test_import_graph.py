import subprocess
import sys
import unittest


class ImportGraphTestCase(unittest.TestCase):
    """
    Imports the entrypoint in a fresh interpreter, which the rest of the suite never does.

    a circular import only shows up on the *first* import in a process. every other test imports pieces
    in an order that happens to work, so a cycle between a handler package and the service it uses can sit
    there with a green suite and a bot that will not start. this is the one test that would have caught it.
    """

    def assert_imports_cleanly(self, module: str) -> None:
        result = subprocess.run([sys.executable, "-c", f"import {module}"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"importing {module} failed:\n{result.stderr}")

    def test_main_imports_in_a_fresh_interpreter(self):
        self.assert_imports_cleanly("src.main")

    def test_application_imports_in_a_fresh_interpreter(self):
        self.assert_imports_cleanly("src.bot.application")
