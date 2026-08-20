"""The specimen sheet's stylesheet and script, kept as real CSS and JS so they stay editable as such."""

from pathlib import Path

GOOGLE_FONTS_URL = "https://fonts.googleapis.com/css2?family=Cinzel:wght@400;600&family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=Courier+Prime:ital,wght@0,400;0,700;1,400&display=swap"  # noqa: E501

STYLESHEET = (Path(__file__).with_name("sheet.css")).read_text(encoding="utf-8")
SCRIPT = (Path(__file__).with_name("sheet.js")).read_text(encoding="utf-8")
