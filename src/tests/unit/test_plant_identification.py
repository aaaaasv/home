import unittest

from src.bot.handlers.plants.claude_plant_identifier import IDENTIFICATION_SCHEMA
from src.bot.handlers.plants.gemini_plant_identifier import parse_identification
from src.bot.handlers.plants.plant_identification_prompt import SYSTEM_PROMPT as IDENTIFICATION_PROMPT
from src.modules.plant_care.domain import PlantIdentification


def build_payload(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class ParseIdentificationTestCase(unittest.TestCase):
    """
    The model is asked for a shape it is free to ignore, so every reply is treated as untrusted text.

    a wrong species is worse than none here: it gets copied into the card and believed for years.
    """

    def test_parse_identification_reads_every_field_the_model_filled(self):
        payload = build_payload(
            '{"common_name": "пеперомія", "species": "Peperomia obtusifolia", '
            '"watering_interval_days": 7, "care_notes": "Заливають частіше, ніж сушать."}'
        )

        identification = parse_identification(payload)

        self.assertEqual(
            identification,
            PlantIdentification(
                common_name="пеперомія",
                species="Peperomia obtusifolia",
                watering_interval_days=7,
                care_notes="Заливають частіше, ніж сушать.",
            ),
        )

    def test_parse_identification_keeps_a_genus_without_a_species(self):
        payload = build_payload(
            '{"common_name": null, "species": "Peperomia", "watering_interval_days": null, "care_notes": null}'
        )

        identification = parse_identification(payload)

        self.assertEqual(
            identification,
            PlantIdentification(common_name=None, species="Peperomia", watering_interval_days=None, care_notes=None),
        )

    def test_parse_identification_naming_nothing_at_all_is_the_same_as_no_reply(self):
        payload = build_payload(
            '{"common_name": null, "species": null, "watering_interval_days": 7, "care_notes": "Полий."}'
        )

        self.assertIsNone(parse_identification(payload))

    def test_parse_identification_with_unparsable_json_returns_none(self):
        self.assertIsNone(parse_identification(build_payload("вибач, я не бачу рослини")))

    def test_parse_identification_without_candidates_returns_none(self):
        self.assertIsNone(parse_identification({"candidates": []}))


class IdentificationSchemaTestCase(unittest.TestCase):
    """
    The shape asked of claude, checked against the shape it is parsed into.

    these two drifted apart for seven weeks and every identification was silently discarded: the schema
    forbids keys it does not list, so a field missing from it can never come back, and the reply then fails
    validation whole — the family saw "не впізнаю за цим фото" for plants the model had named correctly.
    """

    def test_the_schema_asks_for_every_field_the_identification_is_parsed_into(self):
        parsed_fields = set(PlantIdentification.model_fields)

        self.assertEqual(set(IDENTIFICATION_SCHEMA["properties"]), parsed_fields)
        self.assertEqual(set(IDENTIFICATION_SCHEMA["required"]), parsed_fields)


class IdentificationPromptRulesTestCase(unittest.TestCase):
    """
    The two rules the written care text kept breaking before they were spelled out.

    the model read the room off the photo — «не ставте біля батареї (на фото радіатор поруч з рослиною)» —
    for a plant that had merely been carried there to be photographed, and it addressed the family as «ви»
    while every other line the bot writes says «ти».
    """

    def test_the_prompt_refuses_to_read_the_plants_surroundings_off_the_photo(self):
        self.assertIn("Фон у кадрі нічого не каже про рослину", IDENTIFICATION_PROMPT)

    def test_the_prompt_asks_for_the_singular_imperative_the_rest_of_the_bot_speaks(self):
        self.assertIn("Звертайся на «ти» в однині й у наказовому способі", IDENTIFICATION_PROMPT)
