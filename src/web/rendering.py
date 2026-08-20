"""Renders a plant as a herbarium specimen sheet.

Ukrainian lives here because this is a delivery layer, the same way src/bot/ is. Every number on the page
comes from PlantSheet — nothing is computed twice, and nothing is invented when a field is empty.
"""

from html import escape

from src.common.constants import CareTaskType
from src.modules.plant_care.domain import ClimatePoint, PlantSheet
from src.web.styles import GOOGLE_FONTS_URL, STYLESHEET

ROMAN_MONTHS = ("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii")
CALIBRATION_SWATCHES = (
    "#B33A2B",
    "#C98A2E",
    "#D8C64A",
    "#4C7A3A",
    "#2E5F86",
    "#5B3E7A",
    "#1C1712",
    "#7E7669",
    "#C4BEB2",
    "#F2EEE4",
)
TASK_NAMES = {
    CareTaskType.WATERING: "Полив",
    CareTaskType.FERTILIZING: "Живлення",
    CareTaskType.REPOTTING: "Пересадка",
    CareTaskType.FLUSH: "Промивання",
    CareTaskType.ROTATING: "Поворот",
    CareTaskType.PHOTO: "Знімок",
}
PAST_TASK_NAMES = {CareTaskType.WATERING: "Полито", CareTaskType.FERTILIZING: "Підживлено"}


def roman_date(moment) -> str:
    """13.vii.2026 — the herbarium convention, month in lower-case roman."""
    return f"{moment.day:02d}.{ROMAN_MONTHS[moment.month - 1]}.{moment.year}"


def _blank(value: str | None) -> str:
    return escape(value) if value else '<span class="blank">не записано</span>'


def _rhythm_plate(gaps: list[float], target_days: int) -> str:
    if len(gaps) < 2:
        return ""
    width, height, pad = 640, 132, 22
    low = min(min(gaps), target_days) - 0.6
    high = max(max(gaps), target_days) + 0.6

    def y_of(value: float) -> float:
        return pad + (high - value) / (high - low) * (height - 2 * pad)

    step = (width - 2 * pad) / (len(gaps) - 1)
    points = [(pad + index * step, y_of(gap)) for index, gap in enumerate(gaps)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.1" fill="{"#8A3324" if abs(gap - target_days) > 0.7 else "#4C5F35"}"/>'
        for (x, y), gap in zip(points, gaps)
    )
    labels = "".join(
        f'<text x="{x:.1f}" y="{height - 6}" font-size="9" fill="#A2957C" text-anchor="middle" '
        f'font-family="Courier Prime,monospace">{gap}</text>'
        for (x, _), gap in zip(points, gaps)
    )
    return f"""<section class="plate-block"><h3>Tabula II · ритм поливу</h3>
<p class="sub">Проміжки між поливами, у днях. Пунктир — призначені {target_days}; червона позначка — відхилення
понад ⅔ дня.</p>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Проміжки між поливами">
<line x1="{pad}" y1="{y_of(target_days):.1f}" x2="{width - pad}" y2="{y_of(target_days):.1f}" stroke="#4C5F35"
stroke-width="1" stroke-dasharray="5 4"/>
<text x="{width - pad + 2}" y="{y_of(target_days) + 3:.1f}" font-size="9" fill="#4C5F35" font-family="Courier
Prime,monospace">{target_days}д</text>
<polyline points="{line}" fill="none" stroke="#282019" stroke-width="1.5"/>{dots}{labels}</svg></section>"""


