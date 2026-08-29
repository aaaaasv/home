import re
import sys
from pathlib import Path

MONTHS = {
    "січень": 1,
    "лютий": 2,
    "березень": 3,
    "квітень": 4,
    "травень": 5,
    "червень": 6,
    "липень": 7,
    "серпень": 8,
    "вересень": 9,
    "жовтень": 10,
    "листопад": 11,
    "грудень": 12,
}


def to_decimal(raw: str) -> float:
    return float(raw.replace(" ", "").replace(" ", "").replace(",", "."))


def parse_bill(text: str) -> dict:
    period = re.search(r"За\s+([А-Яа-яІіЇїЄєҐґ]+)\s+(\d{4})\s*р", text)
    total_row = re.search(r"ВСЬОГО\s+((?:-?[\d\s ]+,\d{2}\s*)+)", text)
    amounts = re.findall(r"-?[\d\s ]*\d,\d{2}", total_row.group(1)) if total_row else []

    return {
        "period_month": MONTHS.get(period.group(1).lower()) if period else None,
        "period_year": int(period.group(2)) if period else None,
        "recipient": (re.search(r"Отримувач\s+(.+?)\s{2,}", text) or [None, ""])[1].strip(),
        "edrpou": (re.search(r"ЄДРПОУ\s+(\d{8})", text) or [None, ""])[1],
        "iban": re.sub(r"\s", "", (re.search(r"Р/р\s+(UA[\s\d]{27,40})", text) or [None, ""])[1]),
        "account": (re.search(r"Особовий рахунок:\s*(\d+)", text) or [None, ""])[1],
        "due_day": int((re.search(r"не пізніше\s+(\d{1,2})\s+числа", text) or [None, 0])[1]),
        "debt_start": to_decimal(amounts[0]) if len(amounts) > 2 else None,
        "charged": to_decimal(amounts[1]) if len(amounts) > 2 else None,
        "to_pay": to_decimal(amounts[-1]) if amounts else None,
    }


TABLE_HEADER = "Найменування"
TABLE_FOOTER = "ВСЬОГО"


def parse_line_items(text: str) -> list[tuple[str, float]]:
    """
    Read the per-service rows, including the ones whose name is too long for the column.

    a wrapped name arrives as three rows — the head of the name, then the figures with an empty name column,
    then the tail — so not one of them carries both a name and its amount. reading starts at the table header
    and stops at its total, because the document around it is full of lines that look like nameless names.
    """
    items: list[tuple[str, float]] = []
    name_parts: list[str] = []
    amount: float | None = None
    amount_row_was_named = False
    inside_table = False

    def flush() -> None:
        nonlocal name_parts, amount
        if amount is not None and name_parts:
            items.append((" ".join(name_parts), amount))
        name_parts, amount = [], None

    for line in text.splitlines():
        stripped = line.strip()
        if not inside_table:
            inside_table = stripped.startswith(TABLE_HEADER)
            continue
        if stripped.startswith(TABLE_FOOTER):
            break

        name = line.split("  ")[0].strip()
        numbers = re.findall(r"-?[\d\s ]*\d(?:,\d{1,2})?", line)
        carries_amount = len(numbers) >= 2

        # a row of figures closes the item before it. so does a bare name, but only when the item before it
        # was already whole — after a nameless row of figures a bare name is the tail of a wrapped name
        if amount is not None and (carries_amount or (name and amount_row_was_named)):
            flush()

        if name:
            name_parts.append(name)
        if carries_amount:
            amount = to_decimal(numbers[-1])
            amount_row_was_named = bool(name)

    flush()
    return items


def report(text: str) -> None:
    parsed = parse_bill(text)
    for key, value in parsed.items():
        print(f"  {key:<14} {value}")

    print("\n  рядки:")
    line_items = parse_line_items(text)
    for name, value in line_items:
        print(f"    {name[:44]:<46} {value:>10.2f}")
    positives = sum(v for _, v in line_items if v > 0)
    negatives = sum(v for _, v in line_items if v < 0)
    matches_total = abs(positives - (parsed["to_pay"] or 0)) < 0.01
    print(f"\n  сума додатних:  {positives:>10.2f}   <- дорівнює ВСЬОГО? {matches_total}")
    print(f"  сума відʼємних: {negatives:>10.2f}   <- НЕ враховано у ВСЬОГО")


if __name__ == "__main__":
    report(Path(sys.argv[1]).read_text(encoding="utf-8"))
