#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lokale Web-Oberfläche für die FFT-Glättung von Messdaten.

Start:
    python3 webui.py
    python3 webui.py --host 127.0.0.1 --port 8000

Die Oberfläche wird aus dem Ordner ``web/`` geladen. Ist er noch nicht
vorhanden, liefert der Server einen kurzen deutschen Platzhalter. Die
JSON-Schnittstelle arbeitet ohne externe Pakete (nur NumPy wie die
bestehenden Module).

Wichtige interne Bausteine (auch für Tests):
    build_ndbc_dataset(...)   – NDBC-Daten laden, filtern, Statistiken
    build_demo_dataset(...)   – eingebaute Demo
    build_upload_dataset(...) – hochgeladene CSV-Daten verarbeiten
    parse_data_query(...)     – strenge Prüfung der GET-Parameter
"""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import re
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np

import fft_smoothing as fs
import ndbc_to_csv as ndbc

# ---------------------------------------------------------------------------
# Konstanten und Stationsliste
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
STATION_HISTORY_URL = "https://www.ndbc.noaa.gov/station_history.php"
# Ältere Standard-Meteorologie-Dateien (vor 2007) haben eine andere
# Kopfzeile ohne "#" und ohne Minuten-Spalte. Der Parser erwartet das
# moderne Format, daher werden diese Jahre nicht angeboten.
MIN_STDMET_YEAR = 2007
CACHE_TTL = 300.0
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
STATION_PATTERN = re.compile(r"^[A-Za-z0-9]{3,10}$")
VARIABLE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,15}$")
TIME_COLUMNS = {"YY", "MM", "DD", "hh", "mm"}
TIME_COLUMNS_UPPER = {name.upper() for name in TIME_COLUMNS}
DELIMITERS = {"auto", ",", ";", "tab", "space", "\t"}
NO_STORE_SUFFIXES = {".html", ".htm", ".js", ".mjs", ".css"}
TRUE_STRINGS = {"1", "true"}
FALSE_STRINGS = {"0", "false"}


@dataclass(frozen=True)
class Station:
    """Kuratierte Stationsangabe für die Auswahlliste."""

    id: str
    name: str
    latitude: float
    longitude: float
    region: str

    @property
    def position(self) -> str:
        return ndbc.format_position(self.latitude, self.longitude)

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "position": self.position,
            "region": self.region,
        }


STATIONS: tuple[Station, ...] = (
    Station(
        "46001",
        "WESTERN GULF OF ALASKA - 175NM SE of Kodiak, AK",
        56.296,
        -148.027,
        "Golf von Alaska",
    ),
    Station(
        "46002",
        "WEST OREGON - 275NM West of Coos Bay, OR",
        42.560,
        -130.523,
        "Oregon",
    ),
    Station(
        "46026",
        "SAN FRANCISCO - 18NM West of San Francisco, CA",
        37.750,
        -122.838,
        "Kalifornien",
    ),
    Station(
        "46042",
        "MONTEREY - 27NM WNW of Monterey, CA",
        36.787,
        -122.408,
        "Kalifornien",
    ),
    Station(
        "41008",
        "GRAYS REEF - 40 NM Southeast of Savannah, GA",
        31.400,
        -80.866,
        "Georgia",
    ),
    Station(
        "41010",
        "CANAVERAL EAST - 120NM East of Cape Canaveral",
        28.860,
        -78.478,
        "Florida",
    ),
    Station(
        "42001",
        "MID GULF - 180 nm South of Southwest Pass, LA",
        25.922,
        -89.638,
        "Golf von Mexiko",
    ),
    Station(
        "42002",
        "WEST GULF - 207 NM East of Brownsville, TX",
        25.950,
        -93.780,
        "Golf von Mexiko",
    ),
    Station(
        "44013",
        "BOSTON 16 NM East of Boston, MA",
        42.346,
        -70.651,
        "Neuengland",
    ),
    Station(
        "44025",
        "LONG ISLAND - 30 NM South of Islip, NY",
        40.258,
        -73.175,
        "New York",
    ),
    Station(
        "51001",
        "NORTHWESTERN HAWAII ONE - 188 NM NW of Kauai Island, HI",
        24.475,
        -162.030,
        "Hawaii",
    ),
    Station(
        "51002",
        "SOUTHWEST HAWAII - 215NM SSW of Hilo, HI",
        17.070,
        -157.755,
        "Hawaii",
    ),
)
STATIONS_BY_ID = {station.id: station for station in STATIONS}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class TTLCache:
    """Kleiner thread-sicherer Cache mit Ablaufzeit (Standard: 300 s)."""

    def __init__(self, ttl: float = CACHE_TTL) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._items: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires <= now:
                del self._items[key]
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


CACHE = TTLCache()


# ---------------------------------------------------------------------------
# Parameterprüfung
# ---------------------------------------------------------------------------

def parse_bool(value: str, name: str = "Wert") -> bool:
    """Wandelt 1/0/true/false (auch groß geschrieben) in bool um."""
    text = str(value).strip().lower()
    if text in TRUE_STRINGS:
        return True
    if text in FALSE_STRINGS:
        return False
    raise ValueError(
        f"Ungültiger Wert für {name}: {value!r} (erlaubt: 1, 0, true, false)."
    )


def validate_station(station: str) -> str:
    text = str(station).strip().upper()
    if not STATION_PATTERN.fullmatch(text):
        raise ValueError(
            "Ungültige Stationskennung. Erlaubt sind 3 bis 10 Buchstaben oder Ziffern."
        )
    return text


def validate_variable(variable: str) -> str:
    text = str(variable).strip().upper()
    if not VARIABLE_PATTERN.fullmatch(text):
        raise ValueError(
            "Ungültige Messgröße. Erlaubt sind Buchstaben, Ziffern und Unterstriche."
        )
    return text


def validate_filter_name(filter_kind: str) -> str:
    text = str(filter_kind).strip().lower()
    if text not in fs.FILTER_NAMES:
        raise ValueError(
            "Unbekannter Filter. Erlaubt: " + ", ".join(sorted(fs.FILTER_NAMES)) + "."
        )
    return text


def _single_param(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name)
    if not values:
        return None
    if len(values) > 1:
        raise ValueError(f"Parameter {name!r} darf nur einmal angegeben werden.")
    return values[0]


def _float_param(
    params: dict[str, list[str]],
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive_minimum: bool = False,
    exclusive_maximum: bool = False,
) -> float:
    raw = _single_param(params, name)
    if raw is None:
        return default
    if not raw.strip():
        raise ValueError(f"Parameter {name!r} ist leer.")
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"Parameter {name!r} muss eine Zahl sein.") from None
    if not math.isfinite(value):
        raise ValueError(f"Parameter {name!r} muss endlich sein.")
    if minimum is not None:
        if exclusive_minimum and value <= minimum:
            raise ValueError(f"Parameter {name!r} muss größer als {minimum:g} sein.")
        if not exclusive_minimum and value < minimum:
            raise ValueError(f"Parameter {name!r} muss mindestens {minimum:g} sein.")
    if maximum is not None:
        if exclusive_maximum and value >= maximum:
            raise ValueError(f"Parameter {name!r} muss kleiner als {maximum:g} sein.")
        if not exclusive_maximum and value > maximum:
            raise ValueError(f"Parameter {name!r} darf höchstens {maximum:g} sein.")
    return value


def _int_param(
    params: dict[str, list[str]],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = _single_param(params, name)
    if raw is None:
        return default
    if not raw.strip():
        raise ValueError(f"Parameter {name!r} ist leer.")
    try:
        value = int(raw, 10)
    except ValueError:
        raise ValueError(f"Parameter {name!r} muss eine ganze Zahl sein.") from None
    if minimum is not None and value < minimum:
        raise ValueError(f"Parameter {name!r} muss mindestens {minimum} sein.")
    if maximum is not None and value > maximum:
        raise ValueError(f"Parameter {name!r} darf höchstens {maximum} sein.")
    return value


@dataclass(frozen=True)
class DataQuery:
    """Geprüfte Parameter für GET /api/data."""

    demo: bool
    station: str | None
    variable: str
    year: int | None
    days: float
    cutoff: float
    filter_kind: str
    order: int
    detrend: bool
    pad: float
    max_gap_min: float | None
    keep_gaps: bool

    def cache_key(self) -> tuple[Any, ...]:
        return (
            "data",
            self.demo,
            self.station,
            self.variable,
            self.year,
            self.days,
            self.cutoff,
            self.filter_kind,
            self.order,
            self.detrend,
            self.pad,
            self.max_gap_min,
            self.keep_gaps,
        )


def parse_data_query(params: dict[str, list[str]]) -> DataQuery:
    """Prüft alle Parameter von GET /api/data streng."""
    demo_raw = _single_param(params, "demo")
    demo = parse_bool(demo_raw, "demo") if demo_raw is not None else False

    if demo:
        station: str | None = None
        variable = "signal"
        year: int | None = None
    else:
        station_raw = _single_param(params, "station")
        if station_raw is None:
            raise ValueError("Parameter 'station' fehlt (oder demo=1 verwenden).")
        station = validate_station(station_raw)
        variable_raw = _single_param(params, "variable")
        variable = validate_variable(variable_raw if variable_raw is not None else "WVHT")
        year_raw = _single_param(params, "year")
        year = (
            _int_param(params, "year", 0, minimum=1900, maximum=2100)
            if year_raw is not None
            else None
        )

    days = _float_param(params, "days", 30.0, minimum=0.0, maximum=1000.0)
    cutoff = _float_param(
        params,
        "cutoff",
        0.1,
        minimum=0.0,
        maximum=1.0,
        exclusive_minimum=True,
    )
    filter_raw = _single_param(params, "filter")
    filter_kind = validate_filter_name(
        filter_raw if filter_raw is not None else "butterworth"
    )
    order = _int_param(params, "order", 4, minimum=1, maximum=8)
    detrend_raw = _single_param(params, "detrend")
    detrend = parse_bool(detrend_raw, "detrend") if detrend_raw is not None else True
    pad = _float_param(params, "pad", 0.1, minimum=0.0, maximum=0.95)
    max_gap_raw = _single_param(params, "max_gap_min")
    max_gap_min = (
        _float_param(
            params,
            "max_gap_min",
            0.0,
            minimum=0.0,
            exclusive_minimum=True,
        )
        if max_gap_raw is not None
        else None
    )
    keep_gaps_raw = _single_param(params, "keep_gaps")
    keep_gaps = (
        parse_bool(keep_gaps_raw, "keep_gaps") if keep_gaps_raw is not None else False
    )

    return DataQuery(
        demo=demo,
        station=station,
        variable=variable,
        year=year,
        days=days,
        cutoff=cutoff,
        filter_kind=filter_kind,
        order=order,
        detrend=detrend,
        pad=pad,
        max_gap_min=max_gap_min,
        keep_gaps=keep_gaps,
    )


@dataclass(frozen=True)
class UploadRequest:
    """Geprüfter Inhalt von POST /api/upload."""

    filename: str
    csv_text: str
    cutoff: float
    filter_kind: str
    order: int
    detrend: bool
    pad: float
    x_col: int
    y_col: int
    delimiter: str


def _json_bool(payload: dict[str, Any], key: str, default: bool) -> bool:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        return parse_bool(value, key)
    raise ValueError(f"Feld {key!r} muss true/false oder 1/0 sein.")


def _json_float(
    payload: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    exclusive_minimum: bool = False,
) -> float:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, bool):
        raise ValueError(f"Feld {key!r} muss eine Zahl sein.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Feld {key!r} muss eine Zahl sein.") from None
    if not math.isfinite(number):
        raise ValueError(f"Feld {key!r} muss endlich sein.")
    if minimum is not None:
        if exclusive_minimum and number <= minimum:
            raise ValueError(f"Feld {key!r} muss größer als {minimum:g} sein.")
        if not exclusive_minimum and number < minimum:
            raise ValueError(f"Feld {key!r} muss mindestens {minimum:g} sein.")
    if maximum is not None and number > maximum:
        raise ValueError(f"Feld {key!r} darf höchstens {maximum:g} sein.")
    return number


def _json_int(
    payload: dict[str, Any],
    key: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if key not in payload:
        return default
    value = payload[key]
    if isinstance(value, bool):
        raise ValueError(f"Feld {key!r} muss eine ganze Zahl sein.")
    if isinstance(value, int):
        number = value
    else:
        try:
            number_float = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Feld {key!r} muss eine ganze Zahl sein.") from None
        if not number_float.is_integer():
            raise ValueError(f"Feld {key!r} muss eine ganze Zahl sein.")
        number = int(number_float)
    if minimum is not None and number < minimum:
        raise ValueError(f"Feld {key!r} muss mindestens {minimum} sein.")
    if maximum is not None and number > maximum:
        raise ValueError(f"Feld {key!r} darf höchstens {maximum} sein.")
    return number


def parse_upload_payload(payload: dict[str, Any]) -> UploadRequest:
    """Prüft den JSON-Body von POST /api/upload."""
    csv_text = payload.get("csv")
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ValueError("Feld 'csv' fehlt oder ist leer.")

    filename = payload.get("filename", "messdaten.csv")
    if not isinstance(filename, str) or not filename.strip():
        filename = "messdaten.csv"
    filename = Path(filename.strip()).name or "messdaten.csv"

    cutoff = _json_float(
        payload, "cutoff", 0.1, minimum=0.0, maximum=1.0, exclusive_minimum=True
    )
    filter_raw = payload.get("filter", "butterworth")
    if not isinstance(filter_raw, str):
        raise ValueError("Feld 'filter' muss eine Zeichenkette sein.")
    filter_kind = validate_filter_name(filter_raw)
    order = _json_int(payload, "order", 4, minimum=1, maximum=8)
    detrend = _json_bool(payload, "detrend", True)
    pad = _json_float(payload, "pad", 0.1, minimum=0.0, maximum=0.95)
    x_col = _json_int(payload, "x_col", 0)
    y_col = _json_int(payload, "y_col", -1)

    delimiter_raw = payload.get("delimiter", "auto")
    if not isinstance(delimiter_raw, str) or delimiter_raw not in DELIMITERS:
        raise ValueError(
            "Feld 'delimiter' muss auto, ',', ';', tab oder space sein."
        )
    delimiter = "tab" if delimiter_raw == "\t" else delimiter_raw

    return UploadRequest(
        filename=filename,
        csv_text=csv_text,
        cutoff=cutoff,
        filter_kind=filter_kind,
        order=order,
        detrend=detrend,
        pad=pad,
        x_col=x_col,
        y_col=y_col,
        delimiter=delimiter,
    )


# ---------------------------------------------------------------------------
# Gemeinsame Auswertung
# ---------------------------------------------------------------------------

@dataclass
class SmoothingResult:
    x: np.ndarray
    original: np.ndarray
    smoothed: np.ndarray
    residual: np.ndarray
    resampled: bool
    median_dx: float
    stats: dict[str, float]


def filter_label(filter_kind: str, order: int) -> str:
    label = fs.FILTER_NAMES[filter_kind]
    if filter_kind == "butterworth":
        label += f" (Ordnung {order})"
    return label


def _filter_alias(filter_kind: str, aliases: dict[str, Any]) -> str:
    """Erlaubt zusätzlich das API-nahe Schlüsselwort ``filter=``."""
    if "filter" in aliases:
        filter_kind = aliases.pop("filter")
    return filter_kind


def _reject_aliases(aliases: dict[str, Any]) -> None:
    if aliases:
        raise TypeError(
            "Unerwartete Argumente: " + ", ".join(sorted(aliases))
        )


def smooth_series(
    x: np.ndarray | None,
    y: np.ndarray,
    *,
    cutoff: float,
    filter_kind: str,
    order: int,
    detrend: bool,
    pad: float,
) -> SmoothingResult:
    """Bereitet x/y auf, filtert und berechnet die Kennzahlen wie die CLI."""
    x_orig, y_orig, x_grid, y_grid, resampled, _nan_count = fs.prepare_xy(x, y)
    smoothed_grid, _, _ = fs.fft_lowpass(
        y_grid,
        cutoff=cutoff,
        kind=filter_kind,
        order=order,
        pad_fraction=pad,
        detrend=detrend,
    )
    if resampled:
        smoothed = np.interp(x_orig, x_grid, smoothed_grid)
    else:
        smoothed = smoothed_grid
    residual = y_orig - smoothed

    # Vergleichsbasis wie in fft_smoothing.py: trendbereinigt bzw. mittelwertfrei.
    baseline = y_orig - (
        fs._linear_trend(y_orig) if detrend else float(np.mean(y_orig))
    )
    smoothed_baseline = smoothed - (
        fs._linear_trend(smoothed) if detrend else float(np.mean(smoothed))
    )
    rms_original = fs._rms(baseline)
    rms_smoothed = fs._rms(smoothed_baseline)
    rms_residual = fs._rms(residual)
    removed_percent = (
        100.0 * rms_residual / rms_original if rms_original > 0.0 else 0.0
    )

    median_dx = float(np.median(np.diff(x_orig)))
    return SmoothingResult(
        x=x_orig,
        original=y_orig,
        smoothed=smoothed,
        residual=residual,
        resampled=bool(resampled),
        median_dx=median_dx,
        stats={
            "rms_original": float(rms_original),
            "rms_smoothed": float(rms_smoothed),
            "rms_residual": float(rms_residual),
            "removed_percent": float(removed_percent),
        },
    )


def _series_payload(result: SmoothingResult) -> dict[str, list[float]]:
    return {
        "x": result.x.tolist(),
        "original": result.original.tolist(),
        "smoothed": result.smoothed.tolist(),
        "residual": result.residual.tolist(),
    }


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _max_gap_minutes(pairs: list[tuple[datetime, float]]) -> float:
    if len(pairs) < 2:
        return 0.0
    return max(
        (later[0] - earlier[0]).total_seconds() / 60.0
        for earlier, later in zip(pairs, pairs[1:])
    )


# ---------------------------------------------------------------------------
# NDBC
# ---------------------------------------------------------------------------

def fetch_station_years(station: str) -> list[int]:
    """Ermittelt die Jahre mit Standard-Meteorologie-Daten der Station.

    Die NDBC-Stationshistorie listet die vorhandenen Jahresdateien
    (``<station>h<jahr>.txt.gz``). So lassen sich nicht vorhandene Jahre
    bereits in der Oberfläche ausblenden. Jahre vor
    :data:`MIN_STDMET_YEAR` entfallen, weil ihre Dateien nicht das
    moderne Kopfzeilenformat besitzen.
    """
    station = validate_station(station)
    key = ("station-years", station)
    cached = CACHE.get(key)
    if cached is not None:
        return cached

    url = f"{STATION_HISTORY_URL}?station={station}"
    text = ndbc.fetch_text(url)
    pattern = re.compile(
        rf"{re.escape(station)}h(\d{{4}})\.txt\.gz", re.IGNORECASE
    )
    years = sorted({int(year) for year in pattern.findall(text)}, reverse=True)
    years = [year for year in years if year >= MIN_STDMET_YEAR]
    CACHE.set(key, years)
    return years


def _variable_ranges(
    header: list[str], rows: list[list[str]]
) -> dict[str, dict[str, Any]]:
    """Liefert je Messgröße den tatsächlich verfügbaren Echtzeit-Zeitraum."""
    ranges: dict[str, dict[str, Any]] = {}
    for column, name in enumerate(header):
        if name.upper() in TIME_COLUMNS_UPPER:
            continue
        timestamps: list[datetime] = []
        for row in rows:
            if len(row) <= max(column, 4):
                continue
            if not ndbc.is_valid_value(row[column], name):
                continue
            try:
                timestamps.append(ndbc.to_datetime(row))
            except (ValueError, TypeError, IndexError):
                continue
        if not timestamps:
            continue
        start, end = min(timestamps), max(timestamps)
        span_days = max(0.0, (end - start).total_seconds() / 86400.0)
        ranges[name] = {
            "start": _iso_utc(start),
            "end": _iso_utc(end),
            "points": len(timestamps),
            "span_days": round(span_days, 6),
            "max_days": max(1, min(1000, math.ceil(span_days))),
        }
    return ranges


def build_variables(station: str) -> dict[str, Any]:
    """Liest die Spalten einer Station aus der realtime2- oder Jahresdatei."""
    station = validate_station(station)
    realtime_url = f"{ndbc.BASE_URL}/realtime2/{station}.txt"
    realtime_available = True
    try:
        text = ndbc.fetch_text(realtime_url)
        header, units, rows = ndbc.parse_ndbc(text)
        ranges = _variable_ranges(header, rows)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        realtime_available = False
        ranges = {}
        year = datetime.now(timezone.utc).year
        text = ndbc.fetch_text(
            f"{ndbc.BASE_URL}/historical/stdmet/{station}h{year}.txt.gz"
        )
        header, units, _rows = ndbc.parse_ndbc(text)

    try:
        years = fetch_station_years(station)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        years = []
    if not years and not realtime_available:
        # Wenigstens das aktuelle Jahr anbieten, wenn die Historie nicht
        # erreichbar war, die Jahresdatei aber funktioniert hat.
        years = [datetime.now(timezone.utc).year]

    variables: list[dict[str, Any]] = []
    for index, name in enumerate(header):
        if name.upper() in TIME_COLUMNS_UPPER:
            continue
        variables.append(
            {
                "id": name,
                "unit": units[index] if index < len(units) else "",
                "description": ndbc.describe_variable(name),
                "range": ranges.get(name),
            }
        )

    try:
        info = ndbc.fetch_station_info(station)
    except Exception:  # Stammdaten sind optional.
        info = {}
    curated = STATIONS_BY_ID.get(station)
    return {
        "station": station,
        "name": info.get("name") or (curated.name if curated else ""),
        "position": info.get("position") or (curated.position if curated else ""),
        "station_type": info.get("type", ""),
        "years": years,
        "variables": variables,
    }


def build_ndbc_dataset(
    station: str,
    variable: str = "WVHT",
    year: int | None = None,
    days: float = 30.0,
    cutoff: float = 0.1,
    filter_kind: str = "butterworth",
    order: int = 4,
    detrend: bool = True,
    pad: float = 0.1,
    max_gap_min: float | None = None,
    keep_gaps: bool = False,
    **aliases: Any,
) -> dict[str, Any]:
    """Lädt NDBC-Daten, filtert sie und liefert meta/series für das Frontend."""
    filter_kind = _filter_alias(filter_kind, aliases)
    _reject_aliases(aliases)
    station = validate_station(station)
    variable = validate_variable(variable)
    filter_kind = validate_filter_name(filter_kind)
    if not 0.0 < cutoff <= 1.0:
        raise ValueError("Der Parameter cutoff muss im Bereich (0, 1] liegen.")
    if not 1 <= order <= 8:
        raise ValueError("Der Parameter order muss zwischen 1 und 8 liegen.")
    if not 0.0 <= pad <= 0.95:
        raise ValueError("Der Parameter pad muss zwischen 0 und 0.95 liegen.")
    if days < 0.0 or days > 1000.0:
        raise ValueError("Der Parameter days muss zwischen 0 und 1000 liegen.")
    if max_gap_min is not None and max_gap_min <= 0.0:
        raise ValueError("Der Parameter max_gap_min muss positiv sein.")
    if year is not None and not 1900 <= year <= 2100:
        raise ValueError("Das Jahr muss zwischen 1900 und 2100 liegen.")

    if year is not None:
        url = f"{ndbc.BASE_URL}/historical/stdmet/{station}h{year}.txt.gz"
    else:
        url = f"{ndbc.BASE_URL}/realtime2/{station}.txt"

    text = ndbc.fetch_text(url)
    header, units, rows = ndbc.parse_ndbc(text)
    upper_header = [name.upper() for name in header]
    if variable not in upper_header:
        raise ValueError(
            f"Messgröße {variable!r} ist nicht vorhanden. Verfügbar: "
            + ", ".join(header)
        )
    column = upper_header.index(variable)
    unit = units[column] if column < len(units) else ""
    description = ndbc.describe_variable(variable)

    try:
        info = ndbc.fetch_station_info(station)
    except Exception:  # Stammdaten sind optional.
        info = {}
    curated = STATIONS_BY_ID.get(station)

    pairs: list[tuple[datetime, float]] = []
    skipped = 0
    for row in rows:
        if len(row) <= max(column, 4):
            skipped += 1
            continue
        token = row[column]
        if not ndbc.is_valid_value(token, variable):
            skipped += 1
            continue
        try:
            timestamp = ndbc.to_datetime(row)
        except ValueError:
            skipped += 1
            continue
        pairs.append((timestamp, float(token)))

    if not pairs:
        raise ValueError(
            f"Keine gültigen Werte für {variable} gefunden. "
            "Bitte anderes Jahr oder andere Messgröße wählen."
        )

    pairs.sort(key=lambda pair: pair[0])
    deduplicated: dict[datetime, float] = {}
    for timestamp, value in pairs:
        deduplicated[timestamp] = value
    pairs = sorted(deduplicated.items())

    if days > 0.0:
        newest = pairs[-1][0]
        oldest = newest - timedelta(days=days)
        pairs = [pair for pair in pairs if pair[0] >= oldest]
    if not pairs:
        raise ValueError(
            "Im gewählten Zeitraum liegen keine Daten. "
            "Bitte einen größeren Zeitraum wählen."
        )

    if keep_gaps:
        chosen = pairs
    else:
        segments = ndbc.split_segments(pairs, max_gap_min)
        chosen = max(segments, key=lambda segment: (len(segment), segment[-1][0]))

    if len(chosen) < 4:
        raise ValueError("Der gewählte Abschnitt hat weniger als 4 Punkte.")

    start, end = chosen[0][0], chosen[-1][0]
    x = np.round(
        np.asarray(
            [(timestamp - start).total_seconds() / 3600.0 for timestamp, _ in chosen],
            dtype=float,
        ),
        6,
    )
    y = np.asarray([value for _, value in chosen], dtype=float)

    result = smooth_series(
        x,
        y,
        cutoff=cutoff,
        filter_kind=filter_kind,
        order=order,
        detrend=detrend,
        pad=pad,
    )

    median_dx = result.median_dx
    sampling_min = median_dx * 60.0
    fs_hz = 1.0 / (median_dx * 3600.0) if median_dx > 0.0 else None
    cutoff_hz = cutoff * fs_hz / 2.0 if fs_hz is not None else None
    nyquist_hz = fs_hz / 2.0 if fs_hz is not None else None
    duration_h = float(result.x[-1] - result.x[0])

    meta: dict[str, Any] = {
        "kind": "ndbc",
        "station": station,
        "station_name": info.get("name") or (curated.name if curated else ""),
        "position": info.get("position") or (curated.position if curated else ""),
        "station_type": info.get("type", ""),
        "variable": variable,
        "unit": unit,
        "description": description,
        "source_url": url,
        "license": "US-Bundesdaten (gemeinfrei)",
        "start": _iso_utc(start),
        "end": _iso_utc(end),
        "points": int(result.x.size),
        "duration_h": duration_h,
        "sampling_min": sampling_min,
        "sampling_value": sampling_min,
        "sampling_unit": "min",
        "max_gap_min": _max_gap_minutes(chosen),
        "skipped": int(skipped),
        "x_unit": "h",
        "cutoff": float(cutoff),
        "cutoff_hz": cutoff_hz,
        "nyquist_hz": nyquist_hz,
        "filter": filter_kind,
        "filter_label": filter_label(filter_kind, order),
        "order": int(order),
        "detrend": bool(detrend),
        "pad": float(pad),
        "resampled": result.resampled,
        "stats": result.stats,
    }
    return {"meta": meta, "series": _series_payload(result)}


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def build_demo_dataset(
    cutoff: float = 0.1,
    filter_kind: str = "butterworth",
    order: int = 4,
    detrend: bool = True,
    pad: float = 0.1,
    **aliases: Any,
) -> dict[str, Any]:
    """Erzeugt die eingebaute Demo (3 Hz + 8 Hz mit Rauschen, fs = 200 Hz)."""
    filter_kind = _filter_alias(filter_kind, aliases)
    _reject_aliases(aliases)
    filter_kind = validate_filter_name(filter_kind)
    if not 0.0 < cutoff <= 1.0:
        raise ValueError("Der Parameter cutoff muss im Bereich (0, 1] liegen.")
    if not 1 <= order <= 8:
        raise ValueError("Der Parameter order muss zwischen 1 und 8 liegen.")
    if not 0.0 <= pad <= 0.95:
        raise ValueError("Der Parameter pad muss zwischen 0 und 0.95 liegen.")

    x_raw, y_raw, _truth = fs._make_demo()
    result = smooth_series(
        x_raw,
        y_raw,
        cutoff=cutoff,
        filter_kind=filter_kind,
        order=order,
        detrend=detrend,
        pad=pad,
    )
    median_dx = result.median_dx
    fs_hz = 1.0 / median_dx if median_dx > 0.0 else None

    meta: dict[str, Any] = {
        "kind": "demo",
        "station": "",
        "station_name": "Demo",
        "position": "",
        "station_type": "",
        "variable": "signal",
        "unit": "",
        "description": "3 Hz + 8 Hz mit Rauschen",
        "source_url": "",
        "license": "",
        "start": "",
        "end": "",
        "points": int(result.x.size),
        "duration_h": 3.0,
        "sampling_min": median_dx / 60.0,
        "sampling_value": median_dx,
        "sampling_unit": "s",
        "max_gap_min": median_dx / 60.0,
        "skipped": 0,
        "x_unit": "s",
        "cutoff": float(cutoff),
        "cutoff_hz": cutoff * fs_hz / 2.0 if fs_hz is not None else None,
        "nyquist_hz": fs_hz / 2.0 if fs_hz is not None else None,
        "filter": filter_kind,
        "filter_label": filter_label(filter_kind, order),
        "order": int(order),
        "detrend": bool(detrend),
        "pad": float(pad),
        "resampled": result.resampled,
        "stats": result.stats,
    }
    return {"meta": meta, "series": _series_payload(result)}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def build_upload_dataset(
    csv_text: str | None = None,
    filename: str = "messdaten.csv",
    cutoff: float = 0.1,
    filter_kind: str = "butterworth",
    order: int = 4,
    detrend: bool = True,
    pad: float = 0.1,
    x_col: int = 0,
    y_col: int = -1,
    delimiter: str = "auto",
    **aliases: Any,
) -> dict[str, Any]:
    """Verarbeitet eine hochgeladene CSV-Datei über die bestehenden Helfer."""
    if csv_text is None and "csv" in aliases:
        csv_text = aliases.pop("csv")
    filter_kind = _filter_alias(filter_kind, aliases)
    _reject_aliases(aliases)
    if not isinstance(csv_text, str) or not csv_text.strip():
        raise ValueError("Die CSV-Daten sind leer.")
    filter_kind = validate_filter_name(filter_kind)
    if not 0.0 < cutoff <= 1.0:
        raise ValueError("Der Parameter cutoff muss im Bereich (0, 1] liegen.")
    if not 1 <= order <= 8:
        raise ValueError("Der Parameter order muss zwischen 1 und 8 liegen.")
    if not 0.0 <= pad <= 0.95:
        raise ValueError("Der Parameter pad muss zwischen 0 und 0.95 liegen.")
    if delimiter not in DELIMITERS:
        raise ValueError("Unbekanntes Trennzeichen.")

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".csv", encoding="utf-8", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(csv_text)
        comments = fs.read_leading_comments(temp_path)
        metadata = fs.comment_metadata(comments)
        x_raw, y_raw, header, _used_delimiter = fs.load_data(
            temp_path,
            delimiter=delimiter,
            x_col=x_col,
            y_col=y_col,
        )
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    y_header = "y"
    if header:
        y_header = header[y_col % len(header)]

    result = smooth_series(
        x_raw,
        y_raw,
        cutoff=cutoff,
        filter_kind=filter_kind,
        order=order,
        detrend=detrend,
        pad=pad,
    )

    raw_x_unit = metadata.get("x-einheit", "").strip().lower()
    x_unit = raw_x_unit if raw_x_unit in {"s", "min", "h"} else ""
    unit_seconds = fs.X_UNIT_SECONDS.get(x_unit) if x_unit else None

    median_dx = result.median_dx
    if unit_seconds is not None:
        sampling_min: float | None = median_dx * unit_seconds / 60.0
        duration_h: float | None = (
            float(result.x[-1] - result.x[0]) * unit_seconds / 3600.0
        )
        fs_hz = 1.0 / (median_dx * unit_seconds) if median_dx > 0.0 else None
        cutoff_hz = cutoff * fs_hz / 2.0 if fs_hz is not None else None
        nyquist_hz = fs_hz / 2.0 if fs_hz is not None else None
        max_gap_min: float | None = (
            float(np.max(np.diff(result.x))) * unit_seconds / 60.0
            if result.x.size > 1
            else 0.0
        )
    else:
        sampling_min = None
        duration_h = None
        cutoff_hz = None
        nyquist_hz = None
        max_gap_min = None

    station = metadata.get("station", "").strip()
    meta: dict[str, Any] = {
        "kind": "upload",
        "station": station,
        "station_name": station or filename,
        "position": "",
        "station_type": "",
        "variable": y_header,
        "unit": metadata.get("einheit", "").strip(),
        "description": metadata.get("messgröße", "").strip(),
        "source_url": metadata.get("bezugsquelle", "").strip(),
        "license": metadata.get("lizenz", "").strip(),
        "start": "",
        "end": "",
        "points": int(result.x.size),
        "duration_h": duration_h,
        "sampling_min": sampling_min,
        "sampling_value": median_dx,
        "sampling_unit": x_unit,
        "max_gap_min": max_gap_min,
        "skipped": 0,
        "x_unit": x_unit,
        "cutoff": float(cutoff),
        "cutoff_hz": cutoff_hz,
        "nyquist_hz": nyquist_hz,
        "filter": filter_kind,
        "filter_label": filter_label(filter_kind, order),
        "order": int(order),
        "detrend": bool(detrend),
        "pad": float(pad),
        "resampled": result.resampled,
        "stats": result.stats,
    }
    return {"meta": meta, "series": _series_payload(result)}


# ---------------------------------------------------------------------------
# Statische Dateien
# ---------------------------------------------------------------------------

PLACEHOLDER_HTML = """<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FFT-Glättung</title>
</head>
<body>
  <h1>FFT-Glättung</h1>
  <p>Die Weboberfläche ist noch nicht eingerichtet. Bitte den Ordner
     <code>web/</code> mit einer <code>index.html</code> anlegen.</p>
  <p>Die JSON-Schnittstelle ist bereits erreichbar, zum Beispiel unter
     <code>/api/stations</code> oder <code>/api/data?demo=1</code>.</p>
