"""Plain-English meaning of each finding type. Display text only.

These strings explain a finding. They do not decide one. The rules are in
``xercheck.check`` and are unchanged by anything here.
"""

from __future__ import annotations

from decimal import Decimal

# Codes that are about schedule logic and float. Everything else is about
# whether the file itself could be read.
SCHEDULE_CODES = (
    "missing_predecessor",
    "missing_successor",
    "negative_float",
    "high_float",
)

_MISSING_LINKS = (
    "so its dates do not depend on the work around it. "
    "The critical path and float may be unreliable."
)

# code -> (what it means, what to look at)
EXPLANATIONS: dict[str, tuple[str, str]] = {
    "missing_predecessor": (
        "Missing link: this activity has no predecessor, " + _MISSING_LINKS,
        "Add the logic that drives its start, or confirm it is the real project start. "
        "A start milestone (TT_Mile) is allowed to have no predecessor.",
    ),
    "missing_successor": (
        "Missing link: this activity has no successor, " + _MISSING_LINKS,
        "Tie it to the work it feeds, or confirm it is the real project finish. "
        "A finish milestone (TT_FinMile) is allowed to have no successor.",
    ),
    "negative_float": (
        "Negative float: the activity is already pushing the project past its "
        "required finish or a constraint date.",
        "Check the constraint or required finish it is measured against, and the "
        "driving logic in front of it. The value is the float P6 exported; the "
        "checker does not recalculate it.",
    ),
    "high_float": (
        "High float: total float is how long an activity can slip before it delays "
        "the project finish. The checker reads total_float_hr_cnt (working hours) "
        "and flags exported total float above the threshold.",
        "High float is not always wrong. It often points to a missing successor or "
        "weak logic, but it can also be a real constraint or plenty of time.",
    ),
    "malformed_row": (
        "Broken row: a line in the file does not match its table's column list "
        "(too many or too few values, or a marker in the wrong place).",
        "That row was skipped, so it is not used as an activity or a link. "
        "Re-export from P6 or check whether the file was edited by hand.",
    ),
    "malformed_link": (
        "Incomplete relationship: a TASKPRED row is missing one of the activity or "
        "project ids, so it cannot be tied to two activities.",
        "That relationship was ignored. Look at the line in TASKPRED.",
    ),
    "dangling_link": (
        "Dangling relationship: a link points to an activity id that is not in this "
        "file, even though its project is.",
        "The activity may have been deleted or filtered out of the export. "
        "The link does not count as logic for either end.",
    ),
    "unknown_scope": (
        "Unknown scope: a link points to a project that is not in this file, so the "
        "other end cannot be checked.",
        "This is not counted as a missing link and not treated as a proven external "
        "dependency. Export the other project too if you need it checked.",
    ),
    "missing_float": (
        "Blank float: the activity has no total float value in the export.",
        "Blank is not treated as zero. Reschedule in P6 and re-export if float should be there.",
    ),
    "nonnumeric_float": (
        "Unreadable float: the total float value is not a number.",
        "It is not treated as zero. Check the cell on that line.",
    ),
    "nonfinite_float": (
        "Unreadable float: the total float value is infinite or NaN.",
        "It is not treated as zero. Check the cell on that line.",
    ),
    "unsupported_table": (
        "Not used by these checks: the file has a table (for example CALENDAR or "
        "RSRC) that the checker does not read for logic or float.",
        "Nothing is wrong with it. Its rows were only checked for column count. "
        "It is listed so you know it was seen.",
    ),
    "unsupported_directive": (
        "Unknown marker: a line starts with a % marker other than %T, %F, %R or %E.",
        "The line was skipped. Usually a damaged or hand-edited file.",
    ),
    "unsupported_field": (
        "Missing column: a table the checks need is missing a column (for example "
        "task_type or total_float_hr_cnt).",
        "The check that needs that column was not run or ran without its exception. "
        "The finding says which one.",
    ),
    "missing_table": (
        "Missing table: PROJECT, TASK or TASKPRED is not in the file.",
        "Checks that need the table were not run. Nothing is guessed in its place.",
    ),
    "duplicate_activity": (
        "Duplicate activity: the same project and activity id appears twice.",
        "The first row is kept and the later one is ignored.",
    ),
    "missing_end_marker": (
        "No end marker: the file does not finish with %E, so it may be cut short.",
        "Tables above were still read. Re-export if the file looks truncated.",
    ),
    "missing_header": (
        "No export header: the file has no ERMHDR line.",
        "Tables were still read. A normal P6 export starts with ERMHDR.",
    ),
}


def meaning(code: str) -> str:
    return EXPLANATIONS.get(code, ("", ""))[0]


def advice(code: str) -> str:
    return EXPLANATIONS.get(code, ("", ""))[1]


def high_float_rule(threshold_hours: Decimal, shown: str) -> str:
    """One sentence about the active threshold, in working hours."""
    weeks = ""
    if threshold_hours == Decimal("160"):
        weeks = " (about four 40-hour weeks)"
    return (
        f"Flagged when exported total float is more than {shown} working hours{weeks}. "
        "Exactly the threshold is not flagged. The threshold can be changed."
    )
