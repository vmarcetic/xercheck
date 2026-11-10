"""Display-only overview numbers for one XER file.

Nothing here changes a check. These helpers only summarise values that are
already in the export:

* Exported finish: ``PROJECT.scd_end_date`` (the scheduled finish P6 wrote
  at the last schedule run). The latest value across PROJECT rows is shown.
* Data date: ``PROJECT.last_recalc_date``.
* Zero or negative float: activities whose stored total float (the same
  column the float check reads) is at or below 0 hours.
* Median total float: the median of the stored total-float values, in
  exported working hours. Blank, non-numeric, and non-finite values are left
  out and counted separately. Nothing is recalculated or converted to days.

A missing or unreadable date is reported as missing. No date is invented.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

FINISH_FIELD = "scd_end_date"
DATA_DATE_FIELD = "last_recalc_date"

_DATE_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


@dataclass(frozen=True)
class Overview:
    exported_finish: str | None
    finish_note: str
    data_date: str | None
    data_date_note: str
    activity_count: int
    float_values: int
    float_excluded: int
    zero_or_negative: int
    negative: int
    median_float_hours: Decimal | None


def parse_xer_date(raw: str) -> datetime | None:
    """Read an XER date such as ``2019-06-18 08:00``. Return None if unreadable."""
    text = (raw or "").strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def latest_project_date(values: list[str], field: str) -> tuple[str | None, str]:
    """Pick the latest readable date from PROJECT rows.

    Returns the original text of that date (no time zone is added) and a short
    note. If no row has a readable value, the text is None and the note says so.
    """
    readable: list[tuple[datetime, str]] = []
    blank = 0
    unreadable = 0
    for raw in values:
        text = (raw or "").strip()
        if not text:
            blank += 1
            continue
        parsed = parse_xer_date(text)
        if parsed is None:
            unreadable += 1
            continue
        readable.append((parsed, text))
    if not values:
        return None, f"PROJECT.{field} is not in this export."
    if not readable:
        if unreadable:
            return None, f"PROJECT.{field} could not be read as a date."
        return None, f"PROJECT.{field} is blank in this export."
    readable.sort()
    text = readable[-1][1]
    note = f"PROJECT.{field}"
    distinct = {item[1] for item in readable}
    if len(distinct) > 1:
        note += f", latest of {len(distinct)} projects"
    if blank or unreadable:
        note += f"; {blank + unreadable} project row(s) without a readable value"
    return text, note


def median(values: list[Decimal]) -> Decimal | None:
    """Median of Decimal values. None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def build_overview(
    project_rows: list[dict[str, str]] | None,
    project_fields: tuple[str, ...],
    activity_count: int,
    float_values: list[Decimal] | None,
    float_excluded: int,
) -> Overview:
    """Summarise one file. ``float_values`` is None when there is no float column."""
    if project_rows is None or FINISH_FIELD not in project_fields:
        finish, finish_note = None, f"PROJECT.{FINISH_FIELD} is not in this export."
    else:
        finish, finish_note = latest_project_date(
            [row.get(FINISH_FIELD, "") for row in project_rows], FINISH_FIELD
        )
    if project_rows is None or DATA_DATE_FIELD not in project_fields:
        data_date, data_note = None, f"PROJECT.{DATA_DATE_FIELD} is not in this export."
    else:
        data_date, data_note = latest_project_date(
            [row.get(DATA_DATE_FIELD, "") for row in project_rows], DATA_DATE_FIELD
        )
    values = float_values or []
    return Overview(
        exported_finish=finish,
        finish_note=finish_note,
        data_date=data_date,
        data_date_note=data_note,
        activity_count=activity_count,
        float_values=len(values),
        float_excluded=float_excluded if float_values is not None else 0,
        zero_or_negative=sum(1 for value in values if value <= 0),
        negative=sum(1 for value in values if value < 0),
        median_float_hours=median(values) if float_values is not None else None,
    )
