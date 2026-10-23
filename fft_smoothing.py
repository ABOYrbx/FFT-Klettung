#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rauschige Messdaten mit der FFT glätten (Tiefpass im Frequenzbereich).

Beispiele:
    python3 fft_smoothing.py --demo
    python3 fft_smoothing.py data/eigene/messdaten.csv -o output/glatt.csv --cutoff 0.08
    python3 fft_smoothing.py data/eigene/messdaten.csv --cutoff-hz 12 --fs 200

Das Programm benötigt nur NumPy. Plots werden als SVG geschrieben. Eingaben
liegen unter data/, Ergebnisse werden nach output/ geschrieben.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np

FILTER_NAMES = {
    "ideal": "Ideal (harte Grenze)",
    "gaussian": "Gauß",
    "butterworth": "Butterworth",
}


# ---------------------------------------------------------------------------
# Einlesen
# ---------------------------------------------------------------------------

def _detect_delimiter(line: str, requested: str) -> str | None:
    """Liefert das Trennzeichen oder None für beliebigen Leerraum."""
    if requested == "space":
        return None
    if requested == "tab":
        return "\t"
    if requested != "auto":
        return requested

    counts = {",": line.count(","), ";": line.count(";"), "\t": line.count("\t")}
    delimiter, count = max(counts.items(), key=lambda item: item[1])
    return delimiter if count else None


def _split_fields(line: str, delimiter: str | None) -> list[str]:
    if delimiter is None:
        return line.split()
    # csv.reader behandelt Anführungszeichen korrekt.
    return next(csv.reader([line], delimiter=delimiter))


