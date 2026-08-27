import json
import unittest

from src.infrastructure.adapters.gemini_language_model import (
    build_request_body,
    extract_answer_text,
    names_the_daily_quota,
)
from src.modules.assistant.services.language_model import MODEL_ROLE, USER_ROLE, ConversationTurn, ImageAttachment


class BuildRequestBodyTestCase(unittest.TestCase):
    def test_build_request_body_sends_the_grounding_as_a_system_instruction_with_google_search_on(self):
        body = build_request_body([ConversationTurn(role=USER_ROLE, text="коли останнє метро?")], "ти помічник", 0.2)

        self.assertEqual(body["systemInstruction"], {"parts": [{"text": "ти помічник"}]})
        self.assertEqual(body["contents"], [{"role": "user", "parts": [{"text": "коли останнє метро?"}]}])
        self.assertEqual(body["tools"], [{"google_search": {}}])
        self.assertEqual(body["generationConfig"], {"temperature": 0.2})

    def test_build_request_body_keeps_the_earlier_turns_in_order(self):
        conversation = [
            ConversationTurn(role=USER_ROLE, text="як часто поливати плющ?"),
            ConversationTurn(role=MODEL_ROLE, text="Раз на тиждень."),
            ConversationTurn(role=USER_ROLE, text="а взимку?"),
        ]

        body = build_request_body(conversation, "ти помічник", 0.2)

        self.assertEqual(
            body["contents"],
            [
                {"role": "user", "parts": [{"text": "як часто поливати плющ?"}]},
                {"role": "model", "parts": [{"text": "Раз на тиждень."}]},
                {"role": "user", "parts": [{"text": "а взимку?"}]},
            ],
        )

    def test_build_request_body_inlines_images_as_base64(self):
        turn = ConversationTurn(
            role=USER_ROLE, text="що це?", images=[ImageAttachment(data=b"\x00\x01\x02", mime_type="image/png")]
        )

        body = build_request_body([turn], "ти помічник", 0.2)

        self.assertEqual(
            body["contents"][0]["parts"],
            [{"text": "що це?"}, {"inline_data": {"mime_type": "image/png", "data": "AAEC"}}],
        )


class NamesTheDailyQuotaTestCase(unittest.TestCase):
    def test_names_the_daily_quota_recognises_the_spent_day(self):
        error_body = json.dumps(
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}],
                        }
                    ],
                }
            }
        )

        self.assertTrue(names_the_daily_quota(error_body))

    def test_names_the_daily_quota_treats_the_per_minute_limit_as_not_daily(self):
        error_body = json.dumps(
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                            "violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}],
                        }
                    ],
                }
            }
        )

        self.assertFalse(names_the_daily_quota(error_body))

    def test_names_the_daily_quota_treats_an_unrecognised_body_as_not_daily(self):
        self.assertFalse(names_the_daily_quota("<html>429 Too Many Requests</html>"))


class ExtractAnswerTextTestCase(unittest.TestCase):
    def test_extract_answer_text_reads_the_first_candidate_part(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "  Останній потяг ~22:45.  "}]}}]}

        self.assertEqual(extract_answer_text(payload), "Останній потяг ~22:45.")

    def test_extract_answer_text_joins_multiple_grounded_parts(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "Перша частина. "}, {"text": "Друга."}]}}]}

        self.assertEqual(extract_answer_text(payload), "Перша частина. Друга.")

    def test_extract_answer_text_returns_none_when_there_are_no_candidates(self):
        self.assertIsNone(extract_answer_text({"candidates": []}))

    def test_extract_answer_text_returns_none_when_a_candidate_has_no_parts(self):
        self.assertIsNone(extract_answer_text({"candidates": [{"content": {}}]}))

    def test_extract_answer_text_returns_none_for_an_empty_text(self):
        self.assertIsNone(extract_answer_text({"candidates": [{"content": {"parts": [{"text": ""}]}}]}))


if __name__ == "__main__":
    unittest.main()