</body>
</html>
"""


def resolve_static_path(url_path: str) -> Path | None:
    """Bildet einen URL-Pfad sicher auf eine Datei in web/ ab."""
    try:
        relative = unquote(url_path).lstrip("/")
    except (UnicodeDecodeError, ValueError):
        return None
    if not relative:
        relative = "index.html"
    try:
        base = WEB_DIR.resolve()
        candidate = (base / relative).resolve()
        candidate.relative_to(base)
    except (OSError, ValueError):
        return None
    if candidate.is_dir():
        candidate = candidate / "index.html"
    return candidate if candidate.is_file() else None


def content_type_for(path: Path) -> str:
    mime, _encoding = mimetypes.guess_type(path.name)
    if mime is None:
        mime = "application/octet-stream"
    if mime.startswith("text/") or mime in {
        "application/javascript",
        "application/json",
        "image/svg+xml",
    }:
        mime += "; charset=utf-8"
    return mime


# ---------------------------------------------------------------------------
# HTTP-Server
# ---------------------------------------------------------------------------

class PayloadTooLarge(Exception):
    """Anfragekörper überschreitet das erlaubte Limit."""


class WebUIHandler(BaseHTTPRequestHandler):
    """Liefert statische Dateien und die JSON-API."""

    server_version = "FFTWebUI/1.0"

    # -- Antworten ---------------------------------------------------------

    def _send_json(self, payload: Any, status: int = 200) -> None:
        try:
            data = json.dumps(
                payload, ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
        except (TypeError, ValueError):
            # Sollte die Pipeline doch einmal nicht-endliche Werte liefern.
            traceback.print_exc(file=sys.stderr)
            status = 500
            data = json.dumps(
                {"error": "Die Antwort konnte nicht als JSON erzeugt werden."},
                ensure_ascii=False,
            ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_bytes(
        self, data: bytes, content_type: str, *, no_store: bool = False
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if no_store else "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _serve_static(self, url_path: str) -> None:
        if url_path in {"", "/"} and not (WEB_DIR / "index.html").is_file():
            self._send_bytes(
                PLACEHOLDER_HTML.encode("utf-8"),
                "text/html; charset=utf-8",
                no_store=True,
            )
            return

        candidate = resolve_static_path(url_path)
        if candidate is None:
            self._send_error_json(404, "Datei nicht gefunden.")
            return
        try:
            data = candidate.read_bytes()
        except OSError:
            self._send_error_json(404, "Datei nicht gefunden.")
            return
        self._send_bytes(
            data,
            content_type_for(candidate),
            no_store=candidate.suffix.lower() in NO_STORE_SUFFIXES,
        )

    # -- API-Fehlerbehandlung ---------------------------------------------

    def _run_api(self, builder: Callable[[], Any]) -> None:
        try:
            payload = builder()
        except ValueError as exc:
            self._send_error_json(400, str(exc))
        except urllib.error.HTTPError as exc:
            self._send_error_json(
                502,
                f"NDBC-Daten sind nicht verfügbar (HTTP {exc.code}). "
                "Bitte Station und ggf. Jahr prüfen.",
            )
        except urllib.error.URLError as exc:
            self._send_error_json(
                502,
                f"NDBC-Download fehlgeschlagen: {exc.reason}. "
                "Bitte Netzwerkverbindung und Station prüfen.",
            )
        except (TimeoutError, OSError) as exc:
            self._send_error_json(
                502,
                f"NDBC-Download fehlgeschlagen: {exc}. "
                "Bitte Netzwerkverbindung und Station prüfen.",
            )
        except Exception:  # Unerwartet: Traceback ins Server-Log.
            traceback.print_exc(file=sys.stderr)
            self._send_error_json(
                500, "Interner Serverfehler. Details stehen im Server-Log."
            )
        else:
            self._send_json(payload)

    def _handle_get_api(self, path: str, query: str) -> None:
        params = parse_qs(query, keep_blank_values=True)

        if path == "/api/stations":
            self._run_api(lambda: {"stations": [s.as_dict() for s in STATIONS]})
            return

        if path == "/api/variables":
            def variables() -> dict[str, Any]:
                raw = _single_param(params, "station")
                if raw is None:
                    raise ValueError("Parameter 'station' fehlt.")
                station = validate_station(raw)
                key = ("variables", station)
                cached = CACHE.get(key)
                if cached is not None:
                    return cached
                result = build_variables(station)
                CACHE.set(key, result)
                return result

            self._run_api(variables)
            return

        if path == "/api/data":
            def data() -> dict[str, Any]:
                query_params = parse_data_query(params)
                key = query_params.cache_key()
                cached = CACHE.get(key)
                if cached is not None:
                    return cached
                if query_params.demo:
                    result = build_demo_dataset(
                        cutoff=query_params.cutoff,
                        filter_kind=query_params.filter_kind,
                        order=query_params.order,
                        detrend=query_params.detrend,
                        pad=query_params.pad,
                    )
                else:
                    assert query_params.station is not None
                    result = build_ndbc_dataset(
                        station=query_params.station,
                        variable=query_params.variable,
                        year=query_params.year,
                        days=query_params.days,
                        cutoff=query_params.cutoff,
                        filter_kind=query_params.filter_kind,
                        order=query_params.order,
                        detrend=query_params.detrend,
                        pad=query_params.pad,
                        max_gap_min=query_params.max_gap_min,
                        keep_gaps=query_params.keep_gaps,
                    )
                CACHE.set(key, result)
                return result

            self._run_api(data)
            return

        self._send_error_json(404, "Unbekannter API-Endpunkt.")

    # -- Upload ------------------------------------------------------------

    def _read_json_body(self) -> dict[str, Any]:
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            raise ValueError("Content-Length fehlt.")
        try:
            length = int(length_header)
        except ValueError:
            raise ValueError("Ungültiger Content-Length.") from None
        if length < 0:
            raise ValueError("Ungültiger Content-Length.")
        if length > MAX_UPLOAD_BYTES:
            raise PayloadTooLarge(
                "Die Anfrage ist zu groß (maximal 20 MB)."
            )
        body = self.rfile.read(length)
        if len(body) != length:
            raise ValueError("Die Anfrage wurde unvollständig übertragen.")
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Der Anfrageinhalt ist kein gültiges UTF-8.") from None
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise ValueError("Ungültiges JSON im Anfrageinhalt.") from None
        if not isinstance(payload, dict):
            raise ValueError("Das JSON muss ein Objekt sein.")
        return payload

    def _handle_upload(self) -> None:
        try:
            payload = self._read_json_body()
            request = parse_upload_payload(payload)
            result = build_upload_dataset(
                csv_text=request.csv_text,
                filename=request.filename,
                cutoff=request.cutoff,
                filter_kind=request.filter_kind,
                order=request.order,
                detrend=request.detrend,
                pad=request.pad,
                x_col=request.x_col,
                y_col=request.y_col,
                delimiter=request.delimiter,
            )
        except PayloadTooLarge as exc:
            self._send_error_json(413, str(exc))
        except ValueError as exc:
            self._send_error_json(400, str(exc))
        except Exception:
            traceback.print_exc(file=sys.stderr)
            self._send_error_json(
                500, "Interner Serverfehler. Details stehen im Server-Log."
            )
        else:
            self._send_json(result)

    # -- Routing -----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (HTTP-Methodenname)
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_get_api(parsed.path, parsed.query)
        else:
            self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload":
            self._handle_upload()
        else:
            self._send_error_json(404, "Unbekannter API-Endpunkt.")


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    """Erzeugt den Server, ohne ihn zu starten (für Tests und main())."""
    return ThreadingHTTPServer((host, port), WebUIHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Startet die lokale Web-Oberfläche für die FFT-Glättung. "
            "Die JSON-API liegt unter /api/."
        )
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind-Adresse (Standard: 127.0.0.1)."
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port (Standard: 8000)."
    )
    args = parser.parse_args(argv)

    server = create_server(args.host, args.port)
    host, port = server.server_address[0], server.server_address[1]
    print(f"Web-Oberfläche läuft auf http://{host}:{port}/")
    print("Beenden mit Strg+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer beendet.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
