"""Display-only overview numbers and the plain-English UI text."""

from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from xercheck.check import ALL_CODES, check_named, check_paths
from xercheck.explain import EXPLANATIONS, meaning
from xercheck.html_report import render_form, render_html
from xercheck.overview import build_overview, latest_project_date, median, parse_xer_date

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "fixtures" / "public"
SYNTH = ROOT / "fixtures" / "synthetic"


class OverviewHelperTests(unittest.TestCase):
    def test_median(self) -> None:
        self.assertIsNone(median([]))
        self.assertEqual(median([Decimal("5")]), Decimal("5"))
        self.assertEqual(median([Decimal("8"), Decimal("-2"), Decimal("40")]), Decimal("8"))
        self.assertEqual(median([Decimal("0"), Decimal("16"), Decimal("40"), Decimal("8")]), Decimal("12"))

    def test_parse_xer_date(self) -> None:
        self.assertEqual(parse_xer_date("2019-06-18 08:00").hour, 8)
        self.assertIsNotNone(parse_xer_date("2019-06-18"))
        self.assertIsNone(parse_xer_date(""))
        self.assertIsNone(parse_xer_date("next tuesday"))

    def test_latest_project_date_never_invents(self) -> None:
        self.assertEqual(latest_project_date([], "scd_end_date")[0], None)
        text, note = latest_project_date(["", " "], "scd_end_date")
        self.assertIsNone(text)
        self.assertIn("blank", note)
        text, note = latest_project_date(["garbage"], "scd_end_date")
        self.assertIsNone(text)
        self.assertIn("could not be read", note)
        text, note = latest_project_date(
            ["2019-06-04 08:00", "2019-06-18 08:00", ""], "scd_end_date"
        )
        self.assertEqual(text, "2019-06-18 08:00")
        self.assertIn("latest of 2", note)
        self.assertIn("1 project row", note)

    def test_build_overview_without_float_or_project(self) -> None:
        ov = build_overview(None, (), 4, None, 0)
        self.assertIsNone(ov.exported_finish)
        self.assertIsNone(ov.data_date)
        self.assertIsNone(ov.median_float_hours)
        self.assertEqual(ov.zero_or_negative, 0)
        ov = build_overview([{"proj_id": "1"}], ("proj_id",), 0, [], 0)
        self.assertIn("not in this export", ov.finish_note)
        self.assertIsNone(ov.median_float_hours)

    def test_zero_negative_and_median_counts(self) -> None:
        values = [Decimal(v) for v in ("-8", "0", "0", "24", "200")]
        ov = build_overview(
            [{"scd_end_date": "2020-01-31 17:00", "last_recalc_date": "2020-01-01 08:00"}],
            ("scd_end_date", "last_recalc_date"),
            6,
            values,
            1,
        )
        self.assertEqual(ov.exported_finish, "2020-01-31 17:00")
        self.assertEqual(ov.data_date, "2020-01-01 08:00")
        self.assertEqual(ov.zero_or_negative, 3)
        self.assertEqual(ov.negative, 1)
        self.assertEqual(ov.median_float_hours, Decimal("0"))
        self.assertEqual(ov.float_values, 5)
        self.assertEqual(ov.float_excluded, 1)


class OverviewOnFilesTests(unittest.TestCase):
    def test_public_samples(self) -> None:
        report = check_paths([PUBLIC / "P01_CPM.xer", PUBLIC / "P02_CPM.xer"], Decimal("160"))
        p01, p02 = (source.overview for source in report.sources)
        self.assertEqual(p01.exported_finish, "2019-06-18 08:00")
        self.assertEqual(p02.exported_finish, "2019-06-04 08:00")
        self.assertEqual(p01.data_date, "2018-12-20 00:00")
        self.assertEqual((p01.activity_count, p01.float_values, p01.float_excluded), (32, 32, 0))
        self.assertEqual((p01.zero_or_negative, p01.negative), (21, 0))
        self.assertEqual((p02.zero_or_negative, p02.negative), (22, 0))
        self.assertEqual(p01.median_float_hours, Decimal("0"))
        self.assertEqual(p02.median_float_hours, Decimal("0"))
        # The overview does not change the findings.
        totals = report.counts()
        self.assertEqual(totals.get("missing_predecessor"), 2)
        self.assertEqual(totals.get("missing_successor"), 2)
        self.assertEqual(totals.get("negative_float", 0), 0)
        self.assertEqual(totals.get("high_float", 0), 0)

    def test_synthetic_without_dates_and_with_bad_float(self) -> None:
        name = "SYNTHETIC_float_and_rows.xer"
        report = check_named([(name, (SYNTH / name).read_bytes())], Decimal("160"))
        ov = report.sources[0].overview
        self.assertIsNone(ov.exported_finish)
        self.assertEqual(ov.float_values + ov.float_excluded, ov.activity_count)
        self.assertGreater(ov.float_excluded, 0)
        self.assertEqual(ov.negative, report.counts().get("negative_float", 0))
        page = render_html(report)
        self.assertIn("Not in export", page)
        self.assertIn("No date was invented", page)


class PlainEnglishUiTests(unittest.TestCase):
    def test_every_code_has_an_explanation(self) -> None:
        self.assertEqual(set(EXPLANATIONS), set(ALL_CODES))
        for code in ALL_CODES:
            self.assertTrue(meaning(code))

    def test_report_layout_and_required_copy(self) -> None:
        report = check_paths([PUBLIC / "P01_CPM.xer"], Decimal("160"))
        page = render_html(report)
        self.assertIn("Review the exported schedule.", page)
        for label in ("Exported finish", "Activities", "Zero / negative float", "Median total float"):
            self.assertIn(label, page)
        for anchor in ('id="overview"', 'id="checks"', 'id="findings"', 'id="methodology"'):
            self.assertIn(anchor, page)
        self.assertEqual(page.count("<svg "), 1)
        self.assertIn("so its dates do not depend on the work around it", page)
        self.assertIn("critical path and float may be unreliable", page)
        self.assertIn("already pushing the project past its required finish or a constraint date", page)
        self.assertIn("how long an activity can slip before it delays the project finish", page)
        self.assertIn("more than 160 working hours (about four 40-hour weeks)", page)
        self.assertIn("High float is not always wrong", page)
        self.assertIn("2019-06-18", page)
        self.assertIn("Executive brief", page)
        self.assertNotIn("Iowan", page)

    def test_custom_threshold_shows_without_week_hint(self) -> None:
        report = check_paths([PUBLIC / "P01_CPM.xer"], Decimal("80"))
        page = render_html(report)
        self.assertIn("more than 80 working hours.", page)
        self.assertNotIn("four 40-hour weeks)", page.split('id="checks"')[1].split('id="findings"')[0])

    def test_form_explains_checks(self) -> None:
        page = render_form()
        self.assertIn("Review the exported schedule.", page)
        self.assertIn("High float, hours", page)
        self.assertIn('value="160"', page)
        self.assertIn("Missing predecessor", page)
        self.assertIn("Negative float", page)


if __name__ == "__main__":
    unittest.main()
