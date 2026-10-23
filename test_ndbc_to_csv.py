#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für ndbc_to_csv.py (ohne Netzwerkzugriff)."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

import ndbc_to_csv as ndbc

SAMPLE = """\
#YY  MM DD hh mm WSPD WVHT
#yr  mo dy hr mn m/s    m
2026 10 23 19 40  7.0  1.2
2026 10 23 19 30  MM   MM
2026 10 23 19 20  8.0  1.3
2026 10 23 18 00 99.0  99.0
"""


class ParseNdbcTests(unittest.TestCase):
    def test_header_units_and_rows(self):
        header, units, rows = ndbc.parse_ndbc(SAMPLE)
        self.assertEqual(header, ["YY", "MM", "DD", "hh", "mm", "WSPD", "WVHT"])
        self.assertEqual(units, ["yr", "mo", "dy", "hr", "mn", "m/s", "m"])
        self.assertEqual(len(rows), 4)

    def test_missing_header_raises(self):
        with self.assertRaises(ValueError):
            ndbc.parse_ndbc("2026 10 23 19 40 7.0 1.2\n")

    def test_empty_file_raises(self):
        with self.assertRaises(ValueError):
            ndbc.parse_ndbc("#YY MM DD hh mm\n#yr mo dy hr mn\n")

    def test_timestamp_is_utc(self):
        _, _, rows = ndbc.parse_ndbc(SAMPLE)
        stamp = ndbc.to_datetime(rows[0])
        self.assertEqual(stamp, datetime(2026, 10, 23, 19, 40, tzinfo=timezone.utc))


class ValueTests(unittest.TestCase):
    def test_missing_marker(self):
        self.assertFalse(ndbc.is_valid_value("MM", "WVHT"))

    def test_sentinel_values_rejected(self):
        self.assertFalse(ndbc.is_valid_value("99.0", "WVHT"))
        self.assertFalse(ndbc.is_valid_value("9999.0", "PRES"))

    def test_plausible_values(self):
        self.assertTrue(ndbc.is_valid_value("1.2", "WVHT"))
        self.assertTrue(ndbc.is_valid_value("1013.2", "PRES"))

    def test_garbage_rejected(self):
        self.assertFalse(ndbc.is_valid_value("abc", "WSPD"))


class SegmentTests(unittest.TestCase):
    @staticmethod
    def pair(hour: int, minute: int = 0) -> tuple[datetime, float]:
        return datetime(2026, 1, 1, hour, minute, tzinfo=timezone.utc), 1.0

    def test_long_gap_splits(self):
        pairs = [self.pair(0), self.pair(0, 10), self.pair(0, 20), self.pair(5)]
        segments = ndbc.split_segments(pairs, None)
        self.assertEqual([len(segment) for segment in segments], [3, 1])

    def test_no_gap_keeps_one_segment(self):
        pairs = [self.pair(0), self.pair(0, 10), self.pair(0, 20)]
        self.assertEqual(len(ndbc.split_segments(pairs, None)), 1)

    def test_keep_gaps_disables_splitting(self):
        pairs = [self.pair(0), self.pair(5)]
        self.assertEqual(len(ndbc.split_segments(pairs, 0)), 1)

    def test_explicit_threshold(self):
        pairs = [self.pair(0), self.pair(0, 10), self.pair(1)]
        segments = ndbc.split_segments(pairs, 20)
        self.assertEqual([len(segment) for segment in segments], [2, 1])


class StationInfoTests(unittest.TestCase):
    TABLE = (
        "# STATION_ID | OWNER | TTYPE | HULL | NAME | PAYLOAD | LOCATION\n"
        "#\n"
        "46001|N|3-meter foam buoy w/ seal cage|3DV13|"
        "WESTERN GULF OF ALASKA  - 175NM SE of Kodiak, AK|SCOOP payload|"
        "56.296 N 148.027 W (56&#176;17'46\" N 148&#176;1'37\" W)|H|FZAK61.PAFC |\n"
    )

    def test_station_is_parsed(self):
        info = ndbc.parse_station_table(self.TABLE, "46001")
        self.assertEqual(info["name"], "WESTERN GULF OF ALASKA - 175NM SE of Kodiak, AK")
        self.assertEqual(info["type"], "3-meter foam buoy w/ seal cage")
        self.assertEqual(info["hull"], "3DV13")
        self.assertEqual(info["position"], "56.296° N, 148.027° W")

    def test_unknown_station_returns_empty(self):
        self.assertEqual(ndbc.parse_station_table(self.TABLE, "99999"), {})

    def test_variable_description(self):
        self.assertIn("Wellenhöhe", ndbc.describe_variable("WVHT"))
        self.assertEqual(ndbc.describe_variable("XYZ"), "")


class OutputPathTests(unittest.TestCase):
    def test_default_path_uses_data_ndbc(self):
        self.assertEqual(
            ndbc.default_output_path("46001", "WVHT"),
            Path("data/ndbc/46001_WVHT.csv"),
        )

    def test_default_path_includes_year(self):
        self.assertEqual(
            ndbc.default_output_path("46001", "WSPD", 2025),
            Path("data/ndbc/46001_WSPD_2025.csv"),
        )


if __name__ == "__main__":
    unittest.main()
