#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests für fft_smoothing.py (nur Standardbibliothek + NumPy)."""

from __future__ import annotations

import contextlib
import math
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

import fft_smoothing as fs


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


class TestFilter(unittest.TestCase):
    def test_reduces_noise_and_preserves_signal(self) -> None:
        sample_rate = 200.0
        time = np.arange(0.0, 4.0, 1.0 / sample_rate)
        clean = np.sin(2.0 * math.pi * 4.0 * time)
        noisy = clean + 0.6 * np.random.default_rng(7).normal(size=time.size)

        smoothed, _, _ = fs.fft_lowpass(
            noisy, cutoff=0.1, kind="butterworth", order=4, pad_fraction=0.1
        )

        self.assertLess(rms(smoothed - clean), 0.5 * rms(noisy - clean))

    def test_ideal_cutoff_one_keeps_signal(self) -> None:
        signal = np.sin(np.linspace(0.0, 12.0, 200))
        smoothed, _, _ = fs.fft_lowpass(
            signal, cutoff=1.0, kind="ideal", pad_fraction=0.0, detrend=False
        )
        np.testing.assert_allclose(smoothed, signal, atol=1e-10)

    def test_linear_trend_is_preserved(self) -> None:
        trend = np.linspace(-3.0, 5.0, 300)
        noisy = trend + 0.4 * np.random.default_rng(3).normal(size=trend.size)
        smoothed, _, _ = fs.fft_lowpass(noisy, cutoff=0.02, pad_fraction=0.1)
        slope = np.polyfit(np.arange(trend.size), smoothed, 1)[0]
        expected = (trend[-1] - trend[0]) / (trend.size - 1)
        self.assertAlmostEqual(float(slope), float(expected), places=3)

    def test_invalid_cutoff(self) -> None:
        signal = np.zeros(20)
        with self.assertRaises(ValueError):
            fs.fft_lowpass(signal, cutoff=0.0)
        with self.assertRaises(ValueError):
            fs.fft_lowpass(signal, cutoff=1.5)

    def test_too_few_points(self) -> None:
        with self.assertRaises(ValueError):
            fs.fft_lowpass(np.arange(3.0), cutoff=0.2)


class TestDataPreparation(unittest.TestCase):
    def test_nan_values_are_interpolated(self) -> None:
        y = np.array([0.0, 1.0, np.nan, 3.0, 4.0])
        filled, count = fs._fill_nans(y)
        self.assertEqual(count, 1)
        self.assertAlmostEqual(float(filled[2]), 2.0)

    def test_uniform_grid_remains_untouched(self) -> None:
        x = np.linspace(0.0, 1.0, 50)
        y = np.cos(x)
        _, _, x_grid, y_grid, resampled, _ = fs.prepare_xy(x, y)
        self.assertFalse(resampled)
        np.testing.assert_array_equal(x_grid, x)
        np.testing.assert_array_equal(y_grid, y)

    def test_irregular_grid_is_resampled(self) -> None:
        x = np.sort(np.random.default_rng(2).uniform(0.0, 10.0, 100))
        y = np.sin(x)
        _, _, x_grid, _, resampled, _ = fs.prepare_xy(x, y)
        self.assertTrue(resampled)
        steps = np.diff(x_grid)
        self.assertLess(float(np.max(np.abs(steps - steps[0]))), 1e-9)

    def test_duplicate_x_values_are_averaged(self) -> None:
        x = np.array([0.0, 1.0, 1.0, 2.0, 3.0, 4.0])
        y = np.array([0.0, 2.0, 4.0, 6.0, 8.0, 10.0])
        x_orig, y_orig, _, _, _, _ = fs.prepare_xy(x, y)
        self.assertEqual(x_orig.size, 5)
        self.assertAlmostEqual(float(y_orig[1]), 3.0)


