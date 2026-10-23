# FFT-Glättung

Ein kleines Kommandozeilenprogramm, das verrauschte Messdaten mit einem
Tiefpass im Frequenzbereich (Fast Fourier Transform) glättet. Es benötigt nur
NumPy und erzeugt zusätzlich ein SVG-Diagramm – ohne Matplotlib oder andere
Plot-Bibliotheken.

## Installation

```bash
python3 -m pip install -r requirements.txt
```

Voraussetzung ist Python 3.9 oder neuer (getestet mit Python 3.14 und NumPy 2.5).

## Schnellstart

```bash
python3 fft_smoothing.py --demo
```

Das erzeugt Beispieldaten (3-Hz- und 8-Hz-Signal plus Rauschen), glättet sie und
schreibt:

| Datei | Inhalt |
| --- | --- |
| `data/demo/demo_input.csv` | die verrauschten Eingangsdaten |
| `output/demo/demo_smoothed.csv` | x, Original, geglättet, Rest |
| `output/demo/demo.svg` | Diagramm zum Öffnen im Browser |

In der Konsole wird zusätzlich ausgegeben, wie stark der Fehler gegenüber dem
unverrauschten Demo-Signal sinkt.

## Ordnerstruktur

Eingaben und Ergebnisse sind getrennt. Rohdaten und eigene Messdateien gehören
nach `data/`, alle erzeugten Dateien nach `output/`:

```text
data/
  demo/           Beispieldaten (demo_input.csv)
  ndbc/           heruntergeladene Bojendaten (46001_WVHT.csv, …)
  eigene/         optional: eigene Messdateien
output/
  demo/           demo_smoothed.csv, demo.svg
  ndbc/           gespiegelte Unterordner: 46001_WVHT_smoothed.csv, 46001_WVHT.svg
  eigene/         Ergebnisse eigener Messdateien
```

Liegt eine Eingabe unter `data/`, wird ihr Unterordner beim Schreiben unter
`output/` gespiegelt. Eine Eingabe außerhalb von `data/` landet direkt in
`output/`. Mit `-o` und `--plot` lassen sich die Pfade jederzeit überschreiben.
Fehlende Ordner werden automatisch angelegt.

## Eigene Daten glätten

```bash
python3 fft_smoothing.py data/eigene/messdaten.csv --cutoff 0.08
```

Standardmäßig wird die letzte Spalte als y und die erste Spalte als x
interpretiert. Eine Kopfzeile ist optional. Unterstützt werden Komma, Semikolon,
Tabulator und Leerraum als Trenner (automatische Erkennung). Eine Datei mit nur
einer Spalte (nur y) funktioniert ebenfalls; dann wird der Zeilenindex als x
verwendet.

Ausgaben (jeweils unter `output/`, Unterordner wie bei der Eingabe):

- `<name>_smoothed.csv` mit `x, original, smoothed, residual`
- `<name>.svg` mit Original, geglättetem Signal und Rest

Beispiel: `data/eigene/messdaten.csv` → `output/eigene/messdaten_smoothed.csv`
und `output/eigene/messdaten.svg`.

Die Spalte `residual` ist der entfernte Anteil (`original - smoothed`). Bei einer
gut gewählten Grenzfrequenz entspricht er überwiegend dem Rauschen; er enthält
aber immer auch Signalanteile nahe der Grenzfrequenz.

Kommentarzeilen am Dateianfang (`# ...`) werden als Metadaten gelesen und in der
Konsole unter „Datenherkunft“ ausgegeben. Die Ergebnisdatei enthält diese
Herkunft sowie die verwendeten Filtereinstellungen wieder als Kommentarzeilen.
Damit bleibt nachvollziehbar, welche Messgröße, Station und welcher Zeitraum
verarbeitet wurde.

Optional kann eine Datei die Zeitachse mit `# x-Einheit: s`, `# x-Einheit: min`
oder `# x-Einheit: h` beschreiben. Dann zeigt das Programm zusätzlich
Abtastrate, Nyquist-Frequenz, Grenzfrequenz in Hz und die zugehörigen Perioden an;
`--cutoff-hz` funktioniert damit auch ohne `--fs`.

In der Konsole erscheinen außerdem Datenpunkte, Abtastintervall, Zeitumfang,
gegebenenfalls interpolierte Rasterpunkte sowie die RMS-Werte von Original,
geglättetem Signal und entferntem Anteil.

### Beispiele

```bash
# Grenzfrequenz als Anteil der Nyquist-Frequenz (hier 8 %)
python3 fft_smoothing.py data/eigene/messdaten.csv --cutoff 0.08

# Grenzfrequenz direkt in Hz (Abtastrate 200 Hz)
python3 fft_smoothing.py data/eigene/messdaten.csv --cutoff-hz 12 --fs 200

# Sanfter Gauß-Filter statt Butterworth
python3 fft_smoothing.py data/eigene/messdaten.csv --filter gaussian --cutoff 0.06

# Andere Spalten, Semikolon, ohne Plot
python3 fft_smoothing.py data/eigene/messdaten.csv --x-col 1 --y-col 3 --delimiter ';' --no-plot

# Zieldateien festlegen
python3 fft_smoothing.py data/eigene/messdaten.csv -o output/eigene/ergebnis.csv --plot output/eigene/ergebnis.svg
```