def _climate_plate(points: list[ClimatePoint], humidity_floor: float | None) -> str:
    if len(points) < 3:
        return ""
    width, height, pad = 640, 168, 24
    temperatures = [p.temperature_celsius for p in points]
    humidities = [p.relative_humidity_percent for p in points]

    def scale(values: list[float], value: float) -> float:
        low, high = min(values) - 0.6, max(values) + 0.6
        return pad + (high - value) / (high - low) * (height - 2 * pad)

    step = (width - 2 * pad) / (len(points) - 1)
    temperature_line = " ".join(
        f"{pad + i * step:.1f},{scale(temperatures, v):.1f}" for i, v in enumerate(temperatures)
    )
    humidity_line = " ".join(f"{pad + i * step:.1f},{scale(humidities, v):.1f}" for i, v in enumerate(humidities))
    hours = [point.hour[-2:] for point in points]
    nights = "".join(
        f'<rect x="{pad + i * step:.1f}" y="{pad}" width="{step:.1f}"'
        f' height="{height - 2 * pad}" fill="#282019" opacity=".055"/>'
        for i, hour in enumerate(hours)
        if int(hour) >= 22 or int(hour) < 6
    )
    ticks = "".join(
        f'<text x="{pad + i * step:.1f}" y="{height - 7}" font-size="8.5" fill="#A2957C" text-anchor="middle" '
        f'font-family="Courier Prime,monospace">{hour}</text>'
        for i, hour in enumerate(hours)
        if int(hour) % 6 == 0
    )
    floor_line = ""
    if humidity_floor is not None and min(humidities) - 0.6 <= humidity_floor <= max(humidities) + 0.6:
        y = scale(humidities, humidity_floor)
        floor_line = (
            f'<line x1="{pad}" y1="{y:.1f}" x2="{width - pad}" y2="{y:.1f}" stroke="#8A3324" '
            f'stroke-width="1" stroke-dasharray="4 4" opacity=".7"/>'
            f'<text x="{width - pad + 2}" y="{y + 3:.1f}" font-size="8.5" fill="#8A3324" '
            f'font-family="Courier Prime,monospace">{humidity_floor:.0f}%</text>'
        )
    return f"""<section class="plate-block"><h3>Tabula III · мікроклімат, дві доби</h3>
<p class="sub">Погодинне середнє. Затінені смуги — ніч. Червоний пунктир — нижня межа вологості.</p>
<svg viewBox="0 0 {width} {height}" role="img" aria-label="Температура і вологість за дві доби">
{nights}{floor_line}
<polyline points="{humidity_line}" fill="none" stroke="#8A3324" stroke-width="1.6"/>
<polyline points="{temperature_line}" fill="none" stroke="#4C5F35" stroke-width="1.6"/>{ticks}</svg>
<div class="legend"><span><i style="border-color:#4C5F35">
</i>температура, {min(temperatures):.1f}–{max(temperatures):.1f} °C</span>
<span><i style="border-color:#8A3324"></i>вологість, {min(humidities):.1f}–{max(humidities):.1f} %</span>
</div></section>"""


def _label(sheet: PlantSheet) -> str:
    watering = sheet.watering
    rows = [
        ("Надійшов", f"{roman_date(sheet.created_at)} · {sheet.age_days} діб у домі"),
        ("Походження", _blank(sheet.provenance)),
        ("Локалітет", _blank(sheet.location)),
        ("Субстрат", _blank(sheet.substrate)),
    ]
    if watering is not None:
        rows.append(("Полив", f"кожні {watering.interval_days} дн. · далі {roman_date(watering.next_due_on)}"))
    for schedule in sheet.schedules:
        if schedule.task_type is CareTaskType.REPOTTING:
            rows.append(("Пересадка", roman_date(schedule.next_due_on)))
    rows.append(("Токсичність", _blank(sheet.toxicity)))
    fields = "".join(f"<dt>{escape(name)}</dt><dd>{value}</dd>" for name, value in rows)
    return f"""<div class="label"><h3>Hortus Domesticus</h3><dl>{fields}</dl>
<div class="stamp"><b>HD</b>ACC {sheet.id:03d}</div></div>"""


def _slips(sheet: PlantSheet) -> str:
    """Determination and annotation slips, newest last — a real sheet accrues them upward from the label."""
    slips = []
    if sheet.species:
        slips.append(
            (
                "Det.",
                f"{sheet.species} — {sheet.recent_events[-1].performed_by_display_name}"
                if sheet.recent_events
                else sheet.species,
                roman_date(sheet.created_at),
            )
        )
    for event in list(reversed(sheet.recent_events))[-3:]:
        verb = PAST_TASK_NAMES.get(event.task_type, TASK_NAMES.get(event.task_type, str(event.task_type)))
        slips.append(("Annot.", f"{verb} — {event.performed_by_display_name}", roman_date(event.performed_at)))
    return "".join(
        f'<div class="slip"><b>{kind}</b> {escape(text)}<span>{date}</span></div>' for kind, text, date in slips
    )


def _carers(sheet: PlantSheet) -> str:
    if not sheet.carers:
        return ""
    entries = "".join(
        f'<div class="curator"><div class="who">{escape(c.name)}</div><div class="tally">'
        f'<span class="marks">{"|" * min(c.count, 12)}</span><span class="n">{c.count}</span></div></div>'
        for c in sheet.carers
    )
    return (
        f'<section class="plate-block"><h3>Coluerunt · хто доглядає</h3><div class="curators">{entries}</div></section>'
    )