class TestMetadata(unittest.TestCase):
    def test_leading_comments_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text(
                "# Quelle: Testboje\n# Position: 54.0 N 7.0 E\nzeit,signal\n0,1\n1,2\n",
                encoding="utf-8",
            )
            comments = fs.read_leading_comments(path)
            self.assertEqual(comments, ["Quelle: Testboje", "Position: 54.0 N 7.0 E"])

    def test_comments_stop_at_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("zeit,signal\n0,1\n1,2\n", encoding="utf-8")
            self.assertEqual(fs.read_leading_comments(path), [])

    def test_comment_metadata_and_plain_lines(self) -> None:
        items = fs.split_comments(["NDBC-Bojendaten", "Station: 46001", "x-Einheit: h"])
        self.assertEqual(items[0], (None, "NDBC-Bojendaten"))
        metadata = fs.comment_metadata(["Station: 46001", "x-Einheit: h"])
        self.assertEqual(metadata["station"], "46001")
        self.assertEqual(metadata["x-einheit"], "h")

    def test_format_seconds(self) -> None:
        self.assertEqual(fs.format_seconds(600), "10 min")
        self.assertEqual(fs.format_seconds(3600), "1 h")
        self.assertEqual(fs.format_seconds(86400), "1 d")

    def test_output_csv_keeps_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.csv"
            fs.write_csv(
                path,
                [np.array([0.0, 1.0]), np.array([2.0, 3.0])],
                ["x", "y"],
                comments=["Quelle: Test", "", "# Filter: Gauß"],
            )
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0], "# Quelle: Test")
            self.assertEqual(lines[1], "#")
            self.assertEqual(lines[2], "# Filter: Gauß")
            self.assertEqual(lines[3], "x,y")
            self.assertEqual(lines[4], "0,2")


class TestInputOutput(unittest.TestCase):
    def test_load_semicolon_with_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text(
                "Zeit;Spannung\n0.5;1.5\n1.0;2.0\n1.5;2.5\n", encoding="utf-8"
            )
            x, y, header, delimiter = fs.load_data(path, delimiter=";")
            self.assertEqual(delimiter, ";")
            self.assertEqual(header, ["Zeit", "Spannung"])
            np.testing.assert_allclose(x, [0.5, 1.0, 1.5])
            np.testing.assert_allclose(y, [1.5, 2.0, 2.5])

    def test_load_single_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text("wert\n1\n2\n3\n4\n", encoding="utf-8")
            x, y, header, _ = fs.load_data(path)
            self.assertIsNone(x)
            self.assertEqual(header, ["wert"])
            np.testing.assert_allclose(y, [1, 2, 3, 4])

    def test_svg_is_well_formed(self) -> None:
        x = np.linspace(0.0, 1.0, 100)
        y = np.sin(x) + 0.1 * np.random.default_rng(1).normal(size=x.size)
        smoothed = np.sin(x)
        residual = y - smoothed

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "plot.svg"
            fs.write_svg_plot(
                path,
                x,
                y,
                smoothed,
                residual,
                title="Test",
                subtitle="Untertitel",
            )
            tree = ET.parse(path)
            root = tree.getroot()
            self.assertTrue(root.tag.endswith("svg"))
            self.assertEqual(len(root.findall(".//{*}polyline")), 3)


class TestOutputPaths(unittest.TestCase):
    def test_data_folder_is_mirrored_into_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            output = fs.default_output_path("data/ndbc/46001_WVHT.csv")
            self.assertEqual(output, Path("output/ndbc/46001_WVHT_smoothed.csv"))
            self.assertEqual(
                fs.default_plot_path(output), Path("output/ndbc/46001_WVHT.svg")
            )

    def test_input_outside_data_goes_to_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            output = fs.default_output_path("messdaten.csv")
            self.assertEqual(output, Path("output/messdaten_smoothed.csv"))

    def test_demo_writes_to_data_and_output_folders(self) -> None:
        with tempfile.TemporaryDirectory() as directory, contextlib.chdir(directory):
            self.assertEqual(fs.main(["--demo", "--quiet"]), 0)
            self.assertTrue(Path("data/demo/demo_input.csv").is_file())
            self.assertTrue(Path("output/demo/demo_smoothed.csv").is_file())
            self.assertTrue(Path("output/demo/demo.svg").is_file())


if __name__ == "__main__":
    unittest.main()
