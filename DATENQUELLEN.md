# Echte Bojendaten

Diese Datei sammelt öffentliche Datenquellen für Messdaten einer Boje und
erklärt, welche davon zu `fft_smoothing.py` passen.

## Kurzfassung

Für den Einstieg ist **NDBC** am einfachsten: kostenlos, ohne Anmeldung, mit
einem mitgelieferten Konverter.

```bash
# letzte 30 Tage Wellenhöhe der Boje 46001 (Golf von Alaska)
python3 ndbc_to_csv.py 46001 --variable WVHT --days 30

# glätten (schreibt nach output/ndbc/)
python3 fft_smoothing.py data/ndbc/46001_WVHT.csv --cutoff 0.1
```

Für europäische Gewässer sind **Cefas WaveNet** (UK), **Marine Institute
ERDDAP** (Irland), **Rijkswaterstaat** (Niederlande) und **EMODnet Physics**
(EU-weit) gute Anlaufstellen. Wer wirklich die Bewegung der Boje im
Sekundentakt glätten will, braucht **Rohdaten mit 1–2 Hz**; die gibt es vor
allem bei **CDIP** und **OOI**.

## Wichtig: Auflösung passt oft nicht zur Frage

Die meisten öffentlichen Bojenprodukte sind bereits gemittelte Wellen- oder
Wetterwerte (z. B. alle 10 Minuten). Damit lässt sich der Wetterverlauf glätten,
aber keine einzelne Welle. Für die FFT-Glättung gilt:

| Abtastung | Nyquist-Frequenz | `--cutoff 0.1` behält Perioden länger als |
| --- | --- | --- |
| 10 min | 0,83 mHz | ca. 3,3 h |
| 1 h | 0,14 mHz | ca. 20 h |
| 1 Hz | 0,5 Hz | ca. 20 s |
| 2 Hz | 1 Hz | ca. 10 s |

Ein Wellensignal mit 5–15 s Periode braucht also mindestens 1–2 Hz. Bei
10-Minuten-Daten kann die FFT nur noch Wetterlagen glätten – das ist kein Fehler
des Programms, sondern eine Eigenschaft der Daten.

## Quellen im Überblick

