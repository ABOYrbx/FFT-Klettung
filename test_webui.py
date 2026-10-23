#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für webui.py – vollständig ohne Netzwerkzugriff."""

from __future__ import annotations

import json
import math
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from urllib.parse import parse_qs

import webui


def make_ndbc_sample() -> str:
    """Kleiner NDBC-Ausschnitt: 3 Kopfzeilen, 30 gültige und 1 ungültige Zeile."""
    lines = [
        "#YY  MM DD hh mm WDIR WSPD  WVHT",
        "#yr  mo dy hr mn degT  m/s     m",
        "# Testdaten ohne echte NDBC-Verbindung",
    ]
    base = datetime(2026, 10, 22, tzinfo=timezone.utc)
    for index in range(25):
        stamp = base + timedelta(minutes=20 * index)
        value = 1.0 + 0.2 * math.sin(index / 3.0)
        lines.append(
            f"{stamp.year:4d} {stamp.month:02d} {stamp.day:02d} "
            f"{stamp.hour:02d} {stamp.minute:02d} 180 7.0 {value:5.2f}"
        )
    second = base + timedelta(minutes=20 * 24 + 180)
    for index in range(5):
        stamp = second + timedelta(minutes=20 * index)
        value = 1.1 + 0.1 * math.cos(index)
        lines.append(
            f"{stamp.year:4d} {stamp.month:02d} {stamp.day:02d} "
            f"{stamp.hour:02d} {stamp.minute:02d} 180 7.0 {value:5.2f}"
        )
    # Fehlender Messwert: wird übersprungen und als "skipped" gezählt.
    lines.append(f"{base.year} {base.month:02d} {base.day:02d} 00 00 180 7.0 MM")
    return "\n".join(lines) + "\n"


def make_tilt_csv() -> str:
    """Stündliche Kipp-Daten: 30 Werte, Lücke, 10 Werte, 2 ungültige Zeilen."""
    lines = [
        "Time[GMT],current_speed[cm/s](2m),current_direction[angular_degrees](2m),"
        "temperature[C](2m),current_u[cm/s](2m),current_v[cm/s](2m),"
        "signal_strength[db](2m),tilt[degrees](2m)",
    ]
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(30):
        stamp = base + timedelta(hours=index)
        value = 4.0 + 0.5 * math.sin(index / 4.0)
        lines.append(
            f"{stamp.strftime('%Y-%m-%d %H:%M')},10.0,180.0,8.0,0.0,0.0,"
            f"-30.0,{value:.2f}"
        )
    # Lücke von 6 Stunden trennt die Abschnitte.
    second = base + timedelta(hours=30 + 6)
    for index in range(10):
        stamp = second + timedelta(hours=index)
        value = 5.0 + 0.4 * math.cos(index / 3.0)
        lines.append(
            f"{stamp.strftime('%Y-%m-%d %H:%M')},10.0,180.0,8.0,0.0,0.0,"
            f"-30.0,{value:.2f}"
        )
    # Ungültige Neigungswerte: leer und unplausibel.
    lines.append("2026-01-05 00:00,10.0,180.0,8.0,0.0,0.0,-30.0,")
    lines.append("2026-01-05 01:00,10.0,180.0,8.0,0.0,0.0,-30.0,120.0")
    return "\n".join(lines) + "\n"


def make_upload_csv(rows: int = 40) -> str:
    lines = [
        "# Station: Testboje",
        "# Messgröße: Spannung",
        "# Einheit: V",
        "# x-Einheit: s",
        "# Bezugsquelle: https://example.org/data",
        "# Lizenz: CC0",
        "x,y",
    ]
    for index in range(rows):
        x = index * 0.1
        y = math.sin(2.0 * math.pi * 0.5 * x) + 0.05 * math.sin(
            2.0 * math.pi * 3.0 * x
        )
        lines.append(f"{x:.1f},{y:.6f}")
    return "\n".join(lines) + "\n"


