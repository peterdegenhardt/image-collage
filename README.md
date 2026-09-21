# Image Collage

Eine einfache Python/Tkinter-Anwendung zum Anordnen von bis zu 4 Bildern pro DIN A4 Blatt im Querformat.
Bilder können per Drag & Drop eingefügt werden. Beim Überschreiten der Begrenzung wird automatisch ein neues Blatt erstellt.
Die Blätter können als PDF exportiert werden (mit reportlab), wobei die Dateigröße gering gehalten wird (ähnlich wie beim CAQ-Prüfstempel Projekt).

## Features

- Drag & Drop von Bilddateien (PNG, JPG, JPEG, BMP, GIF, TIFF)
- Maximal 4 Bilder pro A4-Blatt (Querformat)
- Automatisches Erstellen neuer Blätter bei Bedarf
- Bilder können per Maus verschoben werden
- Export als mehrseitiges PDF (DIN A4 Querformat)
- Projekt speichern und laden (JSON-Format)
- Einfache, ressourcenschonende Speicherung (ähnliche Qualität wie CAQ-Prüfstempel beim „Zeichnung+Foto speichern“)

## Installation

### Abhängigkeiten

```bash
pip install -r requirements.txt
```

### Ausführung

```bash
python main.py
```

### Build zur EXE (Windows)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "ImageCollage" main.py
```

Die erstellte EXE befindet sich im `dist`-Ordner.

## Lizenz

Dieses Projekt ist unter der MIT-Lizenz lizenziert – siehe [LICENSE](LICENSE) für Details.