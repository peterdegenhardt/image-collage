#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Collage - fixed quadrant layout with correct scaling for fixed window.
4 images placed in fixed quadrants of A4 landscape page.
Each image is scaled to fit its quadrant without overlap.
PDF export uses downscaled images (40%) and JPEG quality 70 to keep file size small.
Additional tools: Text, Circle, Rectangle, Arrow.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinterdnd2 as dnd2
from PIL import Image, ImageTk
import os
import json
import io

# Try to import reportlab for PDF export
try:
    from reportlab.pdfgen import canvas as reportlab_canvas
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# ----------------------- Constants -----------------------
# A4 portrait dimensions in mm
A4_W_MM, A4_H_MM = 210, 297   # width, height portrait
# Landscape: width = 297mm, height = 210mm
LAND_W_MM, LAND_H_MM = A4_H_MM, A4_W_MM

# Convert to pixels at 300 DPI
MM_TO_PX = 300 / 25.4  # pixels per mm
LAND_W_PX = int(LAND_W_MM * MM_TO_PX)   # 3508
LAND_H_PX = int(LAND_H_MM * MM_TO_PX)   # 2480

# Split into quadrants (equal size)
HALF_W = LAND_W_PX // 2
HALF_H = LAND_H_PX // 2

# Quadrants in page pixels (x0, y0, width, height)
QUADRANTS_PX = [
    (0, 0, HALF_W, HALF_H),           # 0: top-left
    (0, HALF_H, HALF_W, HALF_H),      # 1: bottom-left
    (HALF_W, 0, HALF_W, HALF_H),      # 2: top-right
    (HALF_W, HALF_H, HALF_W, HALF_H)  # 3: bottom-right
]

# Fixed window size for the GUI (canvas)
CANVAS_W_PX = 900
CANVAS_H_PX = 600

# Scale to fit the whole A4 landscape page into the canvas
CANVAS_SCALE = min(CANVAS_W_PX / LAND_W_PX, CANVAS_H_PX / LAND_H_PX)

# Quadrants in canvas (screen) pixels
QUADRANTS = [
    (x0 * CANVAS_SCALE, y0 * CANVAS_SCALE, w * CANVAS_SCALE, h * CANVAS_SCALE)
    for (x0, y0, w, h) in QUADRANTS_PX
]

MAX_IMAGES = 4

# PDF export settings (to keep file size small)
PDF_EXPORT_SCALE = 0.4      # downscale to 40% of original size (like CAQ)
PDF_JPEG_QUALITY = 70       # JPEG quality for embedded images


class ImageCollageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Collage - 4 quadrants, correct scaling")
        self.root.geometry(f"{CANVAS_W_PX + 200}x{CANVAS_H_PX + 50}")
        self.root.minsize(CANVAS_W_PX + 200, CANVAS_H_PX + 50)

        # State: one dict per slot, or None
        self.slots: list[dict | None] = [None] * MAX_IMAGES
        self.next_slot = 0

        # Annotation state
        self.current_tool = None  # None, 'text', 'circle', 'rect', 'arrow'
        self.annotations = []     # list of dicts for drawn objects

        self._build_ui()
        self._bind_events()
        self._render_canvas()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Canvas
        canvas_frame = ttk.LabelFrame(main_frame, text="DIN A4 Blatt (Querformat)")
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.canvas = tk.Canvas(canvas_frame, bg="white",
                                width=CANVAS_W_PX, height=CANVAS_H_PX)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Side panel
        side_frame = ttk.Frame(main_frame, width=200)
        side_frame.pack(side=tk.RIGHT, fill=tk.Y)
        side_frame.pack_propagate(False)

        ttk.Label(side_frame, text="Steuerung", font=("Segoe UI", 10, "bold")).pack(pady=(0, 10))

        ttk.Button(side_frame, text="Neue Seite (reset)", command=self._reset_slots).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Als PDF speichern", command=self._save_pdf).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Projekt speichern", command=self._save_project).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Projekt laden", command=self._load_project).pack(fill=tk.X, pady=2)
        ttk.Separator(side_frame).pack(fill=tk.X, pady=10)
        ttk.Button(side_frame, text="Beenden", command=self.root.quit).pack(fill=tk.X, pady=2)

        # Tools
        ttk.Label(side_frame, text="Werkzeuge", font=("Segoe UI", 10, "bold")).pack(pady=(10, 5))
        ttk.Button(side_frame, text="Text", command=self._set_tool_text).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Kreis", command=self._set_tool_circle).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Rechteck", command=self._set_tool_rect).pack(fill=tk.X, pady=2)
        ttk.Button(side_frame, text="Pfeil", command=self._set_tool_arrow).pack(fill=tk.X, pady=2)

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Bereit – Bilder per Drag & Drop auf die Quadranten ziehen")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_events(self):
        self.canvas.drop_target_register(dnd2.DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self._on_drop)
        self.canvas.bind("<Button-1>", self._on_canvas_click)

    # ------------------- Tool selection -------------------
    def _set_tool_text(self):
        self.current_tool = 'text'
        self.status_var.set("Werkzeug: Text – klicke auf die Fläche, um Text einzufügen")

    def _set_tool_circle(self):
        self.current_tool = 'circle'
        self.status_var.set("Werkzeug: Kreis – klicke auf die Fläche, um einen Kreis einzufügen")

    def _set_tool_rect(self):
        self.current_tool = 'rect'
        self.status_var.set("Werkzeug: Rechteck – klicke auf die Fläche, um ein Rechteck einzufügen")

    def _set_tool_arrow(self):
        self.current_tool = 'arrow'
        self.status_var.set("Werkzeug: Pfeil – klicke auf die Fläche, um einen Pfeil einzufügen")

    # ------------------- Drag & Drop -------------------
    def _on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')):
                self._add_image(f)
            else:
                messagebox.showwarning("Unsupported Dateityp",
                                       f"Die Datei {os.path.basename(f)} ist kein unterstütztes Bildformat.")
        self._render_canvas()

    def _add_image(self, filepath):
        if self.next_slot >= MAX_IMAGES:
            messagebox.showinfo("Info", "Alle vier Quadranten sind belegt. Bitte resetten oder ein Bild ersetzen.")
            return
        try:
            pil_img = Image.open(filepath)
        except Exception as e:
            messagebox.showerror("Fehler beim Laden",
                                 f"Konnte Bild nicht laden:\n{filepath}\n{e}")
            return

        slot_idx = self.next_slot
        qx0, qy0, qw, qh = QUADRANTS[slot_idx]

        # Scale image to fit quadrant (preserve aspect, do not upscale)
        img_w_px, img_h_px = pil_img.size
        scale_w = qw / img_w_px
        scale_h = qh / img_h_px
        scale = min(scale_w, scale_h, 1.0)  # 1.0 prevents upscaling
        new_w = max(1, int(img_w_px * scale))
        new_h = max(1, int(img_h_px * scale))
        
        # Create thumbnail for display (already in screen pixels)
        thumb = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(thumb)

        # Store original image and prepared thumbnail for display
        self.slots[slot_idx] = {
            "filepath": filepath,
            "original": pil_img,
            "thumb": thumb,
            "photo": photo,
            "display_w": new_w,
            "display_h": new_h,
            # For debugging
            "scale_used": scale,
            "quadrant_px": (qw, qh),
            "original_size": (img_w_px, img_h_px),
            "scaled_size": (new_w, new_h)
        }
        self.next_slot += 1
        self.status_var.set(f"Bild {slot_idx + 1} platziert (Quadrant {slot_idx + 1}) - Skaliert auf {new_w}x{new_h} Bildschirmpx")
        self._render_canvas()

    # ------------------- Canvas click for tools -------------------
    def _on_canvas_click(self, event):
        if self.current_tool is None:
            return
        x, y = event.x, event.y
        if self.current_tool == 'text':
            self._add_text_annotation(x, y)
        elif self.current_tool == 'circle':
            self._add_circle_annotation(x, y)
        elif self.current_tool == 'rect':
            self._add_rect_annotation(x, y)
        elif self.current_tool == 'arrow':
            self._add_arrow_annotation(x, y)
        # keep tool active for multiple clicks
        self._render_canvas()

    def _add_text_annotation(self, x, y):
        text = simpledialog.askstring("Text eingeben", "Bitte Text eingeben:", parent=self.root)
        if text is None:
            return
        text = text.strip()
        if not text:
            return
        self.annotations.append({
            "type": "text",
            "x": x,
            "y": y,
            "text": text,
            "fontsize": 12
        })
        self.status_var.set(f"Text hinzugefügt: '{text}'")

    def _add_circle_annotation(self, x, y):
        radius = 15  # canvas pixels
        self.annotations.append({
            "type": "circle",
            "x": x,
            "y": y,
            "r": radius
        })
        self.status_var.set(f"Kreis hinzugefügt (Radius {radius} px)")

    def _add_rect_annotation(self, x, y):
        w, h = 30, 20  # canvas pixels
        self.annotations.append({
            "type": "rect",
            "x": x,
            "y": y,
            "w": w,
            "h": h
        })
        self.status_var.set(f"Rechteck hinzugefügt ({w}x{h} px)")

    def _add_arrow_annotation(self, x, y):
        # simple fixed offset arrow
        x2, y2 = x + 30, y + 30
        self.annotations.append({
            "type": "arrow",
            "x1": x,
            "y1": y,
            "x2": x2,
            "y2": y2
        })
        self.status_var.set(f"Pfeil hinzugefügt von ({x},{y}) nach ({x2},{y2})")

    # ------------------- Rendering -------------------
    def _render_canvas(self):
        self.canvas.delete("all")

        # Draw quadrant borders (dashed) and labels
        for idx, (x0, y0, w, h) in enumerate(QUADRANTS):
            self.canvas.create_rectangle(x0, y0, x0 + w, y0 + h,
                                         outline="#888888", dash=(4, 2))
            self.canvas.create_text(x0 + 5, y0 + 12,
                                    anchor="nw", text=f"Quadrant {idx + 1}",
                                    fill="#555555", font=("Segoe UI", 9, "bold"))

            # Draw image if present - centered in quadrant
            slot_data = self.slots[idx]
            if slot_data is not None and slot_data["photo"] is not None:
                # Center of quadrant
                slot_cx = x0 + w / 2
                slot_cy = y0 + h / 2
                self.canvas.create_image(slot_cx, slot_cy,
                                         image=slot_data["photo"])

        # Draw annotations
        for ann in self.annotations:
            if ann["type"] == "text":
                self.canvas.create_text(ann["x"], ann["y"],
                                        anchor="nw",
                                        text=ann["text"],
                                        font=("Segoe UI", ann["fontsize"]),
                                        fill="black")
            elif ann["type"] == "circle":
                x0 = ann["x"] - ann["r"]
                y0 = ann["y"] - ann["r"]
                x1 = ann["x"] + ann["r"]
                y1 = ann["y"] + ann["r"]
                self.canvas.create_oval(x0, y0, x1, y1, outline="black", width=2)
            elif ann["type"] == "rect":
                self.canvas.create_rectangle(ann["x"], ann["y"],
                                             ann["x"] + ann["w"], ann["y"] + ann["h"],
                                             outline="black", width=2)
            elif ann["type"] == "arrow":
                self.canvas.create_line(ann["x1"], ann["y1"], ann["x2"], ann["y2"],
                                        arrow=tk.LAST, fill="black", width=2)

        # Page info
        self.canvas.create_text(CANVAS_W_PX / 2, 15,
                                text=f"DIN A4 Querformat (Scale: {CANVAS_SCALE:.3f})",
                                fill="gray", font=("Segoe UI", 9))

    # ------------------- Slot management -------------------
    def _reset_slots(self):
        self.slots: list[dict | None] = [None] * MAX_IMAGES
        self.next_slot = 0
        self.annotations.clear()
        self.current_tool = None
        self.status_var.set("Alle Quadranten zurückgesetzt, Werkzeuge deaktiviert")
        self._render_canvas()

    # ------------------- Project save/load -------------------
    def _save_project(self):
        if all(s is None for s in self.slots) and not self.annotations:
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
            "slots": [],
            "annotations": self.annotations
        }
        for slot in self.slots:
            if slot is None:
                data["slots"].append(None)
            else:
                data["slots"].append({
                    "filepath": slot["filepath"],
                })
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
        if "slots" not in data or not isinstance(data["slots"], list):
            messagebox.showerror("Ungültiges Format", "Erwartete 'slots' Liste.")
            return
        # Reset
        self.slots: list[dict | None] = [None] * MAX_IMAGES
        self.next_slot = 0
        self.annotations = data.get("annotations", [])
        self.current_tool = None
        for idx, slot_data in enumerate(data["slots"]):
            if slot_data is None:
                continue
            if idx >= MAX_IMAGES:
                break
            filepath = slot_data.get("filepath")
            if not filepath or not os.path.exists(filepath):
                continue
            try:
                pil_img = Image.open(filepath)
            except Exception:
                continue
            # Determine quadrant dimensions to create thumbnail for display
            qx0, qy0, qw, qh = QUADRANTS[idx]
            # Scale image to fit quadrant (preserve aspect, do not upscale)
            img_w_px, img_h_px = pil_img.size
            scale_w = qw / img_w_px
            scale_h = qh / img_h_px
            scale = min(scale_w, scale_h, 1.0)
            new_w = max(1, int(img_w_px * scale))
            new_h = max(1, int(img_h_px * scale))
            thumb = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            self.slots[idx] = {
                "filepath": filepath,
                "original": pil_img,
                "thumb": thumb,
                "photo": photo,
                "display_w": new_w,
                "display_h": new_h,
            }
            if idx + 1 > self.next_slot:
                self.next_slot = idx + 1
        self.status_var.set(f"Projekt geladen: {len([s for s in self.slots if s is not None])} Bilder, {len(self.annotations)} Anmerkungen")
        self._render_canvas()

    # ------------------- PDF Export -------------------
    def _save_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Fehlende Bibliothek",
                                 "Das Paket 'reportlab' ist nicht installiert.\nBitte installieren Sie es mit: pip install reportlab")
            return
        if all(s is None for s in self.slots) and not self.annotations:
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
            width, height = landscape(A4)  # in points
            # Precompute conversion factor from canvas pixels to PDF points
            # canvas_px -> page_px: / CANVAS_SCALE
            # page_px -> mm: / MM_TO_PX
            # mm -> points: * (72/25.4)
            factor = (1 / CANVAS_SCALE) / MM_TO_PX * (72 / 25.4)

            def canvas_to_pdf_x(x):
                return x * factor

            def canvas_to_pdf_y(y):
                # PDF y origin bottom-left
                return height - (y * factor)

            for slot_idx, slot in enumerate(self.slots):
                if slot is None:
                    continue
                img_path = slot["filepath"]
                try:
                    pil_img = Image.open(img_path)
                except Exception:
                    continue
                # Downscale for PDF to keep file size small
                img_w_px, img_h_px = pil_img.size
                small_w = max(1, int(img_w_px * PDF_EXPORT_SCALE))
                small_h = max(1, int(img_h_px * PDF_EXPORT_SCALE))
                img_small = pil_img.resize((small_w, small_h), Image.Resampling.LANCZOS)
                # Convert to JPEG bytes with quality
                buf = io.BytesIO()
                img_small.convert('RGB').save(buf, format='JPEG', quality=PDF_JPEG_QUALITY)
                buf.seek(0)
                img_reader = ImageReader(buf)
                # Determine quadrant dimensions in points
                qx0_mm, qy0_mm, qw_mm, qh_mm = self._quadrant_to_mm(slot_idx)
                qw_pt = qw_mm * (72 / 25.4)
                qh_pt = qh_mm * (72 / 25.4)
                # Scale to fit quadrant while preserving aspect ratio (using downscaled image size)
                img_w_pt = small_w * (72 / 25.4)
                img_h_pt = small_h * (72 / 25.4)
                scale = min(qw_pt / img_w_pt, qh_pt / img_h_pt, 1.0)
                img_w_pt *= scale
                img_h_pt *= scale
                # Position: center of quadrant
                qx0_pt = qx0_mm * (72 / 25.4)
                qy0_pt = qy0_mm * (72 / 25.4)
                center_x = qx0_pt + qw_pt / 2
                center_y = qy0_pt + qh_pt / 2
                x1 = center_x - img_w_pt / 2
                y1 = height - (center_y + img_h_pt / 2)  # flip y for PDF
                c.drawImage(img_reader, x1, y1,
                            width=img_w_pt, height=img_h_pt,
                            preserveAspectRatio=True, mask='auto')

            # Draw annotations
            for ann in self.annotations:
                if ann["type"] == "text":
                    x_pt = canvas_to_pdf_x(ann["x"])
                    y_pt = canvas_to_pdf_y(ann["y"])
                    c.setFont("Helvetica", ann["fontsize"])
                    c.drawString(x_pt, y_pt, ann["text"])
                elif ann["type"] == "circle":
                    x_pt = canvas_to_pdf_x(ann["x"])
                    y_pt = canvas_to_pdf_y(ann["y"])
                    r_pt = ann["r"] * factor
                    c.circle(x_pt, y_pt, r_pt)
                elif ann["type"] == "rect":
                    x_pt = canvas_to_pdf_x(ann["x"])
                    y_pt = canvas_to_pdf_y(ann["y"])
                    w_pt = ann["w"] * factor
                    h_pt = ann["h"] * factor
                    # rect draws lower-left corner; we have y_pt as top? Actually canvas_to_pdf_y gave bottom-left conversion for point.
                    # Since we gave y_pt as bottom-left for a point, for rectangle we need to compute bottom-left.
                    # Our ann["y"] is top-left in canvas. Convert top-left to PDF bottom-left: y_bottom = height - (y*factor) - h_pt
                    y_bottom = height - (ann["y"] * factor) - h_pt
                    c.rect(x_pt, y_bottom, w_pt, h_pt)
                elif ann["type"] == "arrow":
                    x1_pt = canvas_to_pdf_x(ann["x1"])
                    y1_pt = canvas_to_pdf_y(ann["y1"])
                    x2_pt = canvas_to_pdf_x(ann["x2"])
                    y2_pt = canvas_to_pdf_y(ann["y2"])
                    c.setLineWidth(1)
                    c.line(x1_pt, y1_pt, x2_pt, y2_pt)
                    # simple arrow head: draw two lines
                    # compute angle
                    import math
                    angle = math.atan2(y2_pt - y1_pt, x2_pt - x1_pt)
                    head_len = 5
                    angle1 = angle + math.pi / 6
                    angle2 = angle - math.pi / 6
                    x3 = x2_pt - head_len * math.cos(angle1)
                    y3 = y2_pt - head_len * math.sin(angle1)
                    x4 = x2_pt - head_len * math.cos(angle2)
                    y4 = y2_pt - head_len * math.sin(angle2)
                    c.line(x2_pt, y2_pt, x3, y3)
                    c.line(x2_pt, y2_pt, x4, y4)

            c.showPage()
            c.save()
            messagebox.showinfo("PDF exportiert",
                                f"PDF gespeichert unter:\n{filepath}\nSeiten: 1")
        except Exception as e:
            messagebox.showerror("Exportfehler",
                                 f"Konnte PDF nicht erzeugen:\n{e}")

    def _quadrant_to_mm(self, idx):
        """Return (x0_mm, y0_mm, width_mm, height_mm) for given quadrant index."""
        x0_px, y0_px, w_px, h_px = QUADRANTS_PX[idx]
        x0_mm = x0_px / MM_TO_PX
        y0_mm = y0_px / MM_TO_PX
        w_mm = w_px / MM_TO_PX
        h_mm = h_px / MM_TO_PX
        return x0_mm, y0_mm, w_mm, h_mm

def main():
    root = dnd2.Tk()
    app = ImageCollageApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()