class StationListTests(unittest.TestCase):
    def test_curated_station_list(self) -> None:
        self.assertEqual(len(webui.STATIONS), 12)
        payload = {"stations": [station.as_dict() for station in webui.STATIONS]}
        self.assertEqual(len(payload["stations"]), 12)
        for entry in payload["stations"]:
            self.assertEqual(
                set(entry), {"id", "name", "position", "region"}
            )
            self.assertRegex(entry["id"], r"^[A-Za-z0-9]{3,10}$")
            self.assertIn("°", entry["position"])

        first = payload["stations"][0]
        self.assertEqual(first["id"], "46001")
        self.assertEqual(
            first["name"], "WESTERN GULF OF ALASKA - 175NM SE of Kodiak, AK"
        )
        self.assertEqual(first["position"], "56.296° N, 148.027° W")
        self.assertEqual(first["region"], "Golf von Alaska")
        json.dumps(payload)


class ParameterTests(unittest.TestCase):
    def test_parse_bool(self) -> None:
        self.assertTrue(webui.parse_bool("1"))
        self.assertTrue(webui.parse_bool("true"))
        self.assertTrue(webui.parse_bool("TRUE"))
        self.assertFalse(webui.parse_bool("0"))
        self.assertFalse(webui.parse_bool("false"))
        with self.assertRaises(ValueError):
            webui.parse_bool("vielleicht")

    def test_defaults(self) -> None:
        query = webui.parse_data_query(
            parse_qs("station=46001", keep_blank_values=True)
        )
        self.assertFalse(query.demo)
        self.assertEqual(query.station, "46001")
        self.assertEqual(query.variable, "WVHT")
        self.assertIsNone(query.year)
        self.assertEqual(query.days, 30.0)
        self.assertEqual(query.cutoff, 0.1)
        self.assertEqual(query.filter_kind, "butterworth")
        self.assertEqual(query.order, 4)
        self.assertTrue(query.detrend)
        self.assertEqual(query.pad, 0.1)
        self.assertIsNone(query.max_gap_min)
        self.assertFalse(query.keep_gaps)

    def test_demo_ignores_station_and_year(self) -> None:
        query = webui.parse_data_query(
            parse_qs("demo=1&station=!!!&year=abc", keep_blank_values=True)
        )
        self.assertTrue(query.demo)
        self.assertIsNone(query.station)
        self.assertIsNone(query.year)

    def test_tilt_query(self) -> None:
        query = webui.parse_data_query(
            parse_qs("tilt=1&dataset=b0139&days=90", keep_blank_values=True)
        )
        self.assertTrue(query.tilt)
        self.assertFalse(query.demo)
        self.assertEqual(query.dataset, "B0139")
        self.assertIsNone(query.station)
        self.assertEqual(query.variable, "TILT")
        self.assertIsNone(query.year)
        self.assertEqual(query.days, 90.0)

    def test_tilt_query_defaults_and_errors(self) -> None:
        query = webui.parse_data_query(
            parse_qs("tilt=1", keep_blank_values=True)
        )
        self.assertEqual(query.dataset, "B0139")
        for query_string in (
            "tilt=1&dataset=B9999",
            "tilt=1&dataset=abc",
            "tilt=1&demo=1",
        ):
            with self.subTest(query=query_string):
                with self.assertRaises(ValueError):
                    webui.parse_data_query(
                        parse_qs(query_string, keep_blank_values=True)
                    )

    def test_invalid_values_are_rejected(self) -> None:
        cases = [
            "station=ab",
            "station=46001&cutoff=0",
            "station=46001&cutoff=1.1",
            "station=46001&order=9",
            "station=46001&order=0",
            "station=46001&days=-1",
            "station=46001&days=1001",
            "station=46001&pad=0.96",
            "station=46001&filter=foo",
            "station=46001&max_gap_min=0",
            "station=46001&detrend=ja",
            "station=46001&keep_gaps=2",
            "station=46001&year=1800",
            "station=46001&variable=",
            "",
        ]
        for query_string in cases:
            with self.subTest(query=query_string):
                with self.assertRaises(ValueError):
                    webui.parse_data_query(
                        parse_qs(query_string, keep_blank_values=True)
                    )


class NdbcPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = make_ndbc_sample()
        self.station_info = {
            "name": "TESTBOJE",
            "position": "56.296° N, 148.027° W",
            "type": "3-meter buoy",
        }

    def build(self, **overrides):
        kwargs = {
            "station": "46001",
            "variable": "WVHT",
            "days": 0.0,
            "cutoff": 0.1,
            "filter_kind": "butterworth",
            "order": 4,
            "detrend": True,
            "pad": 0.1,
            "max_gap_min": None,
            "keep_gaps": False,
        }
        kwargs.update(overrides)
        with mock.patch.object(
            webui.ndbc, "fetch_text", return_value=self.sample
        ) as fetch_text, mock.patch.object(
            webui.ndbc, "fetch_station_info", return_value=self.station_info
        ):
            result = webui.build_ndbc_dataset(**kwargs)
        return result, fetch_text

    def test_response_shape_and_metadata(self) -> None:
        result, fetch_text = self.build()
        self.assertEqual(set(result), {"meta", "series"})
        meta = result["meta"]
        series = result["series"]
        self.assertEqual(set(series), {"x", "original", "smoothed", "residual"})
        lengths = {len(values) for values in series.values()}
        self.assertEqual(lengths, {25})

        self.assertEqual(meta["kind"], "ndbc")
        self.assertEqual(meta["station"], "46001")
        self.assertEqual(meta["station_name"], "TESTBOJE")
        self.assertEqual(meta["position"], "56.296° N, 148.027° W")
        self.assertEqual(meta["station_type"], "3-meter buoy")
        self.assertEqual(meta["variable"], "WVHT")
        self.assertEqual(meta["unit"], "m")
        self.assertIn("Wellenhöhe", meta["description"])
        self.assertIn("/realtime2/46001.txt", meta["source_url"])
        self.assertEqual(meta["license"], "US-Bundesdaten (gemeinfrei)")
        self.assertEqual(meta["start"], "2026-10-22T00:00:00Z")
        self.assertEqual(meta["end"], "2026-10-22T08:00:00Z")
        self.assertEqual(meta["points"], 25)
        self.assertAlmostEqual(meta["duration_h"], 8.0, places=6)
        self.assertAlmostEqual(meta["sampling_min"], 20.0, delta=1e-4)
        self.assertAlmostEqual(meta["sampling_value"], 20.0, delta=1e-4)
        self.assertEqual(meta["sampling_unit"], "min")
        self.assertAlmostEqual(meta["max_gap_min"], 20.0, places=6)
        self.assertEqual(meta["skipped"], 1)
        self.assertEqual(meta["x_unit"], "h")
        self.assertEqual(meta["filter"], "butterworth")
        self.assertEqual(meta["filter_label"], "Butterworth (Ordnung 4)")
        self.assertEqual(meta["order"], 4)
        self.assertTrue(meta["detrend"])
        self.assertAlmostEqual(meta["pad"], 0.1)
        self.assertFalse(meta["resampled"])
        self.assertEqual(fetch_text.call_args.args[0].count("/realtime2/46001.txt"), 1)

        # fs = 1 / (20 min * 60) = 1/1200 Hz; cutoff_hz = cutoff * fs / 2
        expected_fs = 1.0 / (20.0 * 60.0)
        self.assertAlmostEqual(meta["cutoff_hz"], 0.1 * expected_fs / 2.0, delta=1e-9)
        self.assertAlmostEqual(meta["nyquist_hz"], expected_fs / 2.0, delta=1e-9)

        for values in series.values():
            self.assertTrue(all(math.isfinite(value) for value in values))
        self.assertEqual(set(meta["stats"]), {
            "rms_original",
            "rms_smoothed",
            "rms_residual",
            "removed_percent",
        })
        self.assertGreater(meta["stats"]["rms_original"], 0.0)
        self.assertGreaterEqual(meta["stats"]["removed_percent"], 0.0)
        json.dumps(result)

    def test_historical_url_is_used_for_year(self) -> None:
        result, fetch_text = self.build(year=2025, days=30.0)
        self.assertIn("/historical/stdmet/46001h2025.txt.gz", result["meta"]["source_url"])
        self.assertIn("/historical/stdmet/46001h2025.txt.gz", fetch_text.call_args.args[0])

    def test_gap_handling_keeps_longest_segment(self) -> None:
        result, _ = self.build()
        self.assertEqual(result["meta"]["points"], 25)
        self.assertEqual(result["meta"]["end"], "2026-10-22T08:00:00Z")

        kept, _ = self.build(keep_gaps=True)
        self.assertEqual(kept["meta"]["points"], 30)
        self.assertTrue(kept["meta"]["resampled"])
        self.assertGreater(kept["meta"]["duration_h"], 12.0)

    def test_missing_variable_raises(self) -> None:
        with self.assertRaises(ValueError) as context:
            self.build(variable="XYZ")
        self.assertIn("nicht vorhanden", str(context.exception))

    def test_variable_list(self) -> None:
        with mock.patch.object(
            webui.ndbc, "fetch_text", return_value=self.sample
        ), mock.patch.object(
            webui.ndbc, "fetch_station_info", return_value=self.station_info
        ):
            result = webui.build_variables("46001")
        self.assertEqual(result["station"], "46001")
        self.assertEqual(result["name"], "TESTBOJE")
        self.assertEqual(result["position"], "56.296° N, 148.027° W")
        self.assertEqual(result["station_type"], "3-meter buoy")
        ids = [variable["id"] for variable in result["variables"]]
        self.assertEqual(ids, ["WDIR", "WSPD", "WVHT"])
        wvht = result["variables"][-1]
        self.assertEqual(wvht["unit"], "m")
        self.assertIn("Wellenhöhe", wvht["description"])
        json.dumps(result)


