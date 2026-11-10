"""One SVG bar chart of finding counts."""

from html import escape

from xercheck.check import CHART_CODES, CODE_LABELS, Report
from xercheck.explain import SCHEDULE_CODES

_FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def findings_chart(report: Report) -> str:
    """Return one standalone SVG of the main check counts."""
    totals = report.counts()
    rows = [(code, CODE_LABELS[code], totals.get(code, 0)) for code in CHART_CODES]
    row_height = 30
    label_width = 150
    width = 560
    top = 8
    height = top + row_height * len(rows) + 8
    bar_left = label_width + 10
    bar_max = 330
    peak = max([count for _code, _label, count in rows] + [1])
    summary = ", ".join(f"{label} {count}" for _code, label, count in rows)
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-labelledby="chartTitle chartDesc" width="100%" '
            f'viewBox="0 0 {width} {height}" font-family="{_FONT}">'
        ),
        '<title id="chartTitle">Finding counts by check</title>',
        (
            "<desc id=\"chartDesc\">Bar chart of finding counts for this check. "
            + escape(summary)
            + ". Counts are hours-field and logic findings, not a float recalculation.</desc>"
        ),
    ]
    for index, (code, label, count) in enumerate(rows):
        y = top + index * row_height
        width_px = 0 if count == 0 else max(3, round(bar_max * count / peak))
        schedule = code in SCHEDULE_CODES
        fill = "#2563eb" if schedule else "#64748b"
        text_fill = "#0f172a" if count else "#94a3b8"
        weight = "600" if schedule else "400"
        parts.append(
            f'<text x="0" y="{y + 18}" font-size="12" font-weight="{weight}" fill="{text_fill}">'
            f"{escape(label)}</text>"
        )
        parts.append(
            f'<rect x="{bar_left}" y="{y + 7}" width="{bar_max}" height="14" rx="3" '
            f'fill="#f1f5f9"></rect>'
        )
        parts.append(
            f'<rect x="{bar_left}" y="{y + 7}" width="{width_px}" height="14" rx="3" fill="{fill}">'
            f"<title>{escape(label)}: {count}</title></rect>"
        )
        parts.append(
            f'<text x="{bar_left + bar_max + 10}" y="{y + 18}" font-size="12" '
            f'font-weight="600" fill="{text_fill}">{count}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)
