"""Parse a Primavera P6 XER file.

XER text is tab-delimited. A table starts with ``%T``, column names are the
next ``%F`` line, and each ``%R`` line is one row. ``%E`` ends the file.
``ERMHDR`` is the export header, not a table.

A row whose column count differs from the current ``%F`` line is malformed
and is not turned into a record. A table other than PROJECT, TASK, or
TASKPRED is unsupported: its rows are still counted for column mismatches,
and the checker does not read them as activities or logic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

SUPPORTED_TABLES = ("PROJECT", "TASK", "TASKPRED")


@dataclass(frozen=True)
class ParseIssue:
    code: str
    line: int | None
    table: str
    message: str


@dataclass(frozen=True)
class ParsedRow:
    line: int
    values: dict[str, str]


@dataclass
class ParsedTable:
    name: str
    header_line: int | None = None
    fields: tuple[str, ...] = ()
    rows: list[ParsedRow] = field(default_factory=list)


@dataclass
class ParsedFile:
    filename: str
    sha256: str
    byte_length: int
    encoding: str
    header: str | None
    tables: dict[str, ParsedTable]
    issues: list[ParseIssue]
    ended: bool


def decode_xer(data: bytes) -> tuple[str, str]:
    """Decode XER bytes as UTF-8, including a leading BOM, or as cp1252."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp1252"), "cp1252"


def parse_xer(data: bytes, filename: str) -> ParsedFile:
    text, encoding = decode_xer(data)
    tables: dict[str, ParsedTable] = {}
    issues: list[ParseIssue] = []
    current: str | None = None
    header: str | None = None
    ended = False

    def add(code: str, line: int | None, table: str, message: str) -> None:
        issues.append(ParseIssue(code, line, table, message))

    for lineno, line in enumerate(text.splitlines(), 1):
        if line.strip() == "":
            continue
        if ended:
            add(
                "malformed_row",
                lineno,
                "",
                "Line is after the %E end marker.",
            )
            continue
        if line.startswith("ERMHDR"):
            if header is None:
                header = line
            else:
                add("malformed_row", lineno, "", "File has a second ERMHDR line.")
            continue
        if not line.startswith("%"):
            add(
                "malformed_row",
                lineno,
                current or "",
                "Line is not ERMHDR and does not start with a % marker.",
            )
            continue

        parts = line.split("\t")
        tag = parts[0]
        cells = parts[1:]
        if tag == "%E":
            ended = True
            continue
        if tag == "%T":
            name = cells[0].strip() if cells else ""
            if not name:
                current = None
                add("malformed_row", lineno, "", "Table marker %T has no table name.")
                continue
            current = name
            tables.setdefault(name, ParsedTable(name))
            continue
        if tag == "%F":
            if current is None:
                add(
                    "malformed_row",
                    lineno,
                    "",
                    "Field header %F appears before any %T table marker.",
                )
                continue
            fields = tuple(cell.strip() for cell in cells)
            table = tables[current]
            if not fields or any(name == "" for name in fields):
                add(
                    "malformed_row",
                    lineno,
                    current,
                    f"Field header for {current} has an empty column name.",
                )
                continue
            if len(set(fields)) != len(fields):
                add(
                    "malformed_row",
                    lineno,
                    current,
                    f"Field header for {current} repeats a column name.",
                )
                continue
            if table.fields and table.fields != fields:
                add(
                    "malformed_row",
                    lineno,
                    current,
                    f"Field header for {current} does not match the earlier header on line {table.header_line}.",
                )
                continue
            if not table.fields:
                table.fields = fields
                table.header_line = lineno
            continue
        if tag == "%R":
            table = tables.get(current) if current else None
            if table is None or not table.fields:
                add(
                    "malformed_row",
                    lineno,
                    current or "",
                    "Data row %R appears before a field header for this table.",
                )
                continue
            if len(cells) != len(table.fields):
                add(
                    "malformed_row",
                    lineno,
                    current or "",
                    f"{current} row has {len(cells)} values but the header on line {table.header_line} has {len(table.fields)} columns.",
                )
                continue
            values = {
                column: cells[index].strip()
                for index, column in enumerate(table.fields)
            }
            table.rows.append(ParsedRow(lineno, values))
            continue
        if len(tag) == 2 and tag[1].isalpha():
            add(
                "unsupported_directive",
                lineno,
                current or "",
                f"Marker {tag} is not %T, %F, %R, or %E, so the line was skipped.",
            )
            continue
        add(
            "malformed_row",
            lineno,
            current or "",
            f"Unrecognised marker {tag!r}.",
        )

    if header is None:
        add("missing_header", None, "", "File has no ERMHDR line. Tables were still read.")
    if not ended:
        add(
            "missing_end_marker",
            None,
            "",
            "File has no %E end marker. Tables above it were still read.",
        )
    for name, table in tables.items():
        if name not in SUPPORTED_TABLES:
            add(
                "unsupported_table",
                table.header_line,
                name,
                f"Table {name} is not used for logic or float checks. Its rows were checked only for column count.",
            )
        if not table.fields:
            add(
                "malformed_row",
                None,
                name,
                f"Table {name} has no usable field header.",
            )

    return ParsedFile(
        filename=filename,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_length=len(data),
        encoding=encoding,
        header=header,
        tables=tables,
        issues=issues,
        ended=ended,
    )