class AvailabilityTests(unittest.TestCase):
    HISTORY = (
        '<a href="/download_data.php?filename=46001h2024.txt.gz">2024</a> '
        '<a href="/download_data.php?filename=46001h2023.txt.gz">2023</a> '
        '<a href="/download_data.php?filename=46001h2022.txt.gz">2022</a> '
        '<a href="/download_data.php?filename=46001w2024.txt.gz">2024</a>'
    )

    def setUp(self) -> None:
        webui.CACHE.clear()

    def tearDown(self) -> None:
        webui.CACHE.clear()

    def test_station_years_are_parsed_from_history(self) -> None:
        with mock.patch.object(
            webui.ndbc, "fetch_text", return_value=self.HISTORY
        ) as fetch_text:
            years = webui.fetch_station_years("46001")
        self.assertEqual(years, [2024, 2023, 2022])
        self.assertIn("station_history.php?station=46001", fetch_text.call_args.args[0])

    def test_station_years_skip_legacy_files(self) -> None:
        history = (
            '<a href="/download_data.php?filename=46001h2008.txt.gz">2008</a> '
            '<a href="/download_data.php?filename=46001h2007.txt.gz">2007</a> '
            '<a href="/download_data.php?filename=46001h2006.txt.gz">2006</a> '
            '<a href="/download_data.php?filename=46001h1972.txt.gz">1972</a>'
        )
        with mock.patch.object(
            webui.ndbc, "fetch_text", return_value=history
        ):
            years = webui.fetch_station_years("46001")
        self.assertEqual(years, [2008, 2007])

    def test_variable_ranges_use_only_valid_values(self) -> None:
        header, _units, rows = webui.ndbc.parse_ndbc(make_ndbc_sample())
        ranges = webui._variable_ranges(header, rows)
        self.assertEqual(set(ranges), {"WDIR", "WSPD", "WVHT"})
        wvht = ranges["WVHT"]
        self.assertEqual(wvht["start"], "2026-10-22T00:00:00Z")
        self.assertEqual(wvht["end"], "2026-10-22T12:20:00Z")
        self.assertEqual(wvht["points"], 30)
        self.assertEqual(wvht["max_days"], 1)

    def test_variable_list_contains_years_and_ranges(self) -> None:
        sample = make_ndbc_sample()

        def fake_fetch(url: str) -> str:
            if "station_history" in url:
                return self.HISTORY
            return sample

        with mock.patch.object(
            webui.ndbc, "fetch_text", side_effect=fake_fetch
        ), mock.patch.object(
            webui.ndbc, "fetch_station_info", return_value={}
        ):
            result = webui.build_variables("46001")

        self.assertEqual(result["years"], [2024, 2023, 2022])
        wvht = result["variables"][-1]
        self.assertEqual(wvht["range"]["points"], 30)
        self.assertEqual(wvht["range"]["max_days"], 1)
        json.dumps(result)