| Quelle | Region | Inhalt | Auflösung | Zugang |
| --- | --- | --- | --- | --- |
| [NDBC](https://www.ndbc.noaa.gov/) | USA, Pazifik, Atlantik, Große Seen | Wind, Wellen, Luftdruck, Temperaturen | 10 min (ältere Jahre teils 1 h) | frei, txt/gz, kein Login |
| [GoMOOS/NERACOOS](https://data.neracoos.org/erddap/) | Golf von Maine (USA) | **Bojen-Neigung (Kipp-Daten)**, Strömung, Temperatur | 1 h | frei, CSV, kein Login |
| [NDBC DODS](https://dods.ndbc.noaa.gov/) | wie oben | dieselben Daten als NetCDF/OPeNDAP | wie oben | frei, ohne Login |
| [CDIP](https://cdip.ucsd.edu/) | Kalifornien, weltweit | Rohdaten der Bojenbewegung, Wellenspektren | 1–2 Hz bzw. 30–60 min | frei, THREDDS; blockt automatisierte Clients |
| [Cefas WaveNet](https://wavenet.cefas.co.uk/) | UK, Nordsee, Irische See | Wellenhöhe, -periode, -richtung | 30 min | frei, CSV im Browser |
| [Marine Institute ERDDAP](https://erddap.marine.ie/erddap/index.html) | Irland | Wetterbojen M2–M6 inkl. Wellen | 1 h | frei, CSV/JSON/NetCDF, kein Login |
| [EMODnet Physics](https://emodnet.ec.europa.eu/en/physics) | Europa | aggregierte Bojen, Glider, Plattformen | je Datensatz | frei, Portal + [ERDDAP](https://erddap.emodnet-physics.eu/erddap/index.html) |
| [Rijkswaterstaat Waterinfo](https://waterinfo.rws.nl/) | NL Nordsee, Flüsse | Wasserstand, Wellen, Wind | 10 min–1 h | frei, Download im Browser |
| [BSH](https://www.bsh.de/DE/DATEN/daten_node.html) | Deutsche Nord- und Ostsee | MARNET-Messnetz, Seegangsstatistiken | meist 30 min | frei/teils Registrierung |
| [PMEL GTMBA](https://www.pmel.noaa.gov/gtmba/data-access/disdel) | Tropischer Pazifik, Atlantik, Indik | TAO/PIRATA/RAMA: Meteo, teils Wellen | 10 min–1 h | frei, txt/NetCDF |
| [Copernicus Marine](https://marine.copernicus.eu/access-data) | global, regional | In-situ- und Modelldaten | je Produkt | kostenloses Konto nötig |
| [OOI](https://ooinet.oceanobservatories.org/) | USA, Küsten und offener Ozean | Rohdaten inkl. 1-Hz-Meteorologie | bis 1 Hz | frei, Konto für Rohdatenabfragen |
| [PANGAEA](https://www.pangaea.de/) | weltweit | archivierte Forschungsdatensätze | je Datensatz | frei, DOI-zitierbar |
| [IMOS AODN](https://portal.aodn.org.au/) | Australien | Wellenbojen, Ozeandaten | 30 min–1 h | frei, NetCDF/CSV |
| [MEDS/DFO](https://www.meds-sdmm.dfo-mpo.gc.ca/) | Kanada | Bojen, Wellen, Meteo | 10 min–1 h | frei, CSV |

## NDBC im Detail

NDBC ist der einfachste Einstieg, weil die Dateien ein stabiles Textformat
haben und der Konverter `ndbc_to_csv.py` sie direkt verarbeitet.

- **Realtime:** `https://www.ndbc.noaa.gov/data/realtime2/<station>.txt`
  (letzte Tage, 10-Minuten-Werte)
- **Historie:** `https://www.ndbc.noaa.gov/data/historical/stdmet/<station>h<jahr>.txt.gz`
- **Format:** Leerraum-getrennt, Kopfzeilen mit `#`, fehlende Werte als `MM`
  (Jahresdateien vor 2007 haben ein älteres Format ohne `#` und werden von
  Konverter und Web-UI nicht angeboten)
- **Zeit:** UTC, absteigend sortiert
- **Lizenz:** US-Bundesdaten, gemeinfrei

Beispiele mit dem Konverter:

```bash
# verfügbare Spalten anzeigen
python3 ndbc_to_csv.py 46001 --list-variables

# letzte 5 Tage
python3 ndbc_to_csv.py 41002 --variable WVHT --days 5

# ganzes Jahr 2025, aber nur 60 Tage
python3 ndbc_to_csv.py 46001 --year 2025 --variable WSPD --days 60

# Lücken nicht automatisch trennen
python3 ndbc_to_csv.py 46001 --variable WVHT --keep-gaps

# prüfen, welche zusammenhängenden Abschnitte es gibt
python3 ndbc_to_csv.py 46001 --variable WVHT --list-segments

# zusätzlich eine Datei mit UTC-Zeitstempeln je Zeile
python3 ndbc_to_csv.py 46001 --variable WVHT --with-timestamp
```

Der Konverter schreibt standardmäßig nach
`data/ndbc/<station>_<variable>[_<jahr>].csv` und legt den Ordner bei Bedarf an.
Die Datei enthält eine numerische CSV (`time_h,WVHT`), damit `fft_smoothing.py`
sie ohne Zusatzspalten lesen kann. Der Startzeitpunkt steht als Kommentar in der
Datei; `--with-timestamp` erzeugt zusätzlich `<name>_timestamps.csv` mit den
UTC-Zeitstempeln.

Die Kommentarzeilen am Dateianfang enthalten Stationsname, Position,
Stationstyp, Messgröße mit Kurzbeschreibung, Einheit, Zeitraum, Abtastung,
Bezugsquelle und Lizenz. `fft_smoothing.py` zeigt diese Angaben an und schreibt
sie in die Ergebnisdatei. Über `# x-Einheit: h` erkennt das Programm außerdem,
dass die Zeitachse in Stunden vorliegt, und kann Abtastrate, Nyquist-Frequenz
und Grenzfrequenz in Hz ausgeben.

Hinweise:

- Fehlende Werte (`MM`) und unplausible Sentinel-Werte werden verworfen. Dadurch
  entstehen Lücken; der Konverter verwendet standardmäßig den längsten
  zusammenhängenden Abschnitt.
- Die Spalte `WVHT` ist die signifikante Wellenhöhe, ein bereits gemitteltes
  Wellenprodukt – keine Rohmessung der Bojenbewegung.
- Manche Stationen liefern nur stündlich (z. B. ältere Jahre) oder sind
  vorübergehend außer Betrieb. Bei HTTP 404 hilft ein Blick auf die
  [Stationsstatusseite](https://www.ndbc.noaa.gov/wstat.shtml).

## Kipp-Daten (Bojen-Neigung)

Für die Frage, wie sich eine Boje neigt, gibt es bei NDBC kein direktes
Produkt. Die Web-Oberfläche nutzt stattdessen die Aanderaa-Tilt-Sensoren der
GoMOOS-Bojen (University of Maine / NERACOOS) im Golf von Maine:

- **Quelle:** `https://gyre.umeoce.maine.edu/data/gomoos/buoy/php/view_csv_file.php`
  mit dem jeweiligen NetCDF-Pfad als Parameter,
- **Verankerungen:** B0139 (seit 2024-12-15, laufend), B0137 (2022-09-09 bis
  2024-01-03), B0133 (2019-06-01 bis 2020-01-23), B0132 (2018-10-01 bis
  2019-06-01), alle am Western Maine Shelf (etwa 43,18° N, 70,43° W),
- **Format:** CSV mit `Time[GMT]` und `tilt[degrees](2m)`, stündliche Werte in
  Grad gegenüber der Vertikalen,
- **Zugang:** frei, kein Login; die Web-UI ruft die Datei bei Bedarf ab,
- **Lizenz:** öffentlich, University of Maine / GoMOOS-NERACOOS.

In der Oberfläche stehen die Kipp-Daten im Feld **Kipp-Daten (Neigung)** oder im
Datenbrowser zur Auswahl. `days=0` lädt die gesamte verfügbare Reihe; große
Lücken trennen die Abschnitte, standardmäßig wird der längste zusammenhängende
Abschnitt geglättet. Der Sensor von B0139 liefert erst seit Ende November 2025
Neigungswerte, davor enthält die Datei nur Strömungs- und Temperaturdaten.

## CDIP: Rohdaten mit 1–2 Hz

CDIP (Coastal Data Information Program, Scripps/UCSD) betreibt Wellenbojen, die
neben Wellenparametern auch die Roh-Zeitreihen der Bojenbewegung
veröffentlichen. Das ist der interessanteste Fall für die FFT-Glättung, weil
dort tatsächlich die Bewegung im Sekundentakt vorliegt.

- Einstieg: <https://cdip.ucsd.edu/>
- Katalog: <https://thredds.cdip.ucsd.edu/thredds/catalog.html>
- Formate: NetCDF, teils ASCII; Auswertung z. B. mit `xarray` oder
  `netCDF4`
- **Achtung:** Der Server blockt automatisierte Zugriffe (HTTP 403). Im Browser
  funktioniert er; für Skripte ggf. Kontakt zum CDIP-Support aufnehmen.

Da CDIP NetCDF liefert, braucht man für die Weiterverarbeitung zusätzlich
`xarray`/`netCDF4`. Für einen schnellen Test reicht es, eine Variable
(z. B. die vertikale Auslenkung) in eine zweispaltige CSV zu exportieren und
diese dann mit `fft_smoothing.py` zu glätten.

## Europäische Bojen

### Cefas WaveNet (UK)

<https://wavenet.cefas.co.uk/> – Wellenbojen rund um Großbritannien, Daten als
CSV über die Webseite. Für die deutsche Nordsee ist das geografisch am
nächsten, aber es sind keine deutschen Stationen.

### Marine Institute ERDDAP (Irland)

<https://erddap.marine.ie/erddap/index.html> – die irischen Wetterbojen M2, M3,
M5 und M6 liefern stündliche Wellen- und Meteowerte. ERDDAP erlaubt den direkten
CSV-Download per URL, z. B.:

```text
https://erddap.marine.ie/erddap/tabledap/IWBNetwork.csv?station_id,time,WaveHeight&station_id=%22M3%22
```

Das ist praktisch, wenn man ohne Browser und ohne Login Daten ziehen will.

### EMODnet Physics (EU)

<https://emodnet.ec.europa.eu/en/physics> bündelt Bojen, Glider und
Feststationen aus ganz Europa. Der zugehörige ERDDAP-Server
(<https://erddap.emodnet-physics.eu/erddap/index.html>) bietet CSV, JSON und
NetCDF. Die Variablennamen unterscheiden sich je Datensatz, daher zuerst die
Datensatzbeschreibung prüfen.

### Rijkswaterstaat (Niederlande)

<https://waterinfo.rws.nl/> – Wasserstände, Wellen und Wind an der
niederländischen Nordseeküste, größtenteils 10-Minuten-Werte. Der Download
erfolgt über die Webseite; die Daten sind offen.

### BSH (Deutschland)

<https://www.bsh.de/DE/DATEN/daten_node.html> – das BSH veröffentlicht Daten des
MARNET-Messnetzes (Nord- und Ostsee) sowie Seegangsstatistiken. Die Auflösung
ist überwiegend 30 Minuten, also für Wellenglättung zu grob. Einzelne Produkte
erfordern eine Registrierung. Für Rohdaten der Bojenbewegung ist das BSH daher
keine gute Quelle.

## Tropischer Pazifik und globale Archive

- **PMEL GTMBA** (<https://www.pmel.noaa.gov/gtmba/data-access/disdel>):
  TAO/TRITON, PIRATA und RAMA. Verlässliche Meteo- und Ozeandaten, teils mit
  Wellenparametern; Text- und NetCDF-Formate.
- **Copernicus Marine** (<https://marine.copernicus.eu/access-data>): global und
  regional, In-situ- und Modelldaten. Kostenloses Konto, Zugriff über
  `copernicusmarine`-Tool oder Webinterface.
- **PANGAEA** (<https://www.pangaea.de/>): archivierte Datensätze aus
  Forschungsprojekten, oft mit DOI. Gut für zitierbare Beispieldaten, aber
  Format und Auflösung sind sehr unterschiedlich.
- **IMOS AODN** (<https://portal.aodn.org.au/>): australische Wellenbojen,
  NetCDF/CSV, frei.
- **MEDS/DFO** (<https://www.meds-sdmm.dfo-mpo.gc.ca/>): kanadische Bojen,
  CSV, frei.

## Checkliste vor dem Glätten

1. **Abtastrate prüfen.** Bestimmt die Nyquist-Frequenz und damit, was der
   Filter überhaupt leisten kann.
2. **Zeitachse prüfen.** NDBC liefert UTC; andere Quellen teils lokale Zeit oder
   uneinheitliche Formate.
3. **Lücken prüfen.** Der Konverter trennt Abschnitte automatisch; bei eigenen
   Daten vorher NaNs oder Ausreißer bereinigen.
4. **Bereits gemittelte Werte beachten.** `WVHT`, `WSPD` & Co. sind keine
   Rohsignale. Die FFT glättet dann nur noch den Verlauf dieser Mittelwerte.
5. **Grenzfrequenz begründen.** `--cutoff 0.1` ist ein Startwert, kein
   Naturgesetz. Bei Wellendaten eher über die Periode argumentieren
   (z. B. „alles unter 4 s ist Rauschen“ → `--cutoff-hz 0.25`).
6. **Lizenz und Zitierhinweis klären.** Die meisten Quellen sind frei, aber
   nicht alle sind gemeinfrei. Bei wissenschaftlicher Nutzung die Quelle
   zitieren (NDBC, Cefas, Marine Institute, CDIP usw.).
