"""Rules, parser, HTML escaping, public-file smoke, and the local server."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from http.client import HTTPConnection
from pathlib import Path

from xercheck.check import check_named, check_paths, filter_findings, parse_threshold
from xercheck.html_report import render_html, render_text
from xercheck.limits import MAX_FILE_BYTES, InputError, read_limited
from xercheck.parser import parse_xer
from xercheck.server import CheckerHandler, evaluate_upload, parse_multipart, safe_filename
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "fixtures" / "public"
SYNTH = ROOT / "fixtures" / "synthetic"
P01_SHA = "b580b4fb384bef28529b28b530e13c9276157afcc1c00e395fce22b0b58953bc"
P02_SHA = "a945a7c55a88e4c78d75c4b0a24392f7dde7525b4ce8e6849d4a4c612482259f"


def load(name: str) -> bytes:
    return (SYNTH / name).read_bytes()


def codes(report, code: str) -> list[str]:
    return sorted(
        finding.activity_id for finding in report.findings if finding.code == code
    )


def count(report, code: str) -> int:
    return report.counts().get(code, 0)


class ThresholdTests(unittest.TestCase):
    def test_default_and_edges(self) -> None:
        self.assertEqual(parse_threshold("160"), Decimal("160"))
        self.assertEqual(parse_threshold(" 0 "), Decimal("0"))
        self.assertEqual(parse_threshold("160.0"), Decimal("160.0"))
        for raw in ("-1", "nan", "inf", "-inf", "Infinity", "nope", ""):
            with self.assertRaises(ValueError):
                parse_threshold(raw)


class SyntheticRuleTests(unittest.TestCase):
    def test_linked_start_and_finish_milestones_are_clean(self) -> None:
        report = check_named(
            [("SYNTHETIC_milestones_ok.xer", load("SYNTHETIC_milestones_ok.xer"))],
            Decimal("160"),
        )
        self.assertEqual(report.findings, [])
        self.assertEqual(report.sources[0].activity_count, 3)
        self.assertEqual(report.sources[0].float_column, "total_float_hr_cnt")

    def test_open_ends_and_milestone_exceptions(self) -> None:
        report = check_named(
            [("SYNTHETIC_open_ends.xer", load("SYNTHETIC_open_ends.xer"))],
            Decimal("160"),
        )
        self.assertEqual(
            codes(report, "missing_predecessor"),
            ["BLANKTYPE", "FM", "FM_WITH_SUCC", "LOE", "LOOSE", "SUM"],
        )
        self.assertEqual(
            codes(report, "missing_successor"),
            ["BLANKTYPE", "LOE", "LOOSE", "SM", "SM_WITH_PRED", "SUM"],
        )
        self.assertEqual(count(report, "negative_float"), 0)
        self.assertEqual(count(report, "high_float"), 0)
        self.assertEqual(count(report, "dangling_link"), 0)
        text = render_text(report)
        self.assertIn("still needs a successor", text)
        self.assertIn("still needs a predecessor", text)
        self.assertIn("TT_WBS", text)
        self.assertIn("TT_LOE", text)
        self.assertIn("task_type is blank", text)
        for clean in ("MID", "WORK", "END"):
            self.assertNotIn(clean, codes(report, "missing_predecessor"))
            self.assertNotIn(clean, codes(report, "missing_successor"))

    def test_float_threshold_missing_nonfinite_and_broken_rows(self) -> None:
        report = check_named(
            [("SYNTHETIC_float_and_rows.xer", load("SYNTHETIC_float_and_rows.xer"))],
            Decimal("160"),
        )
        self.assertEqual(codes(report, "negative_float"), ["NEG"])
        self.assertEqual(codes(report, "high_float"), ["HIGH", "HUGE"])
        self.assertEqual(codes(report, "missing_float"), ["BLANK"])
        self.assertEqual(codes(report, "nonfinite_float"), ["INF", "NAN"])
        self.assertEqual(codes(report, "nonnumeric_float"), ["TEXT"])
        self.assertNotIn("EQ", codes(report, "high_float"))
        self.assertNotIn("ZERO", codes(report, "negative_float"))
        self.assertNotIn("NEGZERO", codes(report, "negative_float"))
        self.assertNotIn("INF", codes(report, "high_float"))
        self.assertNotIn("NAN", codes(report, "negative_float"))
        self.assertEqual(count(report, "missing_predecessor"), 0)
        self.assertEqual(count(report, "missing_successor"), 0)
        self.assertGreaterEqual(count(report, "malformed_row"), 5)
        self.assertGreaterEqual(count(report, "unsupported_table"), 1)
        self.assertGreaterEqual(count(report, "unsupported_directive"), 1)
        self.assertNotIn("BAD", codes(report, "high_float") + codes(report, "negative_float"))
        self.assertNotIn("NOID", codes(report, "missing_predecessor"))
        huge = next(item for item in report.findings if item.activity_id == "HUGE")
        self.assertLess(len(huge.message), 500)
        self.assertIn("hours", huge.message)
        self.assertIn("not a day count", huge.message)
        blank = next(item for item in report.findings if item.activity_id == "BLANK")
        self.assertIn("not treated as zero", blank.message)
        nan = next(item for item in report.findings if item.activity_id == "NAN")
        self.assertIn("not a finite number of hours", nan.message)

    def test_exact_threshold_is_not_high(self) -> None:
        report = check_named(
            [("SYNTHETIC_float_and_rows.xer", load("SYNTHETIC_float_and_rows.xer"))],
            Decimal("160.5"),
        )
        self.assertNotIn("HIGH", codes(report, "high_float"))
        self.assertIn("HUGE", codes(report, "high_float"))

    def test_two_files_do_not_resolve_colliding_ids(self) -> None:
        report = check_named(
            [
                ("SYNTHETIC_scope_a.xer", load("SYNTHETIC_scope_a.xer")),
                ("SYNTHETIC_scope_b.xer", load("SYNTHETIC_scope_b.xer")),
            ],
            Decimal("160"),
        )
        dangling = [item for item in report.findings if item.code == "dangling_link"]
        unknown = [item for item in report.findings if item.code == "unknown_scope"]
        malformed = [item for item in report.findings if item.code == "malformed_link"]
        high = [item for item in report.findings if item.code == "high_float"]
        self.assertEqual(len(dangling), 1)
        self.assertIn("scope_a", dangling[0].filename)
        self.assertIn("task_id 77", dangling[0].message)
        self.assertEqual(len(unknown), 1)
        self.assertIn("project 9", unknown[0].message)
        self.assertIn("not treated as a proven external dependency", unknown[0].message)
        self.assertEqual(len(malformed), 1)
        self.assertIn("pred_task_id", malformed[0].message)
        self.assertEqual(len(high), 1)
        self.assertIn("scope_b", high[0].filename)
        self.assertEqual(high[0].activity_name, "Colliding id")
        self.assertEqual(count(report, "missing_predecessor"), 0)
        self.assertEqual(count(report, "missing_successor"), 0)
        self.assertEqual(report.sources[0].activity_count, 3)
        self.assertEqual(report.sources[1].activity_count, 4)

    def test_same_filename_is_not_one_project(self) -> None:
        first = load("SYNTHETIC_scope_a.xer")
        second = load("SYNTHETIC_scope_b.xer")
        report = check_named([("same.xer", first), ("same.xer", second)], Decimal("160"))
        self.assertEqual([source.filename for source in report.sources], ["same.xer#1", "same.xer#2"])
        dangling = [item for item in report.findings if item.code == "dangling_link"]
        self.assertEqual(len(dangling), 1)
        self.assertEqual(dangling[0].filename, "same.xer#1")


class InlineSemanticsTests(unittest.TestCase):
    def test_absent_relationship_table_is_unknown_not_open_ends(self) -> None:
        report = check_named([("no-links.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt",
            "%R\t1\t1\tA\tAlone\tTT_Task\t0",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(count(report, "missing_table"), 1)
        self.assertEqual(count(report, "missing_predecessor"), 0)
        self.assertEqual(count(report, "missing_successor"), 0)

    def test_empty_relationship_table_does_flag_open_ends(self) -> None:
        report = check_named([("empty-links.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt",
            "%R\t1\t1\tA\tAlone\tTT_Task\t0",
            "%T\tTASKPRED",
            "%F\ttask_pred_id\ttask_id\tpred_task_id\tproj_id\tpred_proj_id\tpred_type",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(codes(report, "missing_predecessor"), ["A"])
        self.assertEqual(codes(report, "missing_successor"), ["A"])

    def test_oracle_column_wins_over_alias(self) -> None:
        report = check_named([("both.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt\ttotal_float_hr",
            "%R\t1\t1\tA\tStart\tTT_Mile\t0\t-9",
            "%R\t2\t1\tB\tFinish\tTT_FinMile\t0\t-9",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%R\t2\t1\t1\t1",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(report.sources[0].float_column, "total_float_hr_cnt")
        self.assertEqual(count(report, "negative_float"), 0)
        self.assertEqual(report.findings, [])

    def test_alias_column_is_still_hours(self) -> None:
        report = check_named([("alias.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr",
            "%R\t1\t1\tA\tAlias\tTT_Mile\t-3",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(report.sources[0].float_column, "total_float_hr")
        self.assertEqual(codes(report, "negative_float"), ["A"])
        negative = next(item for item in report.findings if item.code == "negative_float")
        self.assertIn("total_float_hr", negative.message)
        self.assertIn("hours", negative.message)

    def test_missing_float_column_is_not_zero(self) -> None:
        report = check_named([("nofloat.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type",
            "%R\t1\t1\tA\tStart\tTT_Mile",
            "%R\t2\t1\tB\tFinish\tTT_FinMile",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%R\t2\t1\t1\t1",
            "%E",
        ]))], Decimal("160"))
        self.assertIsNone(report.sources[0].float_column)
        self.assertEqual(count(report, "unsupported_field"), 1)
        self.assertEqual(count(report, "missing_float"), 0)
        self.assertEqual(count(report, "negative_float"), 0)
        self.assertEqual(count(report, "missing_predecessor"), 0)
        self.assertEqual(count(report, "missing_successor"), 0)

    def test_missing_task_type_does_not_invent_a_milestone(self) -> None:
        report = check_named([("notype.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttotal_float_hr_cnt",
            "%R\t1\t1\tSM\tLooks like a start\t0",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(codes(report, "missing_predecessor"), ["SM"])
        self.assertEqual(codes(report, "missing_successor"), ["SM"])
        self.assertEqual(count(report, "unsupported_field"), 1)

    def test_self_link_satisfies_both_ends(self) -> None:
        report = check_named([("self.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt",
            "%R\t5\t1\tLOOP\tLoop\tTT_Task\t0",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%R\t5\t5\t1\t1",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(count(report, "missing_predecessor"), 0)
        self.assertEqual(count(report, "missing_successor"), 0)
        self.assertEqual(count(report, "dangling_link"), 0)

    def test_known_project_without_the_activity_is_dangling(self) -> None:
        report = check_named([("projects.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%R\t2\tOTHER",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt",
            "%R\t1\t1\tSM\tStart\tTT_Mile\t0",
            "%R\t2\t1\tA\tWork\tTT_Task\t0",
            "%R\t3\t1\tFM\tFinish\tTT_FinMile\t0",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%R\t2\t1\t1\t1",
            "%R\t3\t2\t1\t1",
            "%R\t2\t5\t1\t2",
            "%R\t2\t8\t1\t9",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(count(report, "dangling_link"), 1)
        self.assertEqual(count(report, "unknown_scope"), 1)
        self.assertIn("proj_id 2", _message(report, "dangling_link"))
        self.assertIn("project 9", _message(report, "unknown_scope"))
        self.assertEqual(count(report, "missing_predecessor"), 0)
        self.assertEqual(count(report, "missing_successor"), 0)

    def test_duplicate_activity_keeps_the_first_row(self) -> None:
        report = check_named([("dup.xer", _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt",
            "%R\t1\t1\tSM\tFirst\tTT_Mile\t0",
            "%R\t1\t1\tSM\tSecond\tTT_Mile\t-5",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%E",
        ]))], Decimal("160"))
        self.assertEqual(report.sources[0].activity_count, 1)
        self.assertEqual(count(report, "duplicate_activity"), 1)
        self.assertEqual(count(report, "negative_float"), 0)
        self.assertEqual(codes(report, "missing_successor"), ["SM"])
        self.assertEqual(count(report, "missing_predecessor"), 0)

    def test_cp1252_and_utf8_names(self) -> None:
        utf8 = _xer([
            "%T\tPROJECT",
            "%F\tproj_id\tproj_short_name",
            "%R\t1\tSYNTHETIC",
            "%T\tTASK",
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt",
            "%R\t1\t1\tU\tCafé béton\tTT_Mile\t0",
            "%T\tTASKPRED",
            "%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id",
            "%E",
        ])
        parsed = parse_xer(utf8, "utf8.xer")
        self.assertEqual(parsed.encoding, "utf-8")
        legacy = (
            "ERMHDR\t16.1\n%T\tTASK\n"
            "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttask_type\ttotal_float_hr_cnt\n"
            "%R\t1\t1\tC\tCaf"
        ).encode("ascii") + (
            b"\xe9\tTT_Mile\t0\n%T\tTASKPRED\n"
            b"%F\ttask_id\tpred_task_id\tproj_id\tpred_proj_id\n%E\n"
        )
        parsed_legacy = parse_xer(legacy, "legacy.xer")
        self.assertEqual(parsed_legacy.encoding, "cp1252")
        report = check_named([("legacy.xer", legacy)], Decimal("160"))
        self.assertIn("Café", render_text(report))
        self.assertIn("béton", render_text(check_named([("utf8.xer", utf8)], Decimal("160"))))

    def test_header_and_end_marker_notes(self) -> None:
        parsed = parse_xer(b"%T\tTASK\n%F\ttask_id\tproj_id\n%R\t1\t1\n", "bare.xer")
        codes_found = {issue.code for issue in parsed.issues}
        self.assertIn("missing_header", codes_found)
        self.assertIn("missing_end_marker", codes_found)

    def test_filter(self) -> None:
        report = check_named(
            [("SYNTHETIC_float_and_rows.xer", load("SYNTHETIC_float_and_rows.xer"))],
            Decimal("160"),
        )
        high = filter_findings(report.findings, "high_float")
        self.assertTrue(high)
        self.assertTrue(all(item.code == "high_float" for item in high))
        self.assertEqual(len(filter_findings(report.findings, "")), len(report.findings))


class HtmlAndServerTests(unittest.TestCase):
    def test_html_escapes_untrusted_names_and_svg_parses(self) -> None:
        report = check_named(
            [("SYNTHETIC_float_and_rows.xer", load("SYNTHETIC_float_and_rows.xer"))],
            Decimal("160"),
        )
        page = render_html(report)
        self.assertIn("Pour béton", page)
        self.assertIn("&lt;/script&gt;&lt;script&gt;alert(1)&lt;/script&gt;", page)
        self.assertNotIn("<script>alert(1)", page)
        self.assertNotIn("Ã©", page)
        self.assertNotIn("Traceback", page)
        self.assertIn('id="only"', page)
        self.assertIn("data-code=\"negative_float\"", page)
        match_start = page.index("<svg ")
        match_end = page.index("</svg>") + len("</svg>")
        ET.fromstring(page[match_start:match_end])
        self.assertIn("Finding counts by check", page)
        self.assertIn("not a P6 scheduling engine", page)

    def test_oversize_upload_and_bad_threshold_and_filename(self) -> None:
        status, page = evaluate_upload([("big.xer", b"x" * (MAX_FILE_BYTES + 1))], "160")
        self.assertEqual(status, 413)
        self.assertIn("byte cap", page)
        self.assertNotIn("Traceback", page)
        status, page = evaluate_upload([("ok.xer", load("SYNTHETIC_milestones_ok.xer"))], "nan")
        self.assertEqual(status, 400)
        self.assertIn("finite", page)
        status, page = evaluate_upload(
            [("../../tmp/evil.xer", load("SYNTHETIC_milestones_ok.xer"))],
            "160",
        )
        self.assertEqual(status, 200)
        self.assertNotIn("../", page)
        self.assertIn("evil.xer", page)
        self.assertEqual(safe_filename("../../tmp/evil.xer"), "evil.xer")
        self.assertEqual(safe_filename(""), "upload.xer")

    def test_http_get_and_post(self) -> None:
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), CheckerHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        host, port = httpd.server_address
        try:
            connection = HTTPConnection(host, port, timeout=5)
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("High float, hours", body)
            self.assertIn("160", body)
            boundary, payload = _multipart(
                [("high_float_hours", "160")],
                [("xer", "SYNTHETIC_milestones_ok.xer", load("SYNTHETIC_milestones_ok.xer"))],
            )
            connection = HTTPConnection(host, port, timeout=5)
            connection.request(
                "POST",
                "/",
                body=payload,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            response = connection.getresponse()
            page = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("<svg ", page)
            self.assertNotIn("Traceback", page)
            self.assertIn("SYNTHETIC_milestones_ok.xer", page)
            parts = parse_multipart(
                f"multipart/form-data; boundary={boundary}",
                payload,
            )
            self.assertEqual(parts[0][0], "high_float_hours")
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_read_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.xer"
            path.write_bytes(b"x" * 50)
            with self.assertRaises(InputError):
                read_limited(path, limit=10)


class PublicFileTests(unittest.TestCase):
    def test_two_licensed_files_smoke(self) -> None:
        paths = [PUBLIC / "P01_CPM.xer", PUBLIC / "P02_CPM.xer"]
        self.assertEqual(paths[0].read_bytes().__class__, bytes)
        report = check_paths(paths, Decimal("160"))
        self.assertEqual([source.sha256 for source in report.sources], [P01_SHA, P02_SHA])
        self.assertEqual([source.activity_count for source in report.sources], [32, 32])
        self.assertEqual([source.relationship_count for source in report.sources], [46, 47])
        self.assertEqual(
            [source.float_column for source in report.sources],
            ["total_float_hr_cnt", "total_float_hr_cnt"],
        )
        self.assertEqual(count(report, "malformed_row"), 0)
        self.assertEqual(count(report, "malformed_link"), 0)
        page = render_html(report)
        self.assertIn("P01_CPM.xer", page)
        self.assertIn("P02_CPM.xer", page)
        self.assertIn(P01_SHA, page)
        self.assertIn("hours", page)
        self.assertNotIn("Traceback", page)
        start = page.index("<svg ")
        end = page.index("</svg>") + len("</svg>")
        ET.fromstring(page[start:end])
        for finding in report.findings:
            if finding.code in {"negative_float", "high_float", "missing_float"}:
                self.assertIn("hours", finding.message)


class CommandTests(unittest.TestCase):
    def test_cli_smoke_and_bad_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "report.html"
            done = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "xercheck",
                    str(PUBLIC / "P01_CPM.xer"),
                    str(PUBLIC / "P02_CPM.xer"),
                    str(SYNTH / "SYNTHETIC_milestones_ok.xer"),
                    "--html",
                    str(html_path),
                    "--high-float-hours",
                    "160",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertNotIn("Traceback", done.stdout)
            self.assertNotIn("Traceback", done.stderr)
            self.assertIn("total_float_hr_cnt", done.stdout)
            page = html_path.read_text(encoding="utf-8")
            self.assertIn("<svg ", page)
            bad = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "xercheck",
                    str(SYNTH / "SYNTHETIC_milestones_ok.xer"),
                    "--high-float-hours",
                    "-5",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(bad.returncode, 2)
            self.assertIn("finite", bad.stderr)
            filtered = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "xercheck",
                    str(SYNTH / "SYNTHETIC_open_ends.xer"),
                    "--only",
                    "missing_predecessor",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(filtered.returncode, 0, filtered.stderr)
            self.assertIn("[missing_predecessor]", filtered.stdout)
            self.assertNotIn("[missing_successor]", filtered.stdout)


def _xer(lines: list[str]) -> bytes:
    body = ["ERMHDR\t16.1\t2026-01-01\tProject\txercheck\tSYNTHETIC\tdb\tProject Management\tUSD"]
    body.extend(lines)
    return ("\r\n".join(body) + "\r\n").encode("utf-8")


def _message(report, code: str) -> str:
    return next(item.message for item in report.findings if item.code == code)


def _multipart(fields: list[tuple[str, str]], files: list[tuple[str, str, bytes]]) -> tuple[str, bytes]:
    boundary = "----xercheckboundary"
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    for name, filename, data in files:
        chunks.append(
            (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + data
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return boundary, b"".join(chunks)


if __name__ == "__main__":
    unittest.main()
