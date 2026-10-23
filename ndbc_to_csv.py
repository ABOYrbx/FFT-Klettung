#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NDBC-Bojendaten laden und für fft_smoothing.py aufbereiten.

Beispiele:
    python3 ndbc_to_csv.py 46001 --variable WVHT
    python3 ndbc_to_csv.py 46001 --year 2025 --variable WSPD --days 60
    python3 ndbc_to_csv.py 41002 --list-variables

Danach:
    python3 fft_smoothing.py data/ndbc/46001_WVHT.csv --cutoff 0.1

Das Skript benötigt nur die Python-Standardbibliothek. Es lädt die öffentlichen
Daten von https://www.ndbc.noaa.gov/ und schreibt eine CSV mit UTC-Zeit nach
data/ndbc/.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import math
import re
import statistics
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

BASE_URL = "https://www.ndbc.noaa.gov/data"
USER_AGENT = "fft-smoothing-buoy-example/1.0 (educational use)"
DATA_DIR = Path("data") / "ndbc"


def default_output_path(station: str, variable: str, year: int | None = None) -> Path:
    """Standard-Ablageort: ``data/ndbc/<station>_<variable>[_<jahr>].csv``."""
    name = f"{station}_{variable}" + (f"_{year}" if year else "") + ".csv"
    return DATA_DIR / name

# Plausible Wertebereiche; alles außerhalb gilt als fehlender Messwert.
# Das fängt neben "MM" auch die historischen Sentinel-Werte (99, 999, 9999) ab.
PLAUSIBLE_RANGES = {
    "WDIR": (0.0, 360.0),
    "WSPD": (0.0, 100.0),
    "GST": (0.0, 100.0),
    "WVHT": (0.0, 30.0),
    "DPD": (0.0, 40.0),
    "APD": (0.0, 40.0),
    "MWD": (0.0, 360.0),
    "PRES": (800.0, 1100.0),
    "ATMP": (-60.0, 60.0),
    "WTMP": (-10.0, 50.0),
    "DEWP": (-60.0, 60.0),
    "VIS": (0.0, 50.0),
    "PTDY": (-30.0, 30.0),
    "TIDE": (-30.0, 30.0),
}

STATION_PATTERN = re.compile(r"^[A-Za-z0-9]{3,10}$")

# Kurzbeschreibung der NDBC-Spalten für die Ausgabe.
VARIABLE_INFO = {
    "WDIR": "Windrichtung (Richtung, aus der der Wind kommt)",
    "WSPD": "Windgeschwindigkeit (Mittelwert)",
    "GST": "maximale Böengeschwindigkeit",
    "WVHT": "signifikante Wellenhöhe (Mittel der höchsten Drittel)",
    "DPD": "dominante Wellenperiode",
    "APD": "mittlere Wellenperiode",
    "MWD": "mittlere Wellenrichtung",
    "PRES": "Luftdruck auf Meereshöhe",
    "ATMP": "Lufttemperatur",
    "WTMP": "Wassertemperatur",
    "DEWP": "Taupunkt",
    "VIS": "Sichtweite",
    "PTDY": "Drucktendenz der letzten drei Stunden",
    "TIDE": "Wasserstand",
}

POSITION_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*([NS])\s+(-?\d+(?:\.\d+)?)\s*([EW])", re.IGNORECASE
)

TIME_COLUMN_INFO = {
    "YY": "Jahr (UTC)",
    "MM": "Monat (UTC)",
    "DD": "Tag (UTC)",
    "hh": "Stunde (UTC)",
    "mm": "Minute (UTC)",
}


def describe_variable(variable: str) -> str:
    if variable in TIME_COLUMN_INFO:
        return TIME_COLUMN_INFO[variable]
    return VARIABLE_INFO.get(variable.upper(), "")


def format_position(latitude: float, longitude: float) -> str:
    north = "N" if latitude >= 0 else "S"
    east = "E" if longitude >= 0 else "W"
    return f"{abs(latitude):.3f}° {north}, {abs(longitude):.3f}° {east}"


def parse_station_table(text: str, station: str) -> dict[str, str]:
    """Liest Stammdaten einer Station aus station_table.txt."""
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.startswith("#"):
            continue
        fields = raw_line.split("|")
        if len(fields) < 7 or fields[0].strip().upper() != station.upper():
            continue
        name = " ".join(unescape(fields[4]).split())
        location = " ".join(unescape(fields[6]).split())
        info = {
            "name": name,
            "location": location,
            "type": fields[2].strip(),
            "hull": fields[3].strip(),
        }
        match = POSITION_PATTERN.search(location)
        if match:
            latitude = float(match.group(1)) * (1 if match.group(2).upper() == "N" else -1)
            longitude = float(match.group(3)) * (1 if match.group(4).upper() == "E" else -1)
            info["position"] = format_position(latitude, longitude)
        return info
    return {}


