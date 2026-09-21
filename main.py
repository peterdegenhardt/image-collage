#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Collage - feste Fenstergröße, Bilder passen in die Ansicht.
4 Bilder pro DIN A4 Blatt (Querformat). Drag & Drop zum Platzieren,
automatisches neues Blatt bei Überschreitung, PDF-Export.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinterdnd2 as dnd2
from PIL import Image, ImageTk, ImageDraw, ImageOps
import os
import json

# Attempt to import reportlab for PDF export
try:
    from reportlab.pdfgen import canvas as reportlab_canvas
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except Exception:  # ImportError or any other
    REPORTLAB_AVAILABLE = False

# ── Konstanten ────────────────────────────────────────────────
# DIN A4 bei 300 DPI (Portrait)
A4_WIDTH_PX = 2480   # kurze Seite
A4_HEIGHT_PX = 3508  # lange Seite
# Wir wollen Querformat: Breite = lange Seite, Höhe = kurze Seite
LANDSCAPE_WIDTH_PX = A4_HEIGHT_PX
LANDSCAPE_HEIGHT_PX = A4_WIDTH_PX

# feste Fenstergröße für die GUI
CANVAS_W = 900   # Breite des Tkinter-Canvas
CANVAS_H = 600   # Höhe des Tkinter-Canvas

# Skalierungsfaktor: passt das komplette A4-Blatt in das Canvas (mit Abstand)
CANVAS_SCALE = min(CANVAS_W / LANDSCAPE_WIDTH_PX, CANVAS_H / LANDSCAPE_HEIGHT_PX)
# Damit wir ein bisschen Rand haben, könnten wir leicht kleiner machen, aber halten wir es so.

# Umrechnung Pixel zu Punkten für PDF (300 DPI -> 1 Pixel = 1/300 in, 1 Punkt = 1/72 in)
PX_TO_PT = 72 / 300.0  # = 0.24

MAX_IMAGES_PER_PAGE = 4


class ImageCollageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Collage - 4 Bilder pro A4 Blatt (festes Fenster)")
        self.root.geometry(f"{CANVAS_W + 200}x{CANVAS_H + 50}")  # etwas Platz für Seitenleiste
        self.root.minsize(CANVAS_W + 200, CANVAS_H + 50)

        # Zustand
        self.pages = [[]]          # Liste von Seiten, jede Seite ist Liste von Bild-Elementen
        self.current_page_index = 0
        self.page_elements = self.pages[self.current_page_index]

        # Für Drag & Drop
        self.dragging_item = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.item_id_map = {}       # canvas item id -> index in page_elements

        self._build_ui()
        self._bind_events()
        self._render_page()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Canvas mit festen Abmessungen
        canvas_frame = ttk.LabelFrame(main_frame, text="DIN A4 Blatt (Querformat)")
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,5))

        self.canvas = tk.Canvas(canvas_frame, bg="white",
                                width=CANVAS_W, height=CANVAS_H)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Seitenleiste
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
        self.canvas.drop_target_register(dnd2.DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self._on_drop)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

    # ----------------- Drag & Drop -----------------
    def _on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')):
                self._add_image(f)
            else:
                messagebox.showwarning("Unsupported Dateityp",
                                       f"Die Datei {os.path.basename(f)} ist kein unterstütztes Bildformat.")
        self._render_page()

    def _add_image(self, filepath):
        """Fügt ein Bild zur aktuellen Seite hinzu, erstellt bei Bedarf eine neue Seite."""
        if len(self.page_elements) >= MAX_IMAGES_PER_PAGE:
            self._new_page()
        try:
            pil_img = Image.open(filepath)
            # Für die Anzeige erstellen wir ein Thumbnail, das wir skaliert darstellen.
            # Wir behalten das Originalbild für den Export.
            max_display_w = CANVAS_W / CANVAS_SCALE
            max_display_h = CANVAS_H / CANVAS_SCALE
            scale_factor = min(max_display_w / pil_img.width, max_display_h / pil_img.height, 1.0)
            new_w = int(pil_img.width * scale_factor)
            new_h = int(pil_img.height * scale_factor)
            thumb = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
        except Exception as e:
            messagebox.showerror("Fehler beim Laden",
                                 f"Konnte Bild nicht laden:\n{filepath}\n{e}")
            return

        # Ausgangsposition: Mitte des A4-Blattes in Originalkoordinaten
        orig_x = LANDSCAPE_WIDTH_PX / 2
        orig_y = LANDSCAPE_HEIGHT_PX / 2

        elem = {
            "filepath": filepath,
            "pil_image": pil_img,          # Originalbild für Export
            "thumb": thumb,                # Thumbnail für Anzeige (ggf. skaliert)
            "photo": photo,
            "orig_x": orig_x, "orig_y": orig_y,   # Position in Originalkoordinaten (Pixel bei 300 DPI)
            "scale": 1.0,                  # zukünftiger Faktor für Größe (wenn wir skalieren wollen)
            "angle": 0                     # Platzhalter für Drehung
        }
        self.page_elements.append(elem)
        self.status_var.set(f"Bild hinzugefügt: {os.path.basename(filepath)}")

    # ----------------- Canvas Interaction -----------------
    def _on_canvas_click(self, event):
        """Maustklick: prüft, ob auf ein Bild geklickt wurde, um es zu ziehen."""
        item = self.canvas.find_closest(event.x, event.y)
        if item:
            idx = self.item_id_map.get(item[0])
            if idx is not None:
                self.dragging_item = idx
                self.drag_start_x = event.x
                self.drag_start_y = event.y
                self.status_var.set(f"Ziehe Bild {idx+1} auf Seite {self.current_page_index+1}")

    def _on_canvas_drag(self, event):
        if self.dragging_item is not None:
            dx = event.x - self.drag_start_x
            dy = event.y - self.drag_start_y
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            elem = self.page_elements[self.dragging_item]
            # Umrechne Canvas-Verschiebung in Originalkoordinaten
            elem["orig_x"] += dx / CANVAS_SCALE
            elem["orig_y"] += dy / CANVAS_SCALE
            # Optional: Begrenzen auf A4-Blatt
            elem["orig_x"] = max(0, min(LANDSCAPE_WIDTH_PX, elem["orig_x"]))
            elem["orig_y"] = max(0, min(LANDSCAPE_HEIGHT_PX, elem["orig_y"]))
            self._render_page()

    def _on_canvas_release(self, event):
        if self.dragging_item is not None:
            self.status_var.set(f"Bild {self.dragging_item+1} platziert")
            self.dragging_item = None

    # ----------------- Rendering -----------------
    def _render_page(self):
        """Rendert die aktuelle Seite auf dem Canvas mit Skalierung."""
        self.canvas.delete("all")
        self.item_id_map.clear()

        # Zeichne das A4-Blatt als Kontur (skaliert)
        self.canvas.create_rectangle(
            0, 0,
            LANDSCAPE_WIDTH_PX * CANVAS_SCALE,
            LANDSCAPE_HEIGHT_PX * CANVAS_SCALE,
            outline="#cccccc", width=2
        )

        for idx, elem in enumerate(self.page_elements):
            # Position im Canvas
            cx = elem["orig_x"] * CANVAS_SCALE
            cy = elem["orig_y"] * CANVAS_SCALE
            photo = elem["photo"]
            image_id = self.canvas.create_image(cx, cy, image=photo, anchor=tk.CENTER)
            self.item_id_map[image_id] = idx

            # Bildnummer
            self.canvas.create_text(
                cx, cy - 20 * CANVAS_SCALE,
                text=str(idx+1),
                fill="red",
                font=("Segoe UI", max(10, int(10 * CANVAS_SCALE)), "bold")
            )

        # Seiteninfo
        self.canvas.create_text(
            LANDSCAPE_WIDTH_PX * CANVAS_SCALE // 2,
            20 * CANVAS_SCALE,
            text=f"Seite {self.current_page_index+1} von {len(self.pages)}",
            fill="gray",
            font=("Segoe UI", max(10, int(10 * CANVAS_SCALE)))
        )

    # ----------------- Seitenmanagement -----------------
    def _new_page(self):
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
        for page in self.pages:
            page_data = []
            for elem in page:
                page_data.append({
                    "filepath": elem["filepath"],
                    "orig_x": elem["orig_x"],
                    "orig_y": elem["orig_y"],
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
        if "pages" not in data:
            messagebox.showerror("Ungültiges Format", "Die Datei enthält keine 'pages'.")
            return
        self.pages = []
        for page_data in data["pages"]:
            page = []
            for ed in page_data:
                filepath = ed.get("filepath")
                if not filepath or not os.path.exists(filepath):
                    continue
                try:
                    pil_img = Image.open(filepath)
                    # Erstelle Thumbnail für Anzeige (gleiche Logik wie beim Hinzufügen)
                    max_display_w = CANVAS_W / CANVAS_SCALE
                    max_display_h = CANVAS_H / CANVAS_SCALE
                    scale_factor = min(max_display_w / pil_img.width, max_display_h / pil_img.height, 1.0)
                    new_w = int(pil_img.width * scale_factor)
                    new_h = int(pil_img.height * scale_factor)
                    thumb = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(thumb)
                except Exception:
                    continue
                elem = {
                    "filepath": filepath,
                    "pil_image": pil_img,
                    "thumb": thumb,
                    "photo": photo,
                    "orig_x": ed.get("orig_x", LANDSCAPE_WIDTH_PX / 2),
                    "orig_y": ed.get("orig_y", LANDSCAPE_HEIGHT_PX / 2),
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
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Fehlende Bibliothek",
                                 "Das Paket 'reportlab' ist nicht installiert.\nBitte installieren Sie es mit: pip install reportlab")
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
            width, height = landscape(A4)  # in Punkten
            for page_idx, page in enumerate(self.pages):
                for elem in page:
                    img_path = elem["filepath"]
                    try:
                        pil_img = Image.open(img_path)
                    except Exception:
                        continue
                    # Originalbildgröße in Pixeln
                    img_w_px, img_h_px = pil_img.size
                    # Umrechnung zu Punkten bei 300 DPI
                    img_w_pt = img_w_px * PX_TO_PT
                    img_h_pt = img_h_px * PX_TO_PT
                    # Skalierungsfaktor aus Element (falls je implementiert)
                    scale = elem.get("scale", 1.0)
                    img_w_pt *= scale
                    img_h_pt *= scale
                    # Position: orig_x, orig_y in Pixeln -> Punkte
                    x_pt = elem["orig_x"] * PX_TO_PT
                    y_pt = elem["orig_y"] * PX_TO_PT
                    # Beim PDF liegt der Ursprung unten links; y muss von oben berechnet werden
                    # Wir wollen, dass (x_pt, y_pt) der Mittelpunkt des Bildes ist.
                    x1 = x_pt - img_w_pt / 2
                    y1 = height - (y_pt + img_h_pt / 2)
                    c.drawImage(ImageReader(pil_img), x1, y1,
                                width=img_w_pt, height=img_h_pt,
                                preserveAspectRatio=True, mask='auto')
                if page_idx < len(self.pages) - 1:
                    c.showPage()
            c.save()
            messagebox.showinfo("PDF exportiert",
                                f"PDF gespeichert unter:\n{filepath}\nSeiten: {len(self.pages)}")
        except Exception as e:
            messagebox.showerror("Exportfehler",
                                 f"Konnte PDF nicht erzeugen:\n{e}")

def main():
    root = dnd2.Tk()
    app = ImageCollageApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()