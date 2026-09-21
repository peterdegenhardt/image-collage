#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Collage - 4 Bilder pro DIN A4 Blatt (Querformat) mit Drag & Drop,
Export als PDF mit niedriger Dateigröße, ähnliche Qualität wie CAQ-Prüfstempel.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinterdnd2 as dnd2
from PIL import Image, ImageTk, ImageDraw
import os
import json
from datetime import datetime

# Versuch, reportlab für PDF-Erzeugung zu importieren
try:
    from reportlab.pdfgen import canvas as reportlab_canvas
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Konstanten
A4_WIDTH_PX = 2480   # Portrait Breite bei 300 DPI
A4_HEIGHT_PX = 3508  # Portrait Höhe bei 300 DPI
# Landschaft: Breite und Höhe tauschen
PAGE_WIDTH_PX = A4_HEIGHT_PX   # 3508
PAGE_HEIGHT_PX = A4_WIDTH_PX   # 2480
DPI = 300
# Umrechnung Pixel zu Punkten (1 Punkt = 1/72 Zoll, 300 DPI => 300/72 = 4.1667... Punkt pro Pixel)
PX_TO_PT = 72 / DPI  # 0.24
# Maximale Anzahl Bilder pro Seite
MAX_IMAGES_PER_PAGE = 4
# Standardbildgröße beim Einfügen (Pixel) - wird später skaliert, um in die Seite zu passen
DEFAULT_IMAGE_SIZE_PX = 200

class ImageCollageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Collage - 4 Bilder pro A4 Blatt")
        self.root.geometry("1200x800")
        self.root.minsize(800, 600)

        # Zustand
        self.pages = [[]]  # Liste von Seiten, jede Seite ist eine Liste von Bild-Elementen
        self.current_page_index = 0
        # Jedes Bild-Element: dict mit Pfad, PIL.Image (thumbnail), PhotoImage, Position (x,y), Scale
        self.page_elements = self.pages[self.current_page_index]

        # Für Drag & Drop und Bewegung
        self.dragging_item = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.item_id_map = {}  # Maps canvas item id zu Index in page_elements

        # UI aufbauen
        self._build_ui()
        self._bind_events()

        # Anfangsseite anzeigen
        self._render_page()

    def _build_ui(self):
        # Hauptframe
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Canvas für das Blatt
        canvas_frame = ttk.LabelFrame(main_frame, text="DIN A4 Blatt (Querformat)")
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))

        self.canvas = tk.Canvas(canvas_frame, bg="white", width=PAGE_WIDTH_PX, height=PAGE_HEIGHT_PX)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Seitenleiste für Steuerung
        side_frame = ttk.Frame(main_frame, width=200)
        side_frame.pack(side=tk.RIGHT, fill=tk.Y)
        side_frame.pack_propagate(False)

        ttk.Label(side_frame, text="Steuerung", font=("Segoe UI", 10, "bold")).pack(pady=(0,10))

        ttk.Button(side_frame, text="Neue Seite", command=self._new_page).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Vorherige Seite", command=self._prev_page).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Nächste Seite", command=self._next_page).pack(fill=tk.X, pady=2)
        ttk.Separator(side_frame).pack(fill=tk.X, pady=10)
        ttk.Button(side_frame, text="Als PDF speichern", command=self._save_pdf).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Projekt speichern", command=self._save_project).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Projekt laden", command=self._load_project).pack(fill=tk.X, pady=2)
        ttk.Separator(side_frame).pack(fill=tk.X, pady=10)
        ttk.Button(side_frame, text="Beenden", command=self.root.quit).pack(fill=tk.X, pady=2)

        # Statusleiste
        self.status_var = tk.StringVar()
        self.status_var.set("Bereit – Bilder per Drag & Drop auf die Fläche ziehen")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_events(self):
        # Canvas Events für Drag & Drop und Bildbewegung
        self.canvas.drop_target_register(dnd2.DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self._on_drop)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

    # ----------------- Drag & Drop -----------------
    def _on_drop(self, event):
        """Handhabt das Fallenlassen von Dateien auf dem Canvas."""
        files = self.root.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')):
                self._add_image(f)
            else:
                messagebox.showwarning("Unsupported Dateityp", f"Die Datei {os.path.basename(f)} ist kein unterstütztes Bildformat.")
        self._render_page()

    def _add_image(self, filepath):
        """Fügt ein Bild zur aktuellen Seite hinzu, erstellt bei Bedarf eine neue Seite."""
        # Prüfe, ob aktuelle Seite voll ist
        if len(self.page_elements) >= MAX_IMAGES_PER_PAGE:
            self._new_page()
        # Lade Bild und erstelle Thumbnail für Anzeige
        try:
            pil_img = Image.open(filepath)
            # Für die Anzeige skalieren wir auf eine maximale Größe, behalten Aspect Ratio bei
            pil_img.thumbnail((DEFAULT_IMAGE_SIZE_PX, DEFAULT_IMAGE_SIZE_PX), Image.LANCZOS)
            photo = ImageTk.PhotoImage(pil_img)
        except Exception as e:
            messagebox.showerror("Fehler beim Laden", f"Konnte Bild nicht laden:\n{filepath}\n{e}")
            return

        # Position: mittig auf der Canvas (oder leicht versetzt, um Überlappung zu vermeiden)
        x = PAGE_WIDTH_PX // 2
        y = PAGE_HEIGHT_PX // 2
        # Element-Objekt
        elem = {
            "filepath": filepath,
            "pil_image": pil_img,      # Originalbild (für Export)
            "thumbnail": pil_img,      # Wir benutzen das gleiche für Anzeige (klein)
            "photo": photo,
            "x": x, "y": y,
            "scale": 1.0,              # Skalierungsfaktor für Export (1 = Originalgröße bei 300 DPI)
            "angle": 0,                # Drehung (noch nicht implementiert, Platzhalter)
        }
        self.page_elements.append(elem)
        self.status_var.set(f"Bild hinzugefügt: {os.path.basename(filepath)}")

    # ----------------- Canvas Interaction -----------------
    def _on_canvas_click(self, event):
        """Maustklick: prüft, ob auf ein Bild geklickt wurde, um es zu ziehen."""
        item = self.canvas.find_closest(event.x, event.y)
        if item:
            # Prüfen, ob das Item ein Bild-Item ist (wir haben alle Bilder als IMAGE-Items angelegt)
            # Wir speichern die Mapping in item_id_map
            idx = self.item_id_map.get(item[0])
            if idx is not None:
                self.dragging_item = idx
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.status_var.set(f"Ziehe Bild {idx+1} auf Seite {self.current_page_index+1}")

    def _on_canvas_drag(self, event):
        """Während des Ziehens: Bild mit der Maus bewegen."""
        if self.dragging_item is not None:
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            self.drag_start_x = event.x
            self.drag_start_y = event.y

            elem = self.page_elements[self.dragging_item]
            elem["x"] += dx
            elem["y"] += dy
            # Begrenzen auf Canvas-Bereich (optional)
            elem["x"] = max(0, min(PAGE_WIDTH_PX, elem["x"]))
            elem["y"] = max(0, min(PAGE_HEIGHT_PX, elem["y"]))
            self._render_page()

    def _on_canvas_release(self, event):
        """Maustaste loslassen: Ziehen beenden."""
        if self.dragging_item is not None:
            self.status_var.set(f"Bild {self.dragging_item+1} platziert")
            self.dragging_item = None

    # ----------------- Rendering -----------------
    def _render_page(self):
        """Rendert die aktuelle Seite auf dem Canvas."""
        self.canvas.delete("all")
        self.item_id_map.clear()

        # Hintergrund: A4 Blatt Kontur (optional)
        self.canvas.create_rectangle(0, 0, PAGE_WIDTH_PX, PAGE_HEIGHT_PX, outline="#cccccc", width=2)

        for idx, elem in enumerate(self.page_elements):
            # Bild auf Canvas platzieren
            # Wir verwenden das thumbnail (bereits skaliert) für die Anzeige
            photo = elem["photo"]
            # Position ist die Mitte des Bildes
            x = elem["x"]
            y = elem["y"]
            image_id = self.canvas.create_image(x, y, image=photo, anchor=tk.CENTER)
            self.item_id_map[image_id] = idx

            # Optional: Nummer anzeigen
            self.canvas.create_text(x, y - 20, text=str(idx+1), fill="red", font=("Segoe UI", 10, "bold"))

        # Seiteninfo
        self.canvas.create_text(PAGE_WIDTH_PX//2, 20, text=f"Seite {self.current_page_index+1} von {len(self.pages)}",
                                fill="gray", font=("Segoe UI", 10))

    def _new_page(self):
        """Erstellt eine neue leere Seite und macht sie aktuell."""
        self.pages.append([])
        self.current_page_index = len(self.pages) - 1
        self.page_elements = self.pages[self.current_page_index]
        self.status_var.set(f"Neue Seite erstellt (Seite {self.current_page_index+1})")
        self._render_page()

    def _prev_page(self):
        if self.current_page_index > 0:
            self.current_page_index -= 1
            self.page_elements = self.pages[self.current_page_index]
            self._render_page()

    def _next_page(self):
        if self.current_page_index < len(self.pages) - 1:
            self.current_page_index += 1
            self.page_elements = self.pages[self.current_page_index]
            self._render_page()

    # ----------------- Projekt speichern/laden -----------------
    def _save_project(self):
        """Speichert die aktuelle Zustandsdatei (JSON)."""
        if not any(self.pages):
            messagebox.showinfo("Hinweis", "Nichts zu speichern.")
            return
        filepath = filedialog.asksaveasfilename(
            title="Projekt speichern",
            defaultextension=".icollage",
            filetypes=[("Image Collage Projekt", "*.icollage"), ("Alle Dateien", "*.*")]
        )
        if not filepath:
            return
        data = {
            "version": "1.0.0",
            "pages": []
        }
        for page_idx, page in enumerate(self.pages):
            page_data = []
            for elem in page:
                # Wir speichern nur die notwendigen Daten: Pfad, Position, Scale, Winkel
                # Das eigentliche Bild wird beim Laden erneut geöffnet
                page_data.append({
                    "filepath": elem["filepath"],
                    "x": elem["x"],
                    "y": elem["y"],
                    "scale": elem.get("scale", 1.0),
                    "angle": elem.get("angle", 0)
                })
            data["pages"].append(page_data)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Gespeichert", f"Projekt gespeichert unter:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Projekt nicht speichern:\n{e}")

    def _load_project(self):
        """Lädt ein Projekt aus JSON."""
        filepath = filedialog.askopenfilename(
            title="Projekt öffnen",
            filetypes=[("Image Collage Projekt", "*.icollage"), ("Alle Dateien", "*.*")]
        )
        if not filepath:
            return
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte Projektdatei nicht lesen:\n{e}")
            return

        # Grundlegende Validierung
        if "pages" not in data:
            messagebox.showerror("Ungültiges Format", "Die Datei enthält keine 'pages'.")
            return

        self.pages = []
        for page_data in data["pages"]:
            page = []
            for ed in page_data:
                filepath = ed.get("filepath")
                if not filepath or not os.path.exists(filepath):
                    # Bild fehlt – überspringen oder Platzhalter?
                    continue
                try:
                    pil_img = Image.open(filepath)
                    # Thumbnail für Anzeige
                    thumb = pil_img.copy()
                    thumb.thumbnail((DEFAULT_IMAGE_SIZE_PX, DEFAULT_IMAGE_SIZE_PX), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(thumb)
                except Exception:
                    continue
                elem = {
                    "filepath": filepath,
                    "pil_image": pil_img,
                    "thumbnail": thumb,
                    "photo": photo,
                    "x": ed.get("x", PAGE_WIDTH_PX//2),
                    "y": ed.get("y", PAGE_HEIGHT_PX//2),
                    "scale": ed.get("scale", 1.0),
                    "angle": ed.get("angle", 0)
                }
                page.append(elem)
            self.pages.append(page)
        if not self.pages:
            self.pages = [[]]
        self.current_page_index = 0
        self.page_elements = self.pages[self.current_page_index]
        self._render_page()
        messagebox.showinfo("Geladen", f"Projekt aus {os.path.basename(filepath)} geladen.")

    # ----------------- PDF Export -----------------
    def _save_pdf(self):
        """Exportiert alle Seiten als PDF."""
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Fehlende Bibliothek", "Das Paket 'reportlab' ist nicht installiert.\nBitte installieren Sie es mit: pip install reportlab")
            return
        if not any(self.pages):
            messagebox.showinfo("Hinweis", "Keine Bilder zum Exportieren vorhanden.")
            return

        filepath = filedialog.asksaveasfilename(
            title="Als PDF speichern",
            defaultextension=".pdf",
            filetypes=[("PDF Dokument", "*.pdf"), ("Alle Dateien", "*.*")]
        )
        if not filepath:
            return

        try:
            c = reportlab_canvas.Canvas(filepath, pagesize=landscape(A4))
            width, height = landscape(A4)  # Größe in Punkten
            for page_idx, page in enumerate(self.pages):
                for elem in page:
                    # Bild öffnen und für reportlab vorbereiten
                    img_path = elem["filepath"]
                    try:
                        pil_img = Image.open(img_path)
                    except Exception:
                        continue
                    # Wir wollen das Bild mit bestimmter Größe und Position platzieren.
                    # Die Koordinaten im Canvas sind in Pixel bei 300 DPI.
                    # Umrechnung zu Punkten: x_pt = x_px * PX_TO_PT, y_pt = y_px * PX_TO_PT
                    x_pt = elem["x"] * PX_TO_PT
                    y_pt = elem["y"] * PX_TO_PT
                    # Skalierung: Das Bild soll mit dem Faktor scale (aus UI) gezeichnet werden.
                    # Wir berechnen die Breite und Höhe in Punkten basierend auf Originalbildgröße und DPI.
                    # Originalbildgröße in Pixel:
                    img_w_px, img_h_px = pil_img.size
                    # Umrechnung zu Punkten bei 300 DPI:
                    img_w_pt = img_w_px * PX_TO_PT
                    img_h_pt = img_h_px * PX_TO_PT
                    # Anwenden des Skalierungsfaktors
                    img_w_pt *= elem.get("scale", 1.0)
                    img_h_pt *= elem.get("scale", 1.0)
                    # Drehung (falls implementiert) – reportlab kann drehen, aber wir überspringen für simplicity
                    # Bild zeichnen
                    c.drawImage(ImageReader(pil_img), x_pt - img_w_pt/2, height - y_pt - img_h_pt/2,
                                width=img_w_pt, height=img_h_pt, preserveAspectRatio=True, mask='auto')
                # Seite beenden (außer letzte Seite)
                if page_idx < len(self.pages) - 1:
                    c.showPage()
            c.save()
            messagebox.showinfo("PDF exportiert", f"PDF gespeichert unter:\n{filepath}\nSeiten: {len(self.pages)}")
        except Exception as e:
            messagebox.showerror("Exportfehler", f"Konnte PDF nicht erzeugen:\n{e}")

def main():
    root = dnd2.Tk()
    app = ImageCollageApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()