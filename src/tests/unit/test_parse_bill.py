import unittest

from scripts.parse_bill import parse_line_items

# the layout `pdftotext -layout` produces: a name too long for its column is split across three rows — the head
# of the name, then the figures with an empty name column, then the tail. the figures are тариф, одиниця, обсяг,
# борг, нараховано, до сплати; the parser takes the last of them
BILL = """\
                        КВИТАНЦІЯ (РАХУНОК НА СПЛАТУ)
                                              лютий 2026

    Найменування послуги           Тариф     Од.вим.    Обсяг    БОРГ    НАРАХОВАНО    ДО СПЛАТИ
                                                                                       та корег.
Перша послуга з довгою
                                     2,07      м2        35,6    -117,47      73,69      -43,78
назвою на два рядки
Друга послуга                        0,75      м2        35,6      26,70      26,70       53,40
Третя послуга теж
                                     1,13      м2        35,6      40,23      40,23       80,46
переноситься
Четверта послуга                     0,89      м2        35,6      31,68      31,68       63,36
ВСЬОГО                                                             98,61      98,61      197,22
Рядок після підсумку                 9,99      м2        11,1      99,99      99,99       99,99
"""


class ParseLineItemsTestCase(unittest.TestCase):
    """
    The per-service rows of a utility bill, where a long name does not fit its column.

    the bug this guards was silent and arithmetic: two services vanished, and the only sign was that the rows
    added up to less than the bill's own total. as in the real document, ВСЬОГО counts what is owed and leaves
    the negative corrections out.
    """

    def test_a_name_wrapped_across_three_rows_is_read_whole_with_its_amount(self):
        items = parse_line_items(BILL)

        self.assertIn(("Перша послуга з довгою назвою на два рядки", -43.78), items)

    def test_a_name_that_fits_one_row_is_read_unchanged(self):
        items = parse_line_items(BILL)

        self.assertIn(("Друга послуга", 53.40), items)

    def test_the_head_of_a_wrapped_name_does_not_stick_to_the_service_before_it(self):
        items = parse_line_items(BILL)

        self.assertIn(("Третя послуга теж переноситься", 80.46), items)

    def test_every_service_is_read_in_the_order_the_bill_lists_them(self):
        items = parse_line_items(BILL)

        self.assertEqual(
            items,
            [
                ("Перша послуга з довгою назвою на два рядки", -43.78),
                ("Друга послуга", 53.40),
                ("Третя послуга теж переноситься", 80.46),
                ("Четверта послуга", 63.36),
            ],
        )

    def test_the_document_heading_above_the_table_is_not_read_as_a_service(self):
        names = [name for name, _ in parse_line_items(BILL)]

        self.assertNotIn("КВИТАНЦІЯ (РАХУНОК НА СПЛАТУ)", names)

    def test_a_row_below_the_total_is_not_read_as_a_service(self):
        names = [name for name, _ in parse_line_items(BILL)]

        self.assertNotIn("Рядок після підсумку", names)

    def test_the_services_that_are_owed_add_up_to_the_total_the_bill_states(self):
        owed = sum(amount for _, amount in parse_line_items(BILL) if amount > 0)

        self.assertEqual(round(owed, 2), 197.22)
