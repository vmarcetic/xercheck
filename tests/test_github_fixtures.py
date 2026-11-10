"""The two GitHub-sourced demo files parse and raise the findings the docs describe."""

from __future__ import annotations

import hashlib
import unittest
from decimal import Decimal
from pathlib import Path

from xercheck.check import check_paths

ROOT = Path(__file__).resolve().parents[1]
GITHUB = ROOT / "fixtures" / "github"

EXPECTED_SHA256 = {
    "MDL4RA.xer": "6fbad1e78450a4a0349e1f1a1a1f6a6d7568757ef142f0ba8819ab619c8668a6",
    "p2_activities.xer": "88ca9af696771297b157e5958de2e1cf0358f5d15803abcca2c9de705e6b732f",
}


def _codes(report, code: str) -> list[str]:
    return sorted(f.activity_id for f in report.findings if f.code == code)


class GithubFixtureTests(unittest.TestCase):
    def test_bytes_match_sources(self) -> None:
        for name, digest in EXPECTED_SHA256.items():
            data = (GITHUB / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, name)

    def test_mdl4ra_high_float_and_dangling_start_milestones(self) -> None:
        report = check_paths([GITHUB / "MDL4RA.xer"], Decimal("160"))
        counts = report.counts()
        self.assertEqual(counts.get("high_float"), 52)
        self.assertEqual(
            _codes(report, "missing_successor"),
            ["C0900", "C2000", "C3000", "C4000", "C5000"],
        )
        for code in ("negative_float", "malformed_row", "dangling_link", "missing_float", "missing_predecessor"):
            self.assertEqual(counts.get(code, 0), 0, code)

    def test_p2_activities_negative_high_and_missing_float(self) -> None:
        report = check_paths([GITHUB / "p2_activities.xer"], Decimal("160"))
        self.assertEqual(_codes(report, "negative_float"), ["B5"])
        self.assertEqual(_codes(report, "high_float"), ["B1", "B2", "B3"])
        self.assertEqual(_codes(report, "missing_float"), ["B10", "B4", "S2"])
        counts = report.counts()
        for code in ("missing_predecessor", "missing_successor", "malformed_row", "dangling_link"):
            self.assertEqual(counts.get(code, 0), 0, code)


if __name__ == "__main__":
    unittest.main()