## Echte Bojendaten

Für einen realistischen Test gibt es den kleinen Konverter `ndbc_to_csv.py`. Er
lädt öffentliche Daten des NOAA National Data Buoy Center (NDBC), filtert
fehlende Werte und schreibt eine CSV, die direkt von `fft_smoothing.py` gelesen
wird. Er benötigt nur die Python-Standardbibliothek.

```bash
# letzte 30 Tage Wellenhöhe der Boje 46001 (Golf von Alaska)
python3 ndbc_to_csv.py 46001 --variable WVHT --days 30
python3 fft_smoothing.py data/ndbc/46001_WVHT.csv --cutoff 0.1

# historisches Jahr, z. B. Windgeschwindigkeit 2025
python3 ndbc_to_csv.py 46001 --year 2025 --variable WSPD --days 60

# verfügbare Spalten und zusammenhängende Abschnitte anzeigen
python3 ndbc_to_csv.py 46001 --list-variables
python3 ndbc_to_csv.py 46001 --variable WVHT --list-segments
```

Der Konverter schreibt standardmäßig nach
`data/ndbc/<station>_<variable>[_<jahr>].csv`, legt den Ordner bei Bedarf an und
verwendet den längsten lückenarmen Abschnitt.
Mit `--keep-gaps` bleiben alle Werte erhalten, mit `--with-timestamp` entsteht
zusätzlich eine Datei mit UTC-Zeitstempeln. Er schreibt Stationsname, Position,
Stationstyp, Messgröße mit Kurzbeschreibung, Einheit, Abtastung, Zeitraum und
Bezugsquelle als Kommentarzeilen in die CSV. `fft_smoothing.py` zeigt diese
Angaben unter „Datenherkunft“ an und übernimmt sie in die Ergebnisdatei.

`--list-variables` zeigt zu jeder Spalte auch die Bedeutung, z. B.
`WVHT  m  signifikante Wellenhöhe`. Weitere Quellen – auch für Rohdaten mit
1–2 Hz – stehen in [DATENQUELLEN.md](DATENQUELLEN.md).

**Wichtig:** NDBC liefert bereits gemittelte Wellen- und Wetterwerte (meist alle
10 Minuten). Damit lässt sich der Wetterverlauf glätten, aber keine einzelne
Welle. Für die Bojenbewegung im Sekundentakt braucht man Rohdaten, z. B. von
CDIP.

## Interaktive Web-Oberfläche

Für die Auswahl der Daten und die interaktive Untersuchung des Diagramms gibt es
eine lokale Web-Oberfläche. Sie benötigt nur die Python-Standardbibliothek und
läuft ohne Build-Schritt, CDN oder zusätzliche Pakete:

```bash
python3 webui.py
```

Danach `http://127.0.0.1:8000/` im Browser öffnen. Mit `--port 8080` und
`--host 0.0.0.0` lassen sich Port und Adresse ändern.

Die Oberfläche bietet:

- 12 kuratierte NDBC-Stationen (oder eine beliebige Stations-ID) und alle
  verfügbaren Messgrößen,
- Echtzeitdaten der letzten Tage oder ein historisches Jahr,
- Zeiträume werden auf die tatsächlich verfügbaren Daten begrenzt: Die
  Jahresauswahl enthält nur vorhandene Archivjahre ab 2007 (ältere Dateien
  nutzen ein anderes NDBC-Format), der Tage-Regler reicht höchstens bis zum
  Beginn der Echtzeitreihe,
- Regler für Grenzfrequenz, Filtertyp, Ordnung, Detrending und Padding,
- ein interaktives Diagramm mit Original, geglättetem Signal und Rest:
  Mausrad = zoomen, Ziehen = verschieben, Doppelklick = zurücksetzen,
  Hover = Messwerte anzeigen,
- Kennzahlen und Metadaten zur geladenen Messreihe,
- helles und dunkles Design (folgt der Systemeinstellung, lässt sich oben rechts
  umschalten und wird im Browser gespeichert),
- eine Demo sowie den Upload eigener CSV-Dateien per Dateiauswahl oder
  Drag & Drop.

Der Server lädt die NDBC-Daten bei Bedarf herunter und rechnet die Glättung
lokal. Ergebnisse werden nicht gespeichert; die Web-Oberfläche ist für die
explorative Analyse gedacht. Für reproduzierbare Dateien weiterhin die
Kommandozeile verwenden.

## Wie es funktioniert

1. **Einlesen und bereinigen:** NaN-Werte werden linear interpoliert. Sind die
   x-Werte unregelmäßig, wird auf ein äquidistantes Raster interpoliert (die
   geglätteten Werte werden anschließend auf die Original-x zurückgerechnet).
