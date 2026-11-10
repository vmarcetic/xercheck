# How the checker works

An XER file is tab-delimited text. `ERMHDR` is the export header. `%T` names a table, `%F` names its columns, each `%R` is one row, and `%E` ends the file. Rows are matched to columns by name, not by a fixed position.

A row with the wrong number of values is a **malformed row**. The finding names the file, the table, and the line, and that row is not used as an activity or a link. A marker other than `%T`, `%F`, `%R`, or `%E` is an **unsupported marker**. `PROJECT`, `TASK`, and `TASKPRED` are the tables the rules read. Any other table, such as `CALENDAR`, is **unsupported**: its rows are checked only for column count.

Activities are identified inside one file by `proj_id` and `task_id`. The same numbers in a second file are a different schedule. A repeated key in one file keeps the earlier row and flags the later row.

**Missing logic.** A relationship counts only when both ids are present. If either activity is missing inside a project that this file does contain, the link is **dangling**. If the predecessor or successor project is not in this file, the scope is **unknown**: the checker does not call that a missing link, and it does not claim the tie is a real external dependency. When `TASKPRED` itself is absent, or is missing the id columns, open ends are not guessed.

A normal activity needs one predecessor and one successor. `TT_Mile` (start milestone) does not need a predecessor, and it still needs a successor. `TT_FinMile` (finish milestone) does not need a successor, and it still needs a predecessor. `TT_WBS`, `TT_LOE`, a blank type, and every other type need both. A self-link satisfies both ends; loops are not a separate check.

**Float.** The P6 export column is `total_float_hr_cnt` (Total Float, hours). If that column is missing and `total_float_hr` is present, that alias is used, still as hours. Below 0 is negative. Strictly above the threshold is high. The default threshold is 160 hours, and it must be a finite number of hours, zero or greater. Empty, non-numeric, and non-finite values are reported as themselves and are not treated as zero. Nothing is divided by a calendar. Float is not recomputed.

## What each finding means, in plain English

These are the lines the page shows next to each check. They explain a finding; they do not change how it is decided.

- **Missing predecessor / Missing successor (missing links).** The activity has no predecessor or no successor, so its dates do not depend on the work around it. The critical path and float may be unreliable. A start milestone may have no predecessor and a finish milestone may have no successor; nothing else is exempt.
- **Negative float.** The activity is already pushing the project past its required finish or a constraint date. The value is the float P6 exported; it is not recalculated.
- **High float.** Total float is how long an activity can slip before it delays the project finish. The checker reads `total_float_hr_cnt` (working hours) and flags exported total float of more than 160 working hours (about four 40-hour weeks). Exactly 160 is not flagged. The threshold can be changed. High float is not always wrong: it often points to a missing successor or weak logic, but it can also be a real constraint or plenty of time.
- **Malformed row (broken row).** A line does not match its table's column list, or a marker is in the wrong place. The row is skipped.
- **Malformed link.** A `TASKPRED` row is missing one of its ids, so it cannot tie two activities. It is ignored.
- **Dangling link.** A link points to an activity id that is not in this file, although its project is. It does not count as logic for either end.
- **Unknown scope.** A link points to a project that is not in this file. It is not called a missing link and not treated as a proven external dependency.
- **Missing / non-numeric / non-finite float.** The total float cell is blank, not a number, or infinite/NaN. It is reported and never treated as zero.
- **Unsupported table.** A table such as `CALENDAR` that these checks do not read. Nothing is wrong with it; it is listed so you know it was seen.
- **Unsupported marker, unsupported field, missing table, duplicate activity, missing end marker, missing header.** Parts of the file that are odd or absent. The finding says which check could not run or which row was kept.

## The page

A left sidebar links to four sections of one page. **Overview** has the headline “Review the exported schedule.”, one panel per file (file name, project, encoding, short SHA256, data date) with four numbers, one bar chart, “Finding counts by check”, with the same counts as text under “Chart values”, and an executive brief written from the counts. **Schedule checks** has one card per logic/float check and a row for every file/data check, each with its plain-English meaning and a count. **Findings** is the table with file, line, table, check, activity, name, and the checker's reason; the filter narrows it in the browser. **Methodology** repeats this file in short form. Schedule text is escaped before it is placed in the HTML. Fonts are the system sans-serif.

## Overview numbers (display only)

| Number | XER field | Notes |
| --- | --- | --- |
| Exported finish | `PROJECT.scd_end_date` | The scheduled finish P6 stored at the last schedule run. Latest readable value across PROJECT rows. Shown as exported, P6 local time; the file has no time zone. Blank, unreadable, or absent shows “Not in export”. |
| Data date | `PROJECT.last_recalc_date` | Same handling. |
| Activities | `TASK` rows with `proj_id` and `task_id` | Duplicates removed the same way the checks do. Relationships are `TASKPRED` rows. |
| Zero / negative float | the checks' float column | Activities with readable stored float at or below 0 hours. All statuses are included; status is not read. |
| Median total float | the checks' float column | Median of readable stored values, in working hours. Blank and unreadable values are left out and counted. Not converted to days. |

On the two CC BY sample networks, each file has 32 activities and no malformed rows. In each, `A01` (`TT_Task`, line 49, 0 hours) has no predecessor and `A32` (`TT_Task`, line 77, 0 hours) has no successor. No stored float is negative or above 160 hours. Eight other tables in each file are listed as unsupported. The overview shows P01 exported finish 2019-06-18 08:00, P02 2019-06-04 08:00, data date 2018-12-20 00:00 for both, 21 (P01) and 22 (P02) of 32 activities at or below 0 hours of float, none negative, and a median total float of 0 hours in both.