class DemoPipelineTests(unittest.TestCase):
    def test_demo_response(self) -> None:
        result = webui.build_demo_dataset()
        meta = result["meta"]
        series = result["series"]
        self.assertEqual(meta["kind"], "demo")
        self.assertEqual(meta["station_name"], "Demo")
        self.assertEqual(meta["variable"], "signal")
        self.assertEqual(meta["unit"], "")
        self.assertEqual(meta["x_unit"], "s")
        self.assertEqual(meta["points"], 600)
        self.assertEqual(len(series["x"]), 600)
        self.assertEqual(len(series["original"]), 600)
        self.assertEqual(len(series["smoothed"]), 600)
        self.assertEqual(len(series["residual"]), 600)
        self.assertEqual(meta["duration_h"], 3.0)
        self.assertAlmostEqual(meta["sampling_value"], 0.005, places=9)
        self.assertEqual(meta["sampling_unit"], "s")
        self.assertAlmostEqual(meta["sampling_min"], 0.005 / 60.0, places=12)
        self.assertAlmostEqual(meta["cutoff_hz"], 10.0, places=6)
        self.assertAlmostEqual(meta["nyquist_hz"], 100.0, places=6)
        self.assertEqual(meta["filter_label"], "Butterworth (Ordnung 4)")
        self.assertEqual(meta["skipped"], 0)
        self.assertTrue(all(math.isfinite(v) for v in series["smoothed"]))
        json.dumps(result)

    def test_demo_other_filter(self) -> None:
        result = webui.build_demo_dataset(
            cutoff=0.2, filter_kind="gaussian", order=2, detrend=False, pad=0.0
        )
        self.assertEqual(result["meta"]["filter"], "gaussian")
        self.assertEqual(result["meta"]["filter_label"], "Gauß")
        self.assertFalse(result["meta"]["detrend"])
        self.assertAlmostEqual(result["meta"]["pad"], 0.0)


