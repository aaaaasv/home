import unittest

from src.bot.handlers.plants.formatting import task_action, task_emoji, task_label
from src.common.constants import CareTaskType


class CareTaskMapsTestCase(unittest.TestCase):
    def test_every_care_task_type_has_a_label_emoji_and_action(self):
        for task_type in CareTaskType:
            self.assertTrue(task_label(task_type), f"no label for {task_type}")
            self.assertTrue(task_emoji(task_type), f"no emoji for {task_type}")
            self.assertTrue(task_action(task_type), f"no action for {task_type}")
