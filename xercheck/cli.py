"""Command line for the XER checker."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from xercheck.check import ALL_CODES, check_paths, parse_threshold
from xercheck.html_report import render_html, render_text
from xercheck.limits import InputError
from xercheck.server import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xercheck",
        description=(
            "Check Primavera P6 XER files for broken rows, missing logic, "
            "negative total float, and high total float."
        ),
    )
    parser.add_argument("files", nargs="*", type=Path, help="XER files to check")
    parser.add_argument(
        "--high-float-hours",
        default="160",
        help="Flag stored total float strictly above this many hours. Default: 160.",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Print only this finding code. The HTML report still lists every finding.",
    )
    parser.add_argument("--html", type=Path, help="Write an HTML report to this path.")
    parser.add_argument("--serve", action="store_true", help="Serve a local upload page.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8741)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.serve:
        if args.files:
            print("Do not pass files together with --serve.", file=sys.stderr)
            return 2
        serve(args.host, args.port)
        return 0
    if not args.files:
        parser.print_help(sys.stderr)
        return 2
    if args.only and args.only not in ALL_CODES:
        print(
            f"Unknown --only code {args.only!r}. Known codes: {', '.join(ALL_CODES)}",
            file=sys.stderr,
        )
        return 2
    try:
        threshold = parse_threshold(args.high_float_hours)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        report = check_paths(list(args.files), threshold)
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    text = render_text(report, args.only)
    sys.stdout.write(text)
    if args.html:
        args.html.write_text(render_html(report), encoding="utf-8")
        print(f"Wrote {args.html}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