def _gauge(
    label: str,
    value: float | None,
    low: float,
    high: float,
    band_low: float | None,
    band_high: float | None,
    unit: str,
    warn: bool,
) -> str:
    if value is None:
        return ""
    span = high - low
    ideal = ""
    if band_low is not None and band_high is not None:
        left = max(0.0, (band_low - low) / span) * 100
        right = max(0.0, (high - band_high) / span) * 100
        ideal = f'<div class="ideal" style="left:{left:.1f}%;right:{right:.1f}%"></div>'
    position = min(max((value - low) / span, 0.0), 1.0) * 100
    verdict = "Нижче бажаного мінімуму." if warn else "У межах бажаного."
    return f"""<div class="reading"><h3>{escape(label)} · {low:g}–{high:g} {unit}</h3>
<div class="bar">{ideal}<div class="now" style="left:{position:.1f}%"><b>{value:.1f} {unit}</b></div></div>
<p class="{'warn' if warn else ''}">{verdict}</p></div>"""


def render_plant_sheet(sheet: PlantSheet, photo_url, bot_name: str, can_act: bool) -> str:
    swatches = "".join(f'<i style="background:{colour}"></i>' for colour in CALIBRATION_SWATCHES)
    latest = sheet.photos[-1] if sheet.photos else None
    specimen = (
        (
            f'<figure class="mount"><img src="{photo_url(latest.id)}" alt="{escape(sheet.name)}">'
            f'<i class="strap a"></i><i class="strap b"></i><i class="strap c"></i></figure>'
        )
        if latest
        else ""
    )
    plates = "".join(
        f'<figure><div class="card"><img src="{photo_url(photo.id)}" alt="{escape(sheet.name)}"></div>'
        f"<figcaption>{roman_date(photo.taken_at)}</figcaption></figure>"
        for photo in sheet.photos
    )
    temperature_gauge = _gauge(
        "Температура",
        sheet.current_temperature_celsius,
        10,
        35,
        sheet.ideal_temperature_min_celsius,
        sheet.ideal_temperature_max_celsius,
        "°C",
        False,
    )
    humidity_gauge = _gauge(
        "Вологість",
        sheet.current_humidity_percent,
        10,
        100,
        sheet.ideal_humidity_min_percent,
        sheet.ideal_humidity_max_percent,
        "%",
        sheet.humidity_is_low,
    )
    watering = sheet.watering
    rhythm = _rhythm_plate(sheet.watering_gaps_days, watering.interval_days) if watering else ""
    action = ""
    if can_act:
        last = next((e for e in sheet.recent_events if e.task_type is CareTaskType.WATERING), None)
        note = (
            f"Останній — {roman_date(last.performed_at)}, {escape(last.performed_by_display_name)}"
            if last
            else "Ще не поливали"
        )
        action = (
            f'<form class="act" method="post" action="water"><button type="submit">Записати полив</button>'
            f"<p>{note}</p></form>"
        )
    return f"""<title>{escape(sheet.name)}, HD {sheet.id:03d}</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{GOOGLE_FONTS_URL}">
<style>{STYLESHEET}</style>
<p class="drawer-tag"><span>{escape(sheet.species or "Hortus")}</span><span>Hortus Domesticus · HD</span></p>
<div class="folder">
  <article class="sheet">
    <div class="calib"><div class="swatches">{swatches}</div><div class="ruler"></div></div>
    <header class="head"><div><h1>Hortus Domesticus</h1><p>Домашній гербарій</p></div>
      <div class="barcode"><div class="bars"></div><small>HD {sheet.id:06d}</small></div></header>
    {specimen}
    <div class="binomial">
      <p class="fam">{escape((sheet.species or "").split()[0] if sheet.species else "—")}</p>
      <h2>{escape(sheet.species or sheet.name)}</h2>
      <p class="vern">у домі — <b>{escape(sheet.name)}</b></p>
      {f'<p class="range">Природний ареал: <b>{escape(sheet.native_range)}</b></p>' if sheet.native_range else ""}
    </div>
    <section class="readings">
      {temperature_gauge}
      {humidity_gauge}
    </section>
    {rhythm}
    {_climate_plate(sheet.climate, sheet.ideal_humidity_min_percent)}
    {_carers(sheet)}
    <div class="lower">
      <div class="packet"><h3>Fragmenta</h3><p>{escape(sheet.notes) if sheet.notes else "—"}</p></div>
      <div><div class="slips">{_slips(sheet)}</div>{_label(sheet)}</div>
    </div>
  </article>
</div>
<section class="contact"><h2>Зібрання таблиць</h2>
  <p>{len(sheet.photos)} знімк{"ів" if len(sheet.photos) != 1 else "ок"} · доглядає {bot_name}</p>
  <div class="strip">{plates}</div></section>
{action}"""