2. **Detrending:** Ein linearer Trend wird abgezogen, damit die FFT keine
   Sprünge an den Datengrenzen sieht. Nach dem Filtern wird der Trend wieder
   addiert. Mit `--no-detrend` lässt sich das abschalten.
3. **Spiegel-Padding:** Die Ränder werden gespiegelt (`--pad`, Standard 10 %),
   um Leckeffekte und Überschwingen zu reduzieren.
4. **FFT:** Vom Signal wird die reelle FFT berechnet. Jede Frequenz wird mit der
   Antwort eines Tiefpasses multipliziert; hohe Frequenzen (Rauschen) werden
   gedämpft, tiefe Frequenzen (der Nutzsignalverlauf) bleiben erhalten.
5. **Inverse FFT:** Zurück ins Zeitbereich, Padding entfernen, Trend addieren.

Weil nur die Amplituden der Frequenzen verändert werden und keine Phasen, ist
der Filter **nullphasig**: Das geglättete Signal wird nicht zeitlich verschoben.

## Parameter

| Option | Bedeutung | Standard |
| --- | --- | --- |
| `--cutoff C` | Grenzfrequenz als Anteil der Nyquist-Frequenz, `0 < C <= 1` | `0.1` |
| `--cutoff-hz H` | Grenzfrequenz in Hz; braucht `--fs` oder ein x-Raster in Sekunden | – |
| `--fs F` | Abtastrate in Hz (für `--cutoff-hz` und die Anzeige) | aus x-Raster, falls `--cutoff-hz` |
| `--filter` | `butterworth`, `gaussian` oder `ideal` | `butterworth` |
| `--order N` | Ordnung des Butterworth-Filters | `4` |
| `--pad P` | Spiegel-Padding als Anteil der Datenlänge | `0.1` |
| `--no-detrend` | linearen Trend nicht entfernen | aus |
| `--x-col`, `--y-col` | Spaltenindizes (negativ ab dem Ende) | `0`, `-1` |
| `--delimiter` | `auto`, `,`, `;`, `tab`, `space` | `auto` |
| `--plot SVG` | SVG-Plot an diesen Pfad schreiben | neben der Ausgabedatei |
| `--no-plot` | keinen Plot schreiben | – |
| `--quiet` | keine Zusammenfassung ausgeben | – |

### Filtertypen

- **Butterworth** (Standard): guter Kompromiss aus scharfer Trennung und
  geringem Überschwingen. Höhere Ordnung = steilere Flanke.
- **Gauß**: sehr weicher Übergang, kaum Ringing, aber weniger Rauschunterdrückung
  bei gleicher Grenzfrequenz.
- **Ideal**: harte Kante. Entfernt Rauschen am aggressivsten, neigt aber zu
  Überschwingen (Gibbs-Effekt) an Sprüngen.

### Grenzfrequenz wählen

Die Nyquist-Frequenz ist die halbe Abtastrate. `--cutoff 0.1` behält also die
unteren 10 % des Frequenzbands. Die Grenzfrequenz ist der −3-dB-Punkt des
Filters (beim idealen Filter die harte Kante). Als Startwert ist `0.05` bis
`0.15` sinnvoll; zu hoch gewählt bleibt Rauschen übrig, zu niedrig gewählt
werden echte Signalanteile mitgeglättet. Das SVG zeigt den Rest und hilft beim
Einstellen. Bei `--cutoff-hz` wird die Grenzfrequenz direkt in Hz angegeben.

## Grenzen

- Die FFT setzt **äquidistante** Abtastung voraus. Unregelmäßige x-Werte werden
  automatisch interpoliert; starke Lücken sollten vorher bereinigt werden.
- Der Filter ist ein **globaler** Tiefpass: Sehr kurze, echte Spitzen im Signal
  werden ebenfalls gedämpft, wenn sie hohe Frequenzanteile enthalten.
- Für Echtzeit-Anwendungen oder Datenströme ist das Programm nicht gedacht –
  es verarbeitet eine komplette Datei.
- Dezimalkommas (`1,23`) werden nicht als Zahlen erkannt, da das Komma als
  Spaltentrenner dient. Bitte Punkt als Dezimaltrennzeichen verwenden.

## Tests

```bash
python3 -m unittest -v test_fft_smoothing.py test_ndbc_to_csv.py test_webui.py
```

Die Tests prüfen unter anderem, dass die FFT-Glättung den Fehler gegenüber einem
bekannten Nutzsignal reduziert, dass das Einlesen mit Semikolon und Kopfzeile
funktioniert, dass das erzeugte SVG gültiges XML ist, dass Eingaben unter `data/`
korrekt nach `output/` gespiegelt werden und dass der NDBC-Konverter Kopfzeilen,
fehlende Werte und Lücken korrekt behandelt. `test_webui.py` prüft die
API-Pipeline der Web-Oberfläche ohne Netzwerkzugriff.