def load_data(
    path: str | Path,
    delimiter: str = "auto",
    x_col: int = 0,
    y_col: int = -1,
) -> tuple[np.ndarray | None, np.ndarray, list[str] | None, str | None]:
    """Liest eine CSV-/Textdatei mit Zahlen.

    Rückgabe: (x oder None, y, Kopfzeile oder None, verwendetes Trennzeichen).
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = file_path.read_text(encoding="latin-1")

    data_lines = [
        (number, raw.strip())
        for number, raw in enumerate(text.splitlines(), start=1)
        if raw.strip() and not raw.lstrip().startswith("#")
    ]
    if not data_lines:
        raise ValueError(f"Die Datei {file_path} enthält keine Daten.")

    chosen = _detect_delimiter(data_lines[0][1], delimiter)

    header: list[str] | None = None
    rows: list[list[float]] = []
    width: int | None = None

    for line_number, line in data_lines:
        parts = [part.strip() for part in _split_fields(line, chosen)]
        try:
            values = [float(part) for part in parts]
        except ValueError:
            if header is None and not rows:
                header = parts  # erste Zeile ist eine Überschrift
                continue
            raise ValueError(
                f"Zeile {line_number}: Nicht-numerischer Wert in {line!r}."
            ) from None

        if width is None:
            width = len(values)
        elif len(values) != width:
            raise ValueError(
                f"Zeile {line_number}: {len(values)} Spalten statt {width}."
            )
        rows.append(values)

    if not rows:
        raise ValueError("Keine numerischen Datenzeilen gefunden.")

    data = np.asarray(rows, dtype=float)
    n_cols = data.shape[1]

    if n_cols == 1:
        return None, data[:, 0], header, chosen

    x_index = x_col % n_cols
    y_index = y_col % n_cols
    if x_index == y_index:
        raise ValueError("x- und y-Spalte dürfen nicht identisch sein.")

    return data[:, x_index], data[:, y_index], header, chosen


def read_leading_comments(path: str | Path, limit: int = 40) -> list[str]:
    """Liest die Kommentarzeilen am Dateianfang (ohne führendes '#').

    Solche Zeilen enthalten bei Dateien aus ndbc_to_csv.py die Herkunft der
    Messwerte (Station, Position, Messgröße, Zeitraum, Quelle).
    """
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = file_path.read_text(encoding="latin-1")

    comments: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if comments:
                break
            continue
        if not line.startswith("#"):
            break
        comments.append(line.lstrip("#").strip())
        if len(comments) >= limit:
            break
    return comments


def split_comments(comments: list[str]) -> list[tuple[str | None, str]]:
    """Trennt Kommentarzeilen in (Schlüssel, Wert); ohne ':' bleibt der Text."""
    items: list[tuple[str | None, str]] = []
    for line in comments:
        if ":" in line:
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if key and value and len(key) <= 40:
                items.append((key, value))
                continue
        items.append((None, line))
    return items


def comment_metadata(comments: list[str]) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in split_comments(comments)
        if key is not None
    }


X_UNIT_SECONDS = {
    "s": 1.0,
    "sek": 1.0,
    "sec": 1.0,
    "sekunde": 1.0,
    "sekunden": 1.0,
    "min": 60.0,
    "minute": 60.0,
    "minuten": 60.0,
    "h": 3600.0,
    "std": 3600.0,
    "stunde": 3600.0,
    "stunden": 3600.0,
}


def format_seconds(seconds: float) -> str:
    """Formatiert eine Dauer lesbar (ms, s, min, h, d)."""
    if seconds <= 0.0:
        return "0 s"
    # Gleitkomma-Rauschen an den Einheitengrenzen vermeiden (0.9999… → 1).
    seconds = float(f"{seconds:.9g}")
    if seconds < 1e-3:
        return f"{seconds * 1e6:.3g} µs"
    if seconds < 1.0:
        return f"{seconds * 1e3:.3g} ms"
    if seconds < 90.0:
        return f"{seconds:.3g} s"
    if seconds < 3600.0:
        return f"{seconds / 60.0:.3g} min"
    if seconds < 86400.0:
        return f"{seconds / 3600.0:.3g} h"
    return f"{seconds / 86400.0:.3g} d"


DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")


def default_output_path(input_path: str | Path) -> Path:
    """Leitet den Ausgabepfad aus der Eingabe ab.

    Liegt die Eingabe unter ``data/``, wird die Unterordnerstruktur unter
    ``output/`` gespiegelt: ``data/ndbc/46001_WVHT.csv`` wird zu
    ``output/ndbc/46001_WVHT_smoothed.csv``. Sonst landet die Ausgabe direkt
    in ``output/``.
    """
    path = Path(input_path)
    try:
        relative = path.resolve().relative_to(DATA_DIR.resolve())
    except ValueError:
        relative = Path(path.name)
    return OUTPUT_DIR / relative.parent / f"{relative.stem}_smoothed.csv"


def default_plot_path(output_path: str | Path) -> Path:
    """Diagrammname ohne ``_smoothed``, im selben Ordner wie die Ausgabe."""
    path = Path(output_path)
    stem = path.stem
    if stem.endswith("_smoothed"):
        stem = stem[: -len("_smoothed")]
    return path.with_name(f"{stem}.svg")


DEMO_INPUT_PATH = DATA_DIR / "demo" / "demo_input.csv"
DEMO_OUTPUT_PATH = OUTPUT_DIR / "demo" / "demo_smoothed.csv"


# ---------------------------------------------------------------------------
# Vorbereitung
# ---------------------------------------------------------------------------

def _fill_nans(values: np.ndarray) -> tuple[np.ndarray, int]:
    """Ersetzt NaN durch lineare Interpolation."""
    nan_count = int(np.count_nonzero(np.isnan(values)))
    if nan_count == 0:
        return values, 0
    if nan_count == values.size:
        raise ValueError("Alle y-Werte sind NaN.")
    index = np.arange(values.size)
    valid = ~np.isnan(values)
    filled = values.copy()
    filled[~valid] = np.interp(index[~valid], index[valid], values[valid])
    return filled, nan_count


def prepare_xy(
    x: np.ndarray | None, y: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, bool, int]:
    """Bereinigt x/y und legt – falls nötig – ein äquidistantes Raster an.

    Rückgabe: x_orig, y_orig, x_raster, y_raster, wurde_interpoliert, nan_anzahl
    """
    y, nan_count = _fill_nans(np.asarray(y, dtype=float))

    if x is None:
        x_orig = np.arange(y.size, dtype=float)
    else:
        x_orig = np.asarray(x, dtype=float)
        if x_orig.size != y.size:
            raise ValueError("x und y haben unterschiedliche Längen.")

        valid = ~np.isnan(x_orig)
        if not np.all(valid):
            x_orig = x_orig[valid]
            y = y[valid]
        if x_orig.size < 4:
            raise ValueError("Nach dem Entfernen ungültiger x-Werte sind zu wenige Punkte übrig.")

        order = np.argsort(x_orig, kind="stable")
        x_orig = x_orig[order]
        y = y[order]

        # Exakte Duplikate mitteln, damit np.interp sauber arbeitet.
        if np.any(np.diff(x_orig) == 0):
            unique_x, inverse = np.unique(x_orig, return_inverse=True)
            sums = np.bincount(inverse, weights=y)
            counts = np.bincount(inverse)
            x_orig = unique_x
            y = sums / counts

    if x_orig.size < 4:
        raise ValueError("Für die FFT werden mindestens 4 Datenpunkte benötigt.")

    steps = np.diff(x_orig)
    if np.any(steps <= 0):
        raise ValueError("Die x-Werte müssen streng aufsteigend sein.")

    dx = float(np.median(steps))
    deviation = float(np.max(np.abs(steps - dx)) / dx)
    resampled = deviation > 1e-3

    if resampled:
        # Anzahl der Rasterpunkte aus der mittleren Schrittweite ableiten.
        count = max(4, int(round((x_orig[-1] - x_orig[0]) / dx)) + 1)
        x_grid = np.linspace(x_orig[0], x_orig[-1], count)
        y_grid = np.interp(x_grid, x_orig, y)
    else:
        x_grid = x_orig
        y_grid = y

    return x_orig, y, x_grid, y_grid, resampled, nan_count


# ---------------------------------------------------------------------------
# FFT-Filter
# ---------------------------------------------------------------------------

def _linear_trend(values: np.ndarray) -> np.ndarray:
    if values.size < 3:
        return np.full(values.size, float(np.mean(values)))
    index = np.arange(values.size, dtype=float)
    coefficients = np.polyfit(index, values, 1)
    return np.polyval(coefficients, index)


def fft_lowpass(
    y: np.ndarray,
    cutoff: float,
    kind: str = "butterworth",
    order: int = 4,
    pad_fraction: float = 0.1,
    detrend: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Glättet y mit einem Tiefpass im Frequenzbereich.

    cutoff: Grenzfrequenz als Anteil der Nyquist-Frequenz (0 < cutoff <= 1).
    Rückgabe: geglättetes Signal, Frequenzachse (Zyklen/Sample), Filterantwort.
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 4:
        raise ValueError("Für die FFT werden mindestens 4 Datenpunkte benötigt.")
    if not 0.0 < cutoff <= 1.0:
        raise ValueError("--cutoff muss im Bereich (0, 1] liegen.")
    if kind not in FILTER_NAMES:
        raise ValueError(f"Unbekannter Filter: {kind}")
    if order < 1:
        raise ValueError("--order muss mindestens 1 sein.")

    if detrend:
        trend = _linear_trend(y)
    else:
        trend = np.zeros_like(y)
    work = y - trend

    # Spiegeln reduziert Sprünge an den Rändern (weniger Leckeffekte/Ringing).
    pad = int(round(pad_fraction * n))
    pad = max(0, min(pad, n - 1))
    if pad:
        work = np.pad(work, pad, mode="reflect")

    spectrum = np.fft.rfft(work)
    frequencies = np.fft.rfftfreq(work.size, d=1.0)  # 0 … 0.5 Zyklen/Sample
    cutoff_cycles = 0.5 * cutoff

    if kind == "ideal":
        response = (frequencies <= cutoff_cycles).astype(float)
    elif kind == "gaussian":
        # -3-dB-Punkt bei der Grenzfrequenz (wie beim Butterworth-Filter).
        response = np.exp(
            -0.5 * math.log(2.0) * (frequencies / cutoff_cycles) ** 2
        )
    else:
        with np.errstate(over="ignore", divide="ignore"):
            response = 1.0 / np.sqrt(1.0 + (frequencies / cutoff_cycles) ** (2 * order))

    smoothed = np.fft.irfft(spectrum * response, n=work.size)
    smoothed = smoothed[pad : pad + n] + trend
    return smoothed, frequencies, response


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def _format_number(value: float) -> str:
    return f"{value:.10g}"


def write_csv(
    path: str | Path,
    columns: list[np.ndarray],
    headers: list[str],
    delimiter: str = ",",
    comments: list[str] | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        for comment in comments or []:
            text = comment.strip().lstrip("#").strip()
            handle.write(f"# {text}\n" if text else "#\n")
        writer = csv.writer(handle, delimiter=delimiter, lineterminator="\n")
        writer.writerow(headers)
        for values in zip(*columns):
            writer.writerow([_format_number(float(value)) for value in values])


def _scale(value: float, low: float, high: float, pixel_low: float, pixel_high: float) -> float:
    if high == low:
        return 0.5 * (pixel_low + pixel_high)
    return pixel_low + (value - low) / (high - low) * (pixel_high - pixel_low)


def _polyline(
    x: np.ndarray,
    values: np.ndarray,
    x_range: tuple[float, float],
    y_range: tuple[float, float],
    left: float,
    right: float,
    top: float,
    bottom: float,
) -> str:
    return " ".join(
        f"{_scale(float(xi), x_range[0], x_range[1], left, right):.1f},"
        f"{_scale(float(vi), y_range[0], y_range[1], bottom, top):.1f}"
        for xi, vi in zip(x, values)
    )


def _ticks(
    low: float,
    high: float,
    count: int,
) -> list[float]:
    return [low + (high - low) * index / count for index in range(count + 1)]


def write_svg_plot(
    path: str | Path,
    x: np.ndarray,
    original: np.ndarray,
    smoothed: np.ndarray,
    residual: np.ndarray,
    *,
    title: str,
    subtitle: str,
    x_label: str = "x",
) -> None:
    """Schreibt ein einfaches SVG-Diagramm (ohne externe Bibliotheken)."""
    width, height = 1000, 630
    left, right = 82, 28
    top_top, top_bottom = 78, 390
    low_top, low_bottom = 445, 575

    # Sehr lange Reihen für die Zeichnung ausdünnen.
    step = max(1, int(math.ceil(x.size / 4000)))
    index = np.arange(0, x.size, step)
    if index[-1] != x.size - 1:
        index = np.append(index, x.size - 1)
    x_draw = x[index]
    original_draw = original[index]
    smoothed_draw = smoothed[index]
    residual_draw = residual[index]

    x_low, x_high = float(x_draw[0]), float(x_draw[-1])
    if x_low == x_high:
        x_low, x_high = x_low - 1.0, x_high + 1.0
    x_range = (x_low, x_high)

    combined = np.concatenate([original_draw, smoothed_draw])
    y_low, y_high = float(np.min(combined)), float(np.max(combined))
    margin = 0.06 * (y_high - y_low) if y_high > y_low else 1.0
    y_range = (y_low - margin, y_high + margin)

    res_low, res_high = float(np.min(residual_draw)), float(np.max(residual_draw))
    res_low = min(res_low, 0.0)
    res_high = max(res_high, 0.0)
    res_margin = 0.08 * (res_high - res_low) if res_high > res_low else 1.0
    res_range = (res_low - res_margin, res_high + res_margin)

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="32" font-size="19" font-weight="bold" fill="#222">'
        f"{escape(title)}</text>",
        f'<text x="{left}" y="54" font-size="12.5" fill="#555">{escape(subtitle)}</text>',
    ]

    grid_color = "#e4e7ec"
    axis_color = "#666666"

    for panel_top, panel_bottom, y_vals in (
        (top_top, top_bottom, y_range),
        (low_top, low_bottom, res_range),
    ):
        # horizontale Gitterlinien + y-Beschriftung
        for value in _ticks(y_vals[0], y_vals[1], 4):
            pixel = _scale(value, y_vals[0], y_vals[1], panel_bottom, panel_top)
            parts.append(
                f'<line x1="{left}" y1="{pixel:.1f}" x2="{width - right}" y2="{pixel:.1f}" '
                f'stroke="{grid_color}" stroke-width="1"/>'
            )
            parts.append(
                f'<text x="{left - 8}" y="{pixel + 4:.1f}" font-size="11" fill="#555" '
                f'text-anchor="end">{value:.4g}</text>'
            )

        # vertikale Gitterlinien
        for value in _ticks(x_range[0], x_range[1], 5):
            pixel = _scale(value, x_range[0], x_range[1], left, width - right)
            parts.append(
                f'<line x1="{pixel:.1f}" y1="{panel_top}" x2="{pixel:.1f}" y2="{panel_bottom}" '
                f'stroke="{grid_color}" stroke-width="1"/>'
            )

        # Rahmen
        parts.append(
            f'<rect x="{left}" y="{panel_top}" width="{width - right - left}" '
            f'height="{panel_bottom - panel_top}" fill="none" stroke="{axis_color}" '
            f'stroke-width="1"/>'
        )

    # x-Beschriftung unter dem unteren Panel
    for value in _ticks(x_range[0], x_range[1], 5):
        pixel = _scale(value, x_range[0], x_range[1], left, width - right)
        parts.append(
            f'<text x="{pixel:.1f}" y="{low_bottom + 20}" font-size="11" fill="#555" '
            f'text-anchor="middle">{value:.4g}</text>'
        )
    parts.append(
        f'<text x="{(left + width - right) / 2:.1f}" y="{height - 12}" font-size="12" '
        f'fill="#444" text-anchor="middle">{escape(x_label)}</text>'
    )

    # Nullinie im Residual-Panel
    zero_y = _scale(0.0, res_range[0], res_range[1], low_bottom, low_top)
    parts.append(
        f'<line x1="{left}" y1="{zero_y:.1f}" x2="{width - right}" y2="{zero_y:.1f}" '
        f'stroke="#999" stroke-width="1" stroke-dasharray="4 3"/>'
    )

    parts.append(
        f'<polyline fill="none" stroke="#aab0bb" stroke-width="1.2" opacity="0.75" '
        f'points="{_polyline(x_draw, original_draw, x_range, y_range, left, width - right, top_top, top_bottom)}"/>'
    )
    parts.append(
        f'<polyline fill="none" stroke="#1769aa" stroke-width="1.8" '
        f'points="{_polyline(x_draw, smoothed_draw, x_range, y_range, left, width - right, top_top, top_bottom)}"/>'
    )
    parts.append(
        f'<polyline fill="none" stroke="#d2691e" stroke-width="1.3" '
        f'points="{_polyline(x_draw, residual_draw, x_range, res_range, left, width - right, low_top, low_bottom)}"/>'
    )

    # Legende
    legend_x = 760
    legend_y = 100
    parts.append(
        f'<rect x="{legend_x - 10}" y="{legend_y - 17}" width="218" height="56" rx="5" '
        f'fill="#ffffff" fill-opacity="0.88" stroke="#dde1e7"/>'
    )
    for offset, color, label in (
        (0, "#aab0bb", "Original (verrauscht)"),
        (20, "#1769aa", "FFT-geglättet"),
    ):
        parts.append(
            f'<line x1="{legend_x}" y1="{legend_y + offset}" x2="{legend_x + 26}" '
            f'y2="{legend_y + offset}" stroke="{color}" stroke-width="2.4"/>'
        )
        parts.append(
            f'<text x="{legend_x + 32}" y="{legend_y + offset + 4}" font-size="12" '
            f'fill="#333">{escape(label)}</text>'
        )

    panel_labels = [
        (left, top_top - 10, "Signal"),
        (left, low_top - 10, "Rest (Original − geglättet)"),
    ]
    for panel_x, panel_y, label in panel_labels:
        parts.append(
            f'<text x="{panel_x}" y="{panel_y}" font-size="12" font-weight="bold" '
            f'fill="#333">{escape(label)}</text>'
        )

    parts.append("</svg>")
    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Ablauf
# ---------------------------------------------------------------------------

def _rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def _make_demo() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sample_rate = 200.0
    time = np.arange(0.0, 3.0, 1.0 / sample_rate)
    clean = np.sin(2.0 * math.pi * 3.0 * time) + 0.45 * np.sin(
        2.0 * math.pi * 8.0 * time + 0.5
    )
    noise = np.random.default_rng(42).normal(0.0, 0.55, time.size)
    return time, clean + noise, clean


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Glättet verrauschte Messdaten mit einem Tiefpass im "
            "Frequenzbereich (FFT)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  python3 fft_smoothing.py --demo\n"
            "  python3 fft_smoothing.py data/eigene/messdaten.csv --cutoff 0.08\n"
            "  python3 fft_smoothing.py data/eigene/messdaten.csv --cutoff-hz 12 --fs 200\n"
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="CSV-/Textdatei; ohne Angabe wird eine Demo erzeugt.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Zieldatei (Standard: output/…, Unterordner wie bei der Eingabe).",
    )
    parser.add_argument(
        "--x-col", type=int, default=0, help="Index der x-Spalte (Standard: 0)."
    )
    parser.add_argument(
        "--y-col", type=int, default=-1, help="Index der y-Spalte (Standard: letzte)."
    )
    parser.add_argument(
        "--delimiter",
        choices=["auto", ",", ";", "tab", "space"],
        default="auto",
        metavar="TRENNER",
        help="Spaltentrenner: auto, ',', ';', tab oder space (Standard: auto).",
    )
    parser.add_argument(
        "--cutoff",
        type=float,
        default=0.1,
        help="Grenzfrequenz als Anteil der Nyquist-Frequenz, 0 < c <= 1 (Standard: 0.1).",
    )
    parser.add_argument(
        "--cutoff-hz",
        type=float,
        help="Grenzfrequenz in Hz (benötigt --fs oder ein zeitliches x-Raster).",
    )
    parser.add_argument(
        "--fs",
        type=float,
        help="Abtastrate in Hz (nur für --cutoff-hz und die Anzeige).",
    )
    parser.add_argument(
        "--filter",
        choices=sorted(FILTER_NAMES),
        default="butterworth",
        help="Filterform (Standard: butterworth).",
    )
    parser.add_argument(
        "--order", type=int, default=4, help="Ordnung des Butterworth-Filters (Standard: 4)."
    )
    parser.add_argument(
        "--pad",
        type=float,
        default=0.1,
        help="Spiegel-Padding als Anteil der Datenlänge, 0 <= p < 1 (Standard: 0.1).",
    )
    parser.add_argument(
        "--no-detrend",
        action="store_true",
        help="Linearen Trend nicht vor der Filterung entfernen.",
    )
    parser.add_argument(
        "--plot",
        metavar="SVG",
        help="SVG-Plot an diesen Pfad schreiben (Standard: neben der Ausgabedatei).",
    )
    parser.add_argument(
        "--no-plot",
        dest="plot",
        action="store_false",
        help="Keinen SVG-Plot schreiben.",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Beispieldaten mit Rauschen verwenden."
    )
    parser.add_argument("--quiet", action="store_true", help="Keine Zusammenfassung ausgeben.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    if args.demo and args.input:
        raise ValueError("Bitte entweder eine Eingabedatei oder --demo angeben, nicht beides.")
    if args.fs is not None and args.fs <= 0:
        raise ValueError("--fs muss positiv sein.")
    if not 0.0 <= args.pad < 1.0:
        raise ValueError("--pad muss im Bereich [0, 1) liegen.")

    demo = args.demo or args.input is None
    truth: np.ndarray | None = None
    input_delimiter: str | None = None
    header: list[str] | None = None
    x_raw: np.ndarray | None
    y_raw: np.ndarray

    if demo:
        x_raw, y_raw, truth = _make_demo()
        header = ["zeit_s", "signal"]
        input_delimiter = ","
        source = "Demo (3 Hz + 8 Hz, Rauschen σ = 0.55, fs = 200 Hz)"
        comments: list[str] = []
    else:
        x_raw, y_raw, header, input_delimiter = load_data(
            args.input, args.delimiter, args.x_col, args.y_col
        )
        source = str(Path(args.input))
        comments = read_leading_comments(args.input)

    metadata = comment_metadata(comments)
    x_unit = metadata.get("x-einheit", "").strip()
    unit_scale = X_UNIT_SECONDS.get(x_unit.lower())

    x_orig, y_orig, x_grid, y_grid, resampled, nan_count = prepare_xy(x_raw, y_raw)

    dx = float(np.median(np.diff(x_grid)))
    fs_from_x_unit = 1.0 / (dx * unit_scale) if unit_scale else None
    fs_used = args.fs
    if fs_used is None and demo:
        fs_used = 1.0 / dx
    if fs_used is None and fs_from_x_unit is not None:
        fs_used = fs_from_x_unit
    if fs_used is None and args.cutoff_hz is not None and x_raw is not None:
        # Ohne --fs wird bei vorhandenem x-Raster eine Einheit in Sekunden angenommen.
        fs_used = 1.0 / dx

    cutoff = args.cutoff
    if args.cutoff_hz is not None:
        if args.cutoff_hz <= 0:
            raise ValueError("--cutoff-hz muss positiv sein.")
        if fs_used is None:
            raise ValueError(
                "Für --cutoff-hz wird --fs benötigt (oder ein x-Raster in Sekunden)."
            )
        cutoff = 2.0 * args.cutoff_hz / fs_used
    if not 0.0 < cutoff <= 1.0:
        raise ValueError(
            f"Die Grenzfrequenz entspricht {cutoff:.3g} × Nyquist und liegt "
            "damit außerhalb von (0, 1]."
        )

    smoothed_grid, _, _ = fft_lowpass(
        y_grid,
        cutoff=cutoff,
        kind=args.filter,
        order=args.order,
        pad_fraction=args.pad,
        detrend=not args.no_detrend,
    )

    if resampled:
        smoothed = np.interp(x_orig, x_grid, smoothed_grid)
    else:
        smoothed = smoothed_grid
    residual = y_orig - smoothed

    # Ausgabepfade: Eingaben unter data/ werden nach output/ gespiegelt.
    if args.output:
        output = Path(args.output)
    elif demo:
        output = DEMO_OUTPUT_PATH
    else:
        output = default_output_path(args.input)
    if not demo and args.input and output.resolve() == Path(args.input).resolve():
        raise ValueError("Ausgabedatei darf nicht die Eingabedatei überschreiben.")

    out_delimiter = ","
    if not demo and input_delimiter in {",", ";", "\t"}:
        out_delimiter = input_delimiter

    x_header = "x"
    if header and x_raw is not None:
        x_index = args.x_col % len(header)
        x_header = header[x_index]

    plot_path: Path | None = None
    if args.plot is not False:
        if isinstance(args.plot, str) and args.plot:
            plot_path = Path(args.plot)
        else:
            plot_path = default_plot_path(output)
        forbidden = {output.resolve()}
        if not demo and args.input:
            forbidden.add(Path(args.input).resolve())
        if plot_path.resolve() in forbidden:
            raise ValueError(
                "Der Plot-Pfad darf keine Daten- oder Eingabedatei überschreiben."
            )

    filter_label = FILTER_NAMES[args.filter]
    if args.filter == "butterworth":
        filter_label += f" (Ordnung {args.order})"

    cutoff_hz = cutoff * fs_used / 2.0 if fs_used is not None else None
    cutoff_text = f"{cutoff:.3g} × Nyquist"
    if cutoff_hz is not None:
        cutoff_text += f" = {cutoff_hz:.4g} Hz"
        cutoff_text += f" (Periode {format_seconds(1.0 / cutoff_hz)})"

    title = "FFT-Glättung"
    variable_label = metadata.get("messgröße", "").split("–")[0].strip()
    meta_unit = metadata.get("einheit", "").strip()
    if variable_label:
        title += f" – {variable_label}"
        if meta_unit and meta_unit.lower() != "keine":
            title += f" ({meta_unit})"

    x_label = x_header
    if unit_scale and x_header.lower() in {"x", "t", "time_h", "time_s", "time_min"}:
        x_label = f"Zeit [{x_unit}]"

    output_comments = ["Erzeugt mit fft_smoothing.py", f"Eingabe: {source}"]
    if comments:
        output_comments.append("")
        output_comments.append("Datenherkunft aus der Eingabedatei:")
        output_comments.extend(comments)
    output_comments.extend(
        [
            "",
            "Verarbeitung:",
            f"Filter: {filter_label}",
            f"Grenzfrequenz: {cutoff_text}",
            (
                f"Detrending: {'ja' if not args.no_detrend else 'nein'}, "
                f"Spiegel-Padding: {args.pad:.0%}"
            ),
            f"Spalten: {x_header}, original, smoothed, residual",
            "residual = original - smoothed",
        ]
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(
        output,
        [x_orig, y_orig, smoothed, residual],
        [x_header, "original", "smoothed", "residual"],
        delimiter=out_delimiter,
        comments=output_comments,
    )

    if demo:
        demo_input = DEMO_INPUT_PATH
        write_csv(demo_input, [x_orig, y_orig], [x_header, "signal"], delimiter=",")

    if plot_path is not None:
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        subtitle = (
            f"{filter_label}, Grenzfrequenz {cutoff_text}, "
            f"{'mit' if not args.no_detrend else 'ohne'} Detrending"
        )
        write_svg_plot(
            plot_path,
            x_orig,
            y_orig,
            smoothed,
            residual,
            title=title,
            subtitle=subtitle,
            x_label=x_label,
        )

    if not args.quiet:
        print("FFT-Glättung")
        print(f"  Eingabedatei:       {source}")

        if comments:
            print()
            print("  Datenherkunft (aus den Kommentarzeilen der Eingabe)")
            items = split_comments(comments)
            key_width = min(max((len(key) for key, _ in items if key), default=0), 20)
            for key, value in items:
                if key is None:
                    print(f"    {value}")
                else:
                    print(f"    {key + ':':<{key_width + 1}} {value}")

        print()
        print("  Analyse")
        print(f"  Datenpunkte:        {x_orig.size}")
        dx_text = f"{dx:.6g}"
        if unit_scale:
            dx_text += f" {x_unit} ({format_seconds(dx * unit_scale)})"
        fs_text = f"  (fs = {fs_used:.6g} Hz)" if fs_used is not None else ""
        print(f"  Abtastintervall:    dx = {dx_text}{fs_text}")
        if unit_scale:
            span = (x_orig[-1] - x_orig[0]) * unit_scale
            print(f"  Zeitumfang:         {format_seconds(span)}")
        if nan_count:
            print(f"  NaN-Werte:          {nan_count} interpoliert")
        if resampled:
            print(
                f"  Rasterpunkte:       {x_grid.size} "
                "(unregelmäßige x-Werte interpoliert)"
            )
        if fs_used is not None:
            nyquist = fs_used / 2.0
            print(
                f"  Nyquist-Frequenz:   {nyquist:.6g} Hz "
                f"(Periode {format_seconds(1.0 / nyquist)})"
            )
        print(f"  Filter:             {filter_label}")
        print(f"  Grenzfrequenz:      {cutoff_text}")
        print(f"  Detrending:         {'ja' if not args.no_detrend else 'nein'}")
        print(f"  Padding:            {args.pad:.0%} Spiegeln")
        print()

        # Vergleichsbasis: trendbereinigte Schwankung
        baseline = y_orig - (_linear_trend(y_orig) if not args.no_detrend else np.mean(y_orig))
        smoothed_baseline = smoothed - (
            _linear_trend(smoothed) if not args.no_detrend else np.mean(smoothed)
        )
        original_rms = _rms(baseline)
        smoothed_rms = _rms(smoothed_baseline)
        residual_rms = _rms(residual)
        ratio = 100.0 * residual_rms / original_rms if original_rms > 0 else 0.0
        print(f"  RMS Originalschwankung: {original_rms:.6g}")
        print(f"  RMS geglättet:          {smoothed_rms:.6g}")
        print(f"  RMS entfernt:           {residual_rms:.6g}")
        print(f"  Entfernter Anteil:      {ratio:.1f} % (RMS, inkl. Anteile nahe der Grenzfrequenz)")

        if truth is not None:
            before = _rms(y_orig - truth)
            after = _rms(smoothed - truth)
            improvement = 100.0 * (1.0 - after / before) if before > 0 else 0.0
            print()
            print(f"  Demo-Fehler vorher:     {before:.4f} (RMS gegenüber Wahrheit)")
            print(f"  Demo-Fehler nachher:    {after:.4f} (RMS gegenüber Wahrheit)")
            print(f"  Verbesserung:           {improvement:.1f} %")

        print()
        print(f"  Daten geschrieben:  {output}")
        if demo:
            print(f"  Demo-Eingabe:       {demo_input}")
        if plot_path is not None:
            print(f"  Diagramm:           {plot_path}")

    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return run(args)
    except (ValueError, OSError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
