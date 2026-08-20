"""Give every plant a slug so its tag can carry a word, not a number

Revision ID: 024
Revises: 023
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

TRANSLITERATION = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "h",
    "ґ": "g",
    "д": "d",
    "е": "e",
    "є": "ie",
    "ж": "zh",
    "з": "z",
    "и": "y",
    "і": "i",
    "ї": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ю": "iu",
    "я": "ia",
    "ь": "",
    "'": "",
    "ʼ": "",
}


def _slugify(name: str) -> str:
    letters = "".join(TRANSLITERATION.get(character, character) for character in (name or "").lower())
    return re.sub(r"[^a-z0-9]+", "-", letters).strip("-") or "plant"


def upgrade() -> None:
    op.add_column("plants", sa.Column("slug", sa.String(80), nullable=True))

    connection = op.get_bind()
    taken: set[str] = set()
    for plant_id, name in connection.execute(sa.text("SELECT id, name FROM plants ORDER BY id")):
        slug = _slugify(name)
        if slug in taken:
            suffix = 2
            while f"{slug}-{suffix}" in taken:
                suffix += 1
            slug = f"{slug}-{suffix}"
        taken.add(slug)
        connection.execute(sa.text("UPDATE plants SET slug = :slug WHERE id = :id"), {"slug": slug, "id": plant_id})

    op.create_index("ix_plants_slug", "plants", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_plants_slug", table_name="plants")
    op.drop_column("plants", "slug")
