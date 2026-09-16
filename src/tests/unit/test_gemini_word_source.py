import json
import unittest

from src.bot.handlers.newspaper.gemini_word_source import parse_clues
from src.modules.newspaper.domain import CrosswordClue


def gemini_payload(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class ParseCluesTestCase(unittest.TestCase):
    def test_parse_clues_from_a_json_array_normalizes_each_answer_to_capitals(self):
        payload = gemini_payload(json.dumps([{"answer": "говерла ", "clue": " Найвища вершина України "}]))

        clues = parse_clues(payload)

        self.assertEqual(clues, [CrosswordClue(answer="ГОВЕРЛА", clue="Найвища вершина України")])

    def test_parse_clues_with_a_full_stop_after_the_clue_drops_it(self):
        payload = gemini_payload(json.dumps([{"answer": "КВАЗАР", "clue": "Надзвичайно яскраве ядро галактики."}]))

        clues = parse_clues(payload)

        self.assertEqual(clues, [CrosswordClue(answer="КВАЗАР", clue="Надзвичайно яскраве ядро галактики")])

    def test_parse_clues_from_text_that_is_not_json_returns_nothing(self):
        payload = gemini_payload("Ось слова для кросворду: говерла, дніпро")

        clues = parse_clues(payload)

        self.assertEqual(clues, [])

    def test_parse_clues_from_a_reply_without_candidates_returns_nothing(self):
        payload = {"promptFeedback": {"blockReason": "OTHER"}}

        clues = parse_clues(payload)

        self.assertEqual(clues, [])
