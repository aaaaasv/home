"""Turns a plant's name into the word that appears in its URL."""

import re

# the official Ukrainian romanisation, near enough — this is a url slug, not a passport
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


def slugify(name: str) -> str:
    """A lower-case latin slug, so a tag can say /p/tihl instead of /p/1."""
    letters = "".join(TRANSLITERATION.get(character, character) for character in name.lower())
    slug = re.sub(r"[^a-z0-9]+", "-", letters).strip("-")
    return slug or "plant"


def unique_slug(name: str, taken: set[str]) -> str:
    """The slug, with a number appended only if the plain one is already someone else's."""
    slug = slugify(name)
    if slug not in taken:
        return slug
    suffix = 2
    while f"{slug}-{suffix}" in taken:
        suffix += 1
    return f"{slug}-{suffix}"
