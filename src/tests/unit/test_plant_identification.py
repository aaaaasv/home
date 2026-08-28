import unittest

from src.bot.handlers.plants.formatting import render_plant_identification
from src.bot.handlers.plants.gemini_plant_identifier import parse_identification
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


class RenderPlantIdentificationTestCase(unittest.TestCase):
    def test_render_plant_identification_leads_with_the_everyday_name_and_keeps_the_latin_under_it(self):
        card = render_plant_identification(
            PlantIdentification(
                common_name="пеперомія",
                species="Peperomia obtusifolia",
                watering_interval_days=7,
                care_notes="Заливають частіше, ніж сушать.",
            )
        )

        self.assertEqual(
            card,
            "Схоже на це:\n\n<b>пеперомія</b>\n<i>Peperomia obtusifolia</i>\n"
            "\n💧 поливати раз на 7 дн.\n\nЗаливають частіше, ніж сушать.",
        )

    def test_render_plant_identification_says_only_what_the_model_knew(self):
        card = render_plant_identification(
            PlantIdentification(common_name=None, species="Peperomia", watering_interval_days=None, care_notes=None)
        )

        self.assertEqual(card, "Схоже на це:\n\n<b>Peperomia</b>")