class UploadPipelineTests(unittest.TestCase):
    def test_upload_response(self) -> None:
        result = webui.build_upload_dataset(
            make_upload_csv(), filename="test.csv"
        )
        meta = result["meta"]
        series = result["series"]
        self.assertEqual(meta["kind"], "upload")
        self.assertEqual(meta["station"], "Testboje")
        self.assertEqual(meta["station_name"], "Testboje")
        self.assertEqual(meta["variable"], "y")
        self.assertEqual(meta["unit"], "V")
        self.assertEqual(meta["description"], "Spannung")
        self.assertEqual(meta["source_url"], "https://example.org/data")
        self.assertEqual(meta["license"], "CC0")
        self.assertEqual(meta["x_unit"], "s")
        self.assertEqual(meta["points"], 40)
        self.assertEqual(len(series["x"]), 40)
        self.assertAlmostEqual(meta["sampling_min"], 0.1 / 60.0, places=12)
        self.assertAlmostEqual(meta["sampling_value"], 0.1, places=9)
        self.assertEqual(meta["sampling_unit"], "s")
        self.assertAlmostEqual(meta["cutoff_hz"], 0.5, places=9)
        self.assertAlmostEqual(meta["nyquist_hz"], 5.0, places=9)
        self.assertAlmostEqual(meta["duration_h"], 39 * 0.1 / 3600.0, places=9)
        self.assertEqual(meta["skipped"], 0)
        self.assertFalse(meta["resampled"])
        self.assertEqual(set(meta["stats"]), {
            "rms_original",
            "rms_smoothed",
            "rms_residual",
            "removed_percent",
        })
        json.dumps(result)

    def test_upload_without_metadata(self) -> None:
        csv_text = "x,y\n" + "\n".join(
            f"{index},{math.sin(index / 3.0)}" for index in range(20)
        )
        result = webui.build_upload_dataset(csv_text, filename="roh.csv")
        meta = result["meta"]
        self.assertEqual(meta["station"], "")
        self.assertEqual(meta["station_name"], "roh.csv")
        self.assertEqual(meta["x_unit"], "")
        self.assertIsNone(meta["sampling_min"])
        self.assertIsNone(meta["cutoff_hz"])
        self.assertIsNone(meta["duration_h"])

    def test_empty_upload_raises(self) -> None:
        with self.assertRaises(ValueError):
            webui.build_upload_dataset("   ")


class TiltPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = make_tilt_csv()

    def build(self, **overrides):
        kwargs = {
            "dataset": "B0139",
            "days": 0.0,
            "cutoff": 0.1,
            "filter_kind": "butterworth",
            "order": 4,
            "detrend": True,
            "pad": 0.1,
            "max_gap_min": None,
            "keep_gaps": False,
        }
        kwargs.update(overrides)
        with mock.patch.object(
            webui.ndbc, "fetch_text", return_value=self.sample
        ) as fetch_text:
            result = webui.build_tilt_dataset(**kwargs)
        return result, fetch_text

    def test_parse_tilt_csv(self) -> None:
        pairs, skipped = webui._parse_tilt_csv(self.sample)
        self.assertEqual(len(pairs), 40)
        self.assertEqual(skipped, 1)
        self.assertEqual(pairs[0][0].isoformat(), "2026-01-01T00:00:00+00:00")
        self.assertAlmostEqual(pairs[0][1], 4.0, places=6)

    def test_tilt_response_and_gap_handling(self) -> None:
        result, fetch_text = self.build()
        meta = result["meta"]
        series = result["series"]
        self.assertEqual(set(result), {"meta", "series"})
        self.assertEqual(set(series), {"x", "original", "smoothed", "residual"})
        lengths = {len(values) for values in series.values()}
        self.assertEqual(lengths, {30})

        self.assertEqual(meta["kind"], "tilt")
        self.assertEqual(meta["dataset"], "B0139")
        self.assertEqual(meta["station"], "B0139")
        self.assertIn("B0139", meta["station_name"])
        self.assertEqual(meta["variable"], "TILT")
        self.assertEqual(meta["unit"], "°")
        self.assertEqual(meta["start"], "2026-01-01T00:00:00Z")
        self.assertEqual(meta["end"], "2026-01-02T05:00:00Z")
        self.assertEqual(meta["points"], 30)
        self.assertAlmostEqual(meta["duration_h"], 29.0, places=6)
        self.assertAlmostEqual(meta["sampling_min"], 60.0, places=6)
        self.assertEqual(meta["sampling_unit"], "min")
        self.assertAlmostEqual(meta["max_gap_min"], 60.0, places=6)
        self.assertEqual(meta["skipped"], 1)
        self.assertEqual(meta["x_unit"], "h")
        self.assertIn("aanderaa.tilt", meta["source_url"])
        self.assertIn("B0139", fetch_text.call_args.args[0])
        self.assertIn("tilt_mean", meta["stats"])
        self.assertIn("tilt_max", meta["stats"])
        self.assertGreater(meta["stats"]["tilt_max"], meta["stats"]["tilt_mean"])
        self.assertTrue(all(math.isfinite(v) for v in series["smoothed"]))
        json.dumps(result)

    def test_tilt_keep_gaps_and_days(self) -> None:
        kept, _ = self.build(keep_gaps=True)
        self.assertEqual(kept["meta"]["points"], 40)
        self.assertGreater(kept["meta"]["duration_h"], 40.0)

        recent, _ = self.build(days=1.0)
        self.assertEqual(recent["meta"]["points"], 10)
        self.assertEqual(recent["meta"]["end"], "2026-01-02T21:00:00Z")

    def test_tilt_invalid_dataset_raises(self) -> None:
        with self.assertRaises(ValueError):
            webui.build_tilt_dataset(dataset="B9999")
        with self.assertRaises(ValueError):
            webui.build_tilt_dataset(dataset="foo")


