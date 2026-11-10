"""Rules for broken rows, open ends, and stored total float.

Float is read from the XER column. It is not recalculated. The column in a
P6 export is ``total_float_hr_cnt`` (Total Float, hours). A file that only
has ``total_float_hr`` uses that column, still as hours. Values are never
divided by hours per day.

Open ends:

* ``TT_Mile`` (start milestone) does not need a predecessor. It still needs
  a successor.
* ``TT_FinMile`` (finish milestone) does not need a successor. It still
  needs a predecessor.
* Every other activity type, including a blank type, ``TT_WBS``, and
  ``TT_LOE``, needs both. There is no blanket milestone exemption.

A relationship is resolved only inside the same file, using ``proj_id`` plus
``task_id`` and ``pred_proj_id`` plus ``pred_task_id``. The same numeric id
in another file is a different activity. A predecessor project that is not
in this file is unknown scope, not a missing link and not proof of an
external dependency.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from xercheck.limits import read_limited
from xercheck.overview import Overview, build_overview
from xercheck.parser import ParsedFile, ParsedRow, parse_xer

DISCLAIMER = (
    "This checker reads Primavera P6 XER text. It is not a P6 scheduling engine. "
    "It does not calculate the critical path, calendars, or float. "
    "Total float is the stored hours value in total_float_hr_cnt "
    "(or total_float_hr when that is the only total-float column). "
    "Hours are not converted to days."
)

DEFAULT_HIGH_FLOAT_HOURS = Decimal("160")

CHART_CODES = (
    "missing_predecessor",
    "missing_successor",
    "negative_float",
    "high_float",
    "malformed_row",
    "malformed_link",
    "dangling_link",
    "unknown_scope",
    "missing_float",
    "nonnumeric_float",
    "nonfinite_float",
)

ALL_CODES = CHART_CODES + (
    "unsupported_table",
    "unsupported_directive",
    "unsupported_field",
    "missing_table",
    "duplicate_activity",
    "missing_end_marker",
    "missing_header",
)

CODE_LABELS = {
    "missing_predecessor": "Missing predecessor",
    "missing_successor": "Missing successor",
    "negative_float": "Negative float",
    "high_float": "High float",
    "malformed_row": "Malformed row",
    "malformed_link": "Malformed link",
    "dangling_link": "Dangling link",
    "unknown_scope": "Unknown scope",
    "missing_float": "Missing float",
    "nonnumeric_float": "Non-numeric float",
    "nonfinite_float": "Non-finite float",
    "unsupported_table": "Unsupported table",
    "unsupported_directive": "Unsupported marker",
    "unsupported_field": "Unsupported field",
    "missing_table": "Missing table",
    "duplicate_activity": "Duplicate activity",
    "missing_end_marker": "Missing end marker",
    "missing_header": "Missing header",
}

_NONFINITE_TOKENS = {
    "nan",
    "+nan",
    "-nan",
    "inf",
    "+inf",
    "-inf",
    "infinity",
    "+infinity",
    "-infinity",
}
_LINK_FIELDS = ("task_id", "pred_task_id", "proj_id", "pred_proj_id")


@dataclass(frozen=True)
class Finding:
    file_index: int
    code: str
    filename: str
    table: str
    line: int | None
    activity_id: str
    activity_name: str
    message: str


@dataclass
class SourceInfo:
    filename: str
    sha256: str
    byte_length: int
    encoding: str
    projects: tuple[str, ...]
    activity_count: int
    relationship_count: int
    float_column: str | None
    # Display-only summary. It does not affect any finding.
    overview: Overview | None = None


@dataclass
class Report:
    sources: list[SourceInfo]
    findings: list[Finding]
    threshold_hours: Decimal
    disclaimer: str = DISCLAIMER

    def counts(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for finding in self.findings:
            totals[finding.code] = totals.get(finding.code, 0) + 1
        return totals


@dataclass
class _Activity:
    line: int
    proj_id: str
    task_id: str
    code: str
    name: str
    task_type: str | None
    float_raw: str | None


@dataclass
class _LinkEnds:
    status: str
    successor: tuple[str, str] | None
    predecessor: tuple[str, str] | None
    succ_state: str
    pred_state: str
    row: ParsedRow
    detail: str


def parse_threshold(raw: str) -> Decimal:
    """Accept a finite high-float threshold in hours, zero or greater."""
    text = raw.strip()
    if text.lower() in _NONFINITE_TOKENS:
        raise ValueError(
            "High-float threshold must be a finite number of hours, zero or greater."
        )
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(
            "High-float threshold must be a finite number of hours, zero or greater."
        ) from exc
    if not value.is_finite() or value < 0:
        raise ValueError(
            "High-float threshold must be a finite number of hours, zero or greater."
        )
    return value


def format_hours(value: Decimal) -> str:
    """Format a hours value without expanding a huge Decimal into a long string."""
    if value == 0:
        return "0"
    if abs(value) >= Decimal("1e12"):
        return format(value, ".6e")
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def filter_findings(findings: list[Finding], code: str) -> list[Finding]:
    if not code:
        return list(findings)
    return [finding for finding in findings if finding.code == code]


def disambiguate(names: list[str]) -> list[str]:
    totals = Counter(names)
    seen: Counter[str] = Counter()
    labels: list[str] = []
    for name in names:
        if totals[name] == 1:
            labels.append(name)
            continue
        seen[name] += 1
        labels.append(f"{name}#{seen[name]}")
    return labels


def check_named(items: list[tuple[str, bytes]], threshold: Decimal) -> Report:
    labels = disambiguate([name for name, _data in items])
    parsed = [
        parse_xer(data, label)
        for label, (_name, data) in zip(labels, items)
    ]
    return evaluate(parsed, threshold)


def check_paths(paths: list[Path], threshold: Decimal) -> Report:
    items = [(str(path), read_limited(path)) for path in paths]
    return check_named(items, threshold)


def evaluate(files: list[ParsedFile], threshold: Decimal) -> Report:
    findings: list[Finding] = []
    sources: list[SourceInfo] = []
    for index, parsed in enumerate(files):
        file_findings, source = _check_file(index, parsed, threshold)
        findings.extend(file_findings)
        sources.append(source)
    findings.sort(key=lambda item: (item.file_index, item.line or 10**9, item.code, item.message))
    return Report(sources=sources, findings=findings, threshold_hours=threshold)


def _check_file(
    index: int, parsed: ParsedFile, threshold: Decimal
) -> tuple[list[Finding], SourceInfo]:
    findings: list[Finding] = []

    def add(
        code: str,
        table: str,
        line: int | None,
        activity_id: str,
        activity_name: str,
        message: str,
    ) -> None:
        findings.append(
            Finding(
                file_index=index,
                code=code,
                filename=parsed.filename,
                table=table,
                line=line,
                activity_id=activity_id,
                activity_name=activity_name,
                message=message,
            )
        )

    for issue in parsed.issues:
        add(issue.code, issue.table, issue.line, "", "", issue.message)

    projects: set[str] = set()
    project_names: list[str] = []
    project_table = parsed.tables.get("PROJECT")
    if project_table is None:
        add(
            "missing_table",
            "PROJECT",
            None,
            "",
            "",
            "PROJECT table is absent. Project ids are taken from TASK rows. "
            "A predecessor project that is not on a TASK row is unknown scope.",
        )
    elif "proj_id" not in project_table.fields:
        if project_table.fields:
            add(
                "unsupported_field",
                "PROJECT",
                project_table.header_line,
                "",
                "",
                "PROJECT has no proj_id column, so the project catalogue cannot be read.",
            )
    else:
        short_name = "proj_short_name" in project_table.fields
        for row in project_table.rows:
            proj_id = row.values.get("proj_id", "")
            if not proj_id:
                add(
                    "malformed_row",
                    "PROJECT",
                    row.line,
                    "",
                    "",
                    "PROJECT row has an empty proj_id.",
                )
                continue
            projects.add(proj_id)
            if short_name and row.values.get("proj_short_name"):
                project_names.append(row.values["proj_short_name"])

    activities: dict[tuple[str, str], _Activity] = {}
    float_column: str | None = None
    task_table = parsed.tables.get("TASK")
    if task_table is None:
        add(
            "missing_table",
            "TASK",
            None,
            "",
            "",
            "TASK table is absent, so activities, float, and open ends were not checked.",
        )
    elif "task_id" not in task_table.fields or "proj_id" not in task_table.fields:
        if task_table.fields:
            add(
                "unsupported_field",
                "TASK",
                task_table.header_line,
                "",
                "",
                "TASK has no task_id or proj_id column, so activities cannot be identified.",
            )
    else:
        if "total_float_hr_cnt" in task_table.fields:
            float_column = "total_float_hr_cnt"
        elif "total_float_hr" in task_table.fields:
            float_column = "total_float_hr"
        else:
            add(
                "unsupported_field",
                "TASK",
                task_table.header_line,
                "",
                "",
                "TASK has neither total_float_hr_cnt nor total_float_hr. "
                "Float was not checked and blank float was not treated as zero.",
            )
        has_type = "task_type" in task_table.fields
        if not has_type:
            add(
                "unsupported_field",
                "TASK",
                task_table.header_line,
                "",
                "",
                "TASK has no task_type column, so start and finish milestone exceptions were not applied.",
            )
        for row in task_table.rows:
            task_id = row.values.get("task_id", "")
            proj_id = row.values.get("proj_id", "")
            if not task_id or not proj_id:
                add(
                    "malformed_row",
                    "TASK",
                    row.line,
                    task_id,
                    row.values.get("task_name", ""),
                    "TASK row is missing task_id or proj_id, so it was not used as an activity.",
                )
                continue
            key = (proj_id, task_id)
            if key in activities:
                kept = activities[key]
                add(
                    "duplicate_activity",
                    "TASK",
                    row.line,
                    task_id,
                    row.values.get("task_name", ""),
                    f"Duplicate activity key proj_id {proj_id} task_id {task_id}. "
                    f"The earlier row on line {kept.line} is kept.",
                )
                continue
            projects.add(proj_id)
            activities[key] = _Activity(
                line=row.line,
                proj_id=proj_id,
                task_id=task_id,
                code=row.values.get("task_code", ""),
                name=row.values.get("task_name", ""),
                task_type=row.values.get("task_type", "") if has_type else None,
                float_raw=row.values.get(float_column, "") if float_column else None,
            )

    relationship_count = 0
    pred_table = parsed.tables.get("TASKPRED")
    links_available = False
    if pred_table is None:
        add(
            "missing_table",
            "TASKPRED",
            None,
            "",
            "",
            "TASKPRED table is absent, so missing predecessors and successors cannot be determined. "
            "No open-end findings were raised from this file.",
        )
    elif any(name not in pred_table.fields for name in _LINK_FIELDS):
        if pred_table.fields:
            add(
                "unsupported_field",
                "TASKPRED",
                pred_table.header_line,
                "",
                "",
                "TASKPRED is missing task_id, pred_task_id, proj_id, or pred_proj_id. "
                "Links cannot be resolved. No open-end findings were raised from this file.",
            )
        relationship_count = len(pred_table.rows)
    else:
        links_available = True
        relationship_count = len(pred_table.rows)
        has_predecessor: set[tuple[str, str]] = set()
        has_successor: set[tuple[str, str]] = set()
        for row in pred_table.rows:
            link = _classify_link(row, projects, activities)
            if link.status == "malformed":
                add("malformed_link", "TASKPRED", row.line, "", "", link.detail)
                continue
            if link.status == "dangling":
                add("dangling_link", "TASKPRED", row.line, "", "", link.detail)
                continue
            if link.status == "unknown":
                add("unknown_scope", "TASKPRED", row.line, "", "", link.detail)
            if (
                link.successor is not None
                and link.succ_state == "resolved"
                and link.pred_state in ("resolved", "unknown")
            ):
                has_predecessor.add(link.successor)
            if (
                link.predecessor is not None
                and link.pred_state == "resolved"
                and link.succ_state in ("resolved", "unknown")
            ):
                has_successor.add(link.predecessor)

        if task_table is not None:
            for key, activity in activities.items():
                _open_ends(add, activity, key, has_predecessor, has_successor)

    if float_column is not None:
        for activity in activities.values():
            _float_finding(add, activity, float_column, threshold)

    float_values: list[Decimal] | None = None
    float_excluded = 0
    if float_column is not None:
        float_values = []
        for activity in activities.values():
            kind, value = _parse_hours(activity.float_raw or "")
            if kind == "ok" and value is not None:
                float_values.append(value)
            else:
                float_excluded += 1
    overview = build_overview(
        [row.values for row in project_table.rows] if project_table is not None else None,
        project_table.fields if project_table is not None else (),
        len(activities),
        float_values,
        float_excluded,
    )

    source = SourceInfo(
        filename=parsed.filename,
        sha256=parsed.sha256,
        byte_length=parsed.byte_length,
        encoding=parsed.encoding,
        projects=tuple(project_names),
        activity_count=len(activities),
        relationship_count=relationship_count,
        float_column=float_column,
        overview=overview,
    )
    return findings, source


def _classify_link(
    row: ParsedRow,
    projects: set[str],
    activities: dict[tuple[str, str], _Activity],
) -> _LinkEnds:
    succ_proj = row.values.get("proj_id", "")
    succ_id = row.values.get("task_id", "")
    pred_proj = row.values.get("pred_proj_id", "")
    pred_id = row.values.get("pred_task_id", "")
    blank = [
        label
        for label, value in (
            ("task_id", succ_id),
            ("proj_id", succ_proj),
            ("pred_task_id", pred_id),
            ("pred_proj_id", pred_proj),
        )
        if not value
    ]
    if blank:
        return _LinkEnds(
            "malformed",
            None,
            None,
            "malformed",
            "malformed",
            row,
            "Relationship is missing " + ", ".join(blank) + ".",
        )

    succ_key = (succ_proj, succ_id)
    pred_key = (pred_proj, pred_id)
    succ_state = _end_state(succ_key, projects, activities)
    pred_state = _end_state(pred_key, projects, activities)
    if "dangling" in (succ_state, pred_state):
        detail = _dangling_detail(succ_key, succ_state, pred_key, pred_state)
        return _LinkEnds("dangling", succ_key, pred_key, succ_state, pred_state, row, detail)
    if "unknown" in (succ_state, pred_state):
        detail = _unknown_detail(succ_key, succ_state, pred_key, pred_state)
        return _LinkEnds("unknown", succ_key, pred_key, succ_state, pred_state, row, detail)
    return _LinkEnds("resolved", succ_key, pred_key, succ_state, pred_state, row, "")


def _end_state(
    key: tuple[str, str],
    projects: set[str],
    activities: dict[tuple[str, str], _Activity],
) -> str:
    if key in activities:
        return "resolved"
    if key[0] in projects:
        return "dangling"
    return "unknown"


def _dangling_detail(
    succ_key: tuple[str, str],
    succ_state: str,
    pred_key: tuple[str, str],
    pred_state: str,
) -> str:
    parts: list[str] = []
    if pred_state == "dangling":
        parts.append(
            f"predecessor proj_id {pred_key[0]} task_id {pred_key[1]} is not an activity in this file"
        )
    if succ_state == "dangling":
        parts.append(
            f"successor proj_id {succ_key[0]} task_id {succ_key[1]} is not an activity in this file"
        )
    return (
        "Dangling relationship: "
        + "; ".join(parts)
        + ". The id was not matched to an activity in another file."
    )


def _unknown_detail(
    succ_key: tuple[str, str],
    succ_state: str,
    pred_key: tuple[str, str],
    pred_state: str,
) -> str:
    parts: list[str] = []
    if pred_state == "unknown":
        parts.append(
            f"predecessor project {pred_key[0]} is not in this file, so task_id {pred_key[1]} cannot be confirmed"
        )
    if succ_state == "unknown":
        parts.append(
            f"successor project {succ_key[0]} is not in this file, so task_id {succ_key[1]} cannot be confirmed"
        )
    return (
        "Unknown scope: "
        + "; ".join(parts)
        + ". This is not reported as a missing predecessor or successor, and it is not treated as a proven external dependency."
    )


def _open_ends(add, activity: _Activity, key: tuple[str, str], has_predecessor: set, has_successor: set) -> None:
    needs_predecessor = activity.task_type != "TT_Mile"
    needs_successor = activity.task_type != "TT_FinMile"
    label = _activity_label(activity)
    if needs_predecessor and key not in has_predecessor:
        add(
            "missing_predecessor",
            "TASK",
            activity.line,
            activity.code or activity.task_id,
            activity.name,
            f"{label} has no predecessor in this file." + _predecessor_clause(activity),
        )
    if needs_successor and key not in has_successor:
        add(
            "missing_successor",
            "TASK",
            activity.line,
            activity.code or activity.task_id,
            activity.name,
            f"{label} has no successor in this file." + _successor_clause(activity),
        )


def _activity_label(activity: _Activity) -> str:
    code = activity.code or activity.task_id
    if activity.name:
        return f"Activity {code} ({activity.name})"
    return f"Activity {code}"


def _predecessor_clause(activity: _Activity) -> str:
    if activity.task_type is None:
        return " The TASK header has no task_type column, so the start-milestone exception was not applied."
    if activity.task_type == "":
        return " task_type is blank, so the start-milestone exception was not applied."
    if activity.task_type == "TT_FinMile":
        return " A finish milestone (TT_FinMile) still needs a predecessor. Only the successor is exempt."
    return f" task_type {activity.task_type} is not the start-milestone exception TT_Mile."


def _successor_clause(activity: _Activity) -> str:
    if activity.task_type is None:
        return " The TASK header has no task_type column, so the finish-milestone exception was not applied."
    if activity.task_type == "":
        return " task_type is blank, so the finish-milestone exception was not applied."
    if activity.task_type == "TT_Mile":
        return " A start milestone (TT_Mile) still needs a successor. Only the predecessor is exempt."
    return f" task_type {activity.task_type} is not the finish-milestone exception TT_FinMile."


def _float_finding(add, activity: _Activity, column: str, threshold: Decimal) -> None:
    kind, value = _parse_hours(activity.float_raw or "")
    label = _activity_label(activity)
    if kind == "missing":
        add(
            "missing_float",
            "TASK",
            activity.line,
            activity.code or activity.task_id,
            activity.name,
            f"{label} has an empty {column}. Empty float is not treated as zero hours.",
        )
        return
    if kind == "nonnumeric":
        add(
            "nonnumeric_float",
            "TASK",
            activity.line,
            activity.code or activity.task_id,
            activity.name,
            f"{label} has {column} value {activity.float_raw!r}, which is not a number of hours. It is not treated as zero.",
        )
        return
    if kind == "nonfinite":
        add(
            "nonfinite_float",
            "TASK",
            activity.line,
            activity.code or activity.task_id,
            activity.name,
            f"{label} has {column} value {activity.float_raw!r}, which is not a finite number of hours. It is not treated as zero.",
        )
        return
    assert value is not None
    shown = format_hours(value)
    if value < 0:
        add(
            "negative_float",
            "TASK",
            activity.line,
            activity.code or activity.task_id,
            activity.name,
            f"{label} has {column} of {shown} hours, which is below 0. "
            "The value is the stored field, not a recomputed float, and it is not a day count.",
        )
        return
    if value > threshold:
        add(
            "high_float",
            "TASK",
            activity.line,
            activity.code or activity.task_id,
            activity.name,
            f"{label} has {column} of {shown} hours, which is greater than the high-float threshold of {format_hours(threshold)} hours. "
            "Equal to the threshold is not high. The value is the stored field, not a recomputed float, and it is not a day count.",
        )


def _parse_hours(raw: str) -> tuple[str, Decimal | None]:
    token = raw.strip()
    if token == "":
        return "missing", None
    if token.lower() in _NONFINITE_TOKENS:
        return "nonfinite", None
    try:
        value = Decimal(token)
    except InvalidOperation:
        return "nonnumeric", None
    if not value.is_finite():
        return "nonfinite", None
    return "ok", value