def fetch_station_info(station: str) -> dict[str, str]:
    """Holt Stationsstammdaten; bei Netzproblemen leeres Ergebnis."""
    try:
        text = fetch_text(f"{BASE_URL}/stations/station_table.txt")
    except (urllib.error.URLError, TimeoutError, OSError):
        return {}
    return parse_station_table(text, station)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    return payload.decode("utf-8", errors="replace")


def parse_ndbc(text: str) -> tuple[list[str], list[str], list[list[str]]]:
    """Liefert Spaltennamen, Einheiten und Datenzeilen."""
    header: list[str] | None = None
    units: list[str] | None = None
    rows: list[list[str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            fields = line.lstrip("#").split()
            if header is None:
                header = fields
            elif units is None:
                units = fields
            continue
        row = line.split()
        if len(row) >= 5:
            rows.append(row)

    if header is None:
        raise ValueError("Keine NDBC-Kopfzeile gefunden.")
    if units is None:
        units = [""] * len(header)
    if not rows:
        raise ValueError("Die Datei enthält keine Datenzeilen.")
    return header, units, rows


def is_valid_value(token: str, variable: str) -> bool:
    if token.upper() in {"MM", "M", ""}:
        return False
    try:
        value = float(token)
    except ValueError:
        return False
    if not math.isfinite(value):
        return False
    low, high = PLAUSIBLE_RANGES.get(variable.upper(), (-math.inf, math.inf))
    return low <= value <= high


def to_datetime(row: list[str]) -> datetime:
    year, month, day, hour, minute = (int(row[index]) for index in range(5))
    if year < 100:
        year += 1900 if year >= 70 else 2000
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def split_segments(
    pairs: list[tuple[datetime, float]], max_gap_minutes: float | None
) -> list[list[tuple[datetime, float]]]:
    if len(pairs) < 2:
        return [pairs]

    seconds = [
        (later[0] - earlier[0]).total_seconds()
        for earlier, later in zip(pairs, pairs[1:])
    ]
    median_step = statistics.median(seconds)
    if max_gap_minutes is None:
        # Automatisch: dreimal der typische Abstand, mindestens 30 Minuten.
        threshold = max(3.0 * median_step, 30.0 * 60.0)
    elif max_gap_minutes <= 0:
        return [pairs]
    else:
        threshold = max_gap_minutes * 60.0

    segments: list[list[tuple[datetime, float]]] = []
    start = 0
    for index, gap in enumerate(seconds, start=1):
        if gap > threshold:
            segments.append(pairs[start:index])
            start = index
    segments.append(pairs[start:])
    return [segment for segment in segments if segment]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Lädt Daten einer NDBC-Boje und schreibt eine für fft_smoothing.py "
            "geeignete CSV-Datei."
        )
    )
    parser.add_argument("station", help="NDBC-Stationskennung, z. B. 46001 oder 41002.")
    parser.add_argument(
        "--variable",
        default="WVHT",
        help="NDBC-Spalte, z. B. WVHT, WSPD, WTMP, PRES (Standard: WVHT).",
    )
    parser.add_argument(
        "--year",
        type=int,
        help="Jahresdatei aus dem historischen Archiv statt der letzten 5 Tage.",
    )
    parser.add_argument(
        "--days",
        type=float,
        default=30.0,
        help="Nur die letzten N Tage verwenden; 0 = alles (Standard: 30).",
    )
    parser.add_argument(
        "--max-gap-min",
        type=float,
        default=None,
        help=(
            "Abschnitte mit größeren Lücken trennen (Standard: automatisch, "
            "mindestens 30 min; 0 = nicht trennen)."
        ),
    )
    parser.add_argument(
        "--keep-gaps",
        action="store_true",
        help="Alle Messwerte behalten, auch über große Lücken hinweg.",
    )
    parser.add_argument(
        "--list-segments",
        action="store_true",
        help="Nur die zusammenhängenden Abschnitte anzeigen.",
    )
    parser.add_argument(
        "--list-variables",
        action="store_true",
        help="Verfügbare Spalten anzeigen und beenden.",
    )
    parser.add_argument(
        "--with-timestamp",
        action="store_true",
        help="Zusätzlich eine Datei mit UTC-Zeitstempeln je Zeile schreiben.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Zieldatei (Standard: data/ndbc/<station>_<variable>[_<jahr>].csv).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    station = args.station.upper()
    if not STATION_PATTERN.fullmatch(station):
        print("Fehler: Ungültige Stationskennung.", file=sys.stderr)
        return 2
    if args.days < 0:
        print("Fehler: --days darf nicht negativ sein.", file=sys.stderr)
        return 2

    if args.year is not None:
        if not 1900 <= args.year <= 2100:
            print("Fehler: Unplausibles Jahr.", file=sys.stderr)
            return 2
        url = f"{BASE_URL}/historical/stdmet/{station}h{args.year}.txt.gz"
    else:
        url = f"{BASE_URL}/realtime2/{station}.txt"

    try:
        text = fetch_text(url)
    except urllib.error.HTTPError as error:
        print(
            f"Fehler: Die Daten sind nicht verfügbar (HTTP {error.code}).\n"
            f"URL: {url}\n"
            "Bei --year prüfen, ob die Boje in diesem Jahr Daten geliefert hat.",
            file=sys.stderr,
        )
        return 2
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"Fehler: Download fehlgeschlagen: {error}", file=sys.stderr)
        return 2

    try:
        header, units, rows = parse_ndbc(text)
    except ValueError as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2

    upper_header = [name.upper() for name in header]
    station_info = fetch_station_info(station)

    if args.list_variables:
        title = f"Station {station}"
        if station_info.get("name"):
            title += f" – {station_info['name']}"
        print(title)
        if station_info.get("position"):
            print(f"Position: {station_info['position']}")
        if station_info.get("type"):
            hull = f", Hull {station_info['hull']}" if station_info.get("hull") else ""
            print(f"Stationstyp: {station_info['type']}{hull}")
        print("Verfügbare Spalten:")
        width = max(len(name) for name in header)
        for name, unit in zip(header, units):
            description = describe_variable(name)
            line = f"  {name:{width}s}  {unit:5s}"
            if description:
                line += f"  {description}"
            print(line.rstrip())
        return 0

    variable = args.variable.upper()
    if variable not in upper_header:
        print(
            f"Fehler: Spalte {variable!r} nicht vorhanden. Verfügbar: "
            + ", ".join(header),
            file=sys.stderr,
        )
        return 2
    column = upper_header.index(variable)
    unit = units[column] if column < len(units) else ""
    description = describe_variable(variable)

    pairs: list[tuple[datetime, float]] = []
    skipped = 0
    for row in rows:
        if len(row) <= max(column, 4):
            skipped += 1
            continue
        token = row[column]
        if not is_valid_value(token, variable):
            skipped += 1
            continue
        try:
            timestamp = to_datetime(row)
        except ValueError:
            skipped += 1
            continue
        pairs.append((timestamp, float(token)))

    if not pairs:
        print(f"Fehler: Keine gültigen Werte für {variable} gefunden.", file=sys.stderr)
        return 2

    pairs.sort(key=lambda pair: pair[0])

    # Doppelte Zeitstempel entfernen (der letzte Wert gewinnt).
    deduplicated: dict[datetime, float] = {}
    for timestamp, value in pairs:
        deduplicated[timestamp] = value
    pairs = sorted(deduplicated.items())

    if args.days:
        newest = pairs[-1][0]
        oldest = newest - timedelta(days=args.days)
        pairs = [pair for pair in pairs if pair[0] >= oldest]
    if not pairs:
        print("Fehler: Im gewählten Zeitraum liegen keine Daten.", file=sys.stderr)
        return 2

    segments = split_segments(pairs, None if args.keep_gaps else args.max_gap_min)
    if args.list_segments:
        label = f"Station {station}"
        if station_info.get("name"):
            label += f" – {station_info['name']}"
        print(label)
        if station_info.get("position"):
            print(f"Position: {station_info['position']}")
        print(
            f"Messgröße: {variable}"
            + (f" ({unit})" if unit else "")
            + (f" – {description}" if description else "")
        )
        print(f"{len(segments)} zusammenhängende Abschnitte:")
        for number, segment in enumerate(segments, start=1):
            duration = segment[-1][0] - segment[0][0]
            print(
                f"  {number:2d}: {segment[0][0]:%Y-%m-%d %H:%M} – "
                f"{segment[-1][0]:%Y-%m-%d %H:%M} UTC, "
                f"{len(segment)} Punkte, {duration.total_seconds() / 3600:.1f} h"
            )
        return 0

    if args.keep_gaps:
        chosen = pairs
    else:
        chosen = max(segments, key=lambda segment: (len(segment), segment[-1][0]))
        if len(segments) > 1:
            print(
                f"Hinweis: {len(segments)} Abschnitte gefunden; der längste wird "
                "verwendet. Mit --list-segments alle anzeigen, mit --keep-gaps "
                "Lücken behalten."
            )

    if len(chosen) < 4:
        print("Fehler: Der gewählte Abschnitt hat weniger als 4 Punkte.", file=sys.stderr)
        return 2

    start = chosen[0][0]
    end = chosen[-1][0]
    output = Path(args.output) if args.output else default_output_path(
        station, variable, args.year
    )
    output.parent.mkdir(parents=True, exist_ok=True)

    duration_hours = (end - start).total_seconds() / 3600.0
    gaps = [
        (later[0] - earlier[0]).total_seconds() / 60.0
        for earlier, later in zip(chosen, chosen[1:])
    ]
    median_gap = statistics.median(gaps) if gaps else 0.0
    max_gap = max(gaps) if gaps else 0.0
    created = datetime.now(timezone.utc)

    station_label = station
    if station_info.get("name"):
        station_label += f" – {station_info['name']}"

    comments = ["NDBC-Bojendaten (NOAA National Data Buoy Center)"]
    comments.append(f"Station: {station_label}")
    if station_info.get("position"):
        comments.append(f"Position: {station_info['position']}")
    if station_info.get("type"):
        hull = f", Hull {station_info['hull']}" if station_info.get("hull") else ""
        comments.append(f"Stationstyp: {station_info['type']}{hull}")
    comments.append(
        f"Messgröße: {variable}" + (f" – {description}" if description else "")
    )
    comments.append(f"Einheit: {unit}" if unit else "Einheit: keine")
    comments.append(f"Zeitraum: {start:%Y-%m-%d %H:%M} bis {end:%Y-%m-%d %H:%M} UTC")
    comments.append(f"Punkte: {len(chosen)}")
    comments.append(
        f"Abtastung: {median_gap:.6g} min (Median), größte Lücke {max_gap:.6g} min"
    )
    if skipped:
        comments.append(f"Übersprungen: {skipped} Zeilen (fehlend/unplausibel)")
    comments.append("x-Einheit: h")
    comments.append("time_h: Stunden seit Beginn des Abschnitts")
    comments.append(f"Bezugsquelle: {url}")
    comments.append("Lizenz: US-Bundesdaten (gemeinfrei)")
    comments.append(f"Erstellt: {created:%Y-%m-%dT%H:%MZ} mit ndbc_to_csv.py")

    with output.open("w", encoding="utf-8", newline="") as handle:
        for comment in comments:
            handle.write(f"# {comment}\n")
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["time_h", variable])
        for timestamp, value in chosen:
            hours = (timestamp - start).total_seconds() / 3600.0
            writer.writerow([f"{hours:.6f}", f"{value:.4f}"])

    if args.with_timestamp:
        sidecar = output.with_name(output.stem + "_timestamps.csv")
        with sidecar.open("w", encoding="utf-8", newline="") as handle:
            handle.write(f"# UTC-Zeitstempel zu {output.name}\n")
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["time_h", "time_utc"])
            for timestamp, _ in chosen:
                hours = (timestamp - start).total_seconds() / 3600.0
                writer.writerow([f"{hours:.6f}", timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")])

    print("NDBC-Bojendaten")
    print(f"  Station:       {station_label}")
    if station_info.get("position"):
        print(f"  Position:      {station_info['position']}")
    if station_info.get("type"):
        hull = f", Hull {station_info['hull']}" if station_info.get("hull") else ""
        print(f"  Stationstyp:   {station_info['type']}{hull}")
    print(
        f"  Messgröße:    {variable}"
        + (f" ({unit})" if unit else "")
        + (f" – {description}" if description else "")
    )
    print(f"  Zeitraum:      {start:%Y-%m-%d %H:%M} – {end:%Y-%m-%d %H:%M} UTC")
    print(
        f"  Punkte:        {len(chosen)} "
        f"({duration_hours:.1f} h, {duration_hours / 24.0:.1f} Tage)"
    )
    print(f"  Abtastung:     {median_gap:.6g} min (Median)")
    print(f"  Größte Lücke:  {max_gap:.6g} min")
    if skipped:
        print(f"  Übersprungen:  {skipped} Zeilen (fehlend/unplausibel)")
    print(f"  Bezugsquelle:  {url}")
    print(f"  Ausgabe:       {output}")

    if variable == "WVHT":
        print()
        print(
            "  Hinweis: WVHT ist eine bereits gemittelte Wellenkenngröße,\n"
            "  kein Rohsignal der Bojenbewegung."
        )

    print()
    print(
        "Nächster Schritt, z. B.:\n"
        f"  python3 fft_smoothing.py {output} --cutoff 0.1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