class CatalogTests(unittest.TestCase):
    XML = """<?xml version="1.0" encoding="utf-8"?>
    <stations created="2026-10-23T21:40:03UTC" count="3">
      <station id="46001" lat="56.296" lon="-148.027" name="  Gulf of Alaska  "
               type="buoy" met="y" currents="n" waterquality="n" dart="n"/>
      <station id="41002" lat="32.0" lon="-75.0" name="South Hatteras"
               type="buoy" met="y" currents="y" waterquality="n" dart="n"/>
      <station id="bad id" lat="1.0" lon="2.0" name="Invalid" type="buoy"/>
    </stations>
    """

    def setUp(self) -> None:
        webui.CATALOG_CACHE.clear()

    def tearDown(self) -> None:
        webui.CATALOG_CACHE.clear()

    def test_active_stations_are_parsed(self) -> None:
        with mock.patch.object(
            webui.ndbc, "fetch_text", return_value=self.XML
        ):
            entries = webui._fetch_active_stations()
        self.assertEqual([entry["id"] for entry in entries], ["46001", "41002"])
        first = entries[0]
        self.assertEqual(first["kind"], "ndbc")
        self.assertEqual(first["name"], "Gulf of Alaska")
        self.assertEqual(first["position"], "56.296° N, 148.027° W")
        self.assertEqual(first["region"], "Golf von Alaska")
        self.assertIn("Meteo", first["tags"])
        second = entries[1]
        self.assertIn("Strömung", second["tags"])
        json.dumps(entries)

    def test_catalog_contains_live_tilt_and_links(self) -> None:
        with mock.patch.object(
            webui.ndbc, "fetch_text", return_value=self.XML
        ):
            catalog = webui.build_catalog()
        kinds = [entry["kind"] for entry in catalog["entries"]]
        self.assertEqual(kinds.count("ndbc"), 2)
        self.assertEqual(kinds.count("tilt"), len(webui.TILT_DATASETS))
        self.assertEqual(kinds.count("link"), len(webui.PUBLIC_LINKS))
        self.assertIsNone(catalog["warning"])
        tilt = next(
            entry for entry in catalog["entries"] if entry["kind"] == "tilt"
        )
        self.assertEqual(tilt["id"], "B0139")
        self.assertIn("Kipp-Daten", tilt["tags"])
        self.assertEqual(tilt["unit"], "°")
        json.dumps(catalog)

    def test_catalog_falls_back_to_curated_stations(self) -> None:
        with mock.patch.object(
            webui.ndbc,
            "fetch_text",
            side_effect=webui.urllib.error.URLError("offline"),
        ):
            catalog = webui.build_catalog()
        ndbc_entries = [
            entry for entry in catalog["entries"] if entry["kind"] == "ndbc"
        ]
        self.assertEqual(len(ndbc_entries), len(webui.STATIONS))
        self.assertIn("nicht erreichbar", catalog["warning"])
        self.assertEqual(
            len(catalog["entries"]),
            len(webui.STATIONS)
            + len(webui.TILT_DATASETS)
            + len(webui.PUBLIC_LINKS),
        )


if __name__ == "__main__":
    unittest.main()
