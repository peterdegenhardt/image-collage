#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Collage - layout according to spec:
Left column: stacked A6 (top) and A5 (bottom).
Right column: two images with same heights as the left column images,
               filling the remaining width to reach A4 width.
All images are scaled to fit within their slots while preserving aspect ratio.
Fixed window size, drag & drop to add images, project save/load, PDF export.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinterdnd2 as dnd2
from PIL import Image, ImageTk, ImageDraw
import os
import json

# Try to import reportlab for PDF export
try:
    from reportlab.pdfgen import canvas as reportlab_canvas
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

# ----------------------- Constants (mm) -----------------------
MM_TO_INCH = 1 / 25.4
INCH_TO_POINT = 72  # 1 inch = 72 pt
DPI = 300  # for pixel conversion

# Slot sizes in mm (as per spec)
A6_W_MM, A6_H_MM = 105, 148   # A6
A5_W_MM, A5_H_MM = 148, 210   # A5
A4_W_MM, A4_H_MM = 210, 297   # A4 portrait

# Convert mm to pixels at 300 DPI
MM_TO_PX = DPI * MM_TO_INCH  # pixels per mm

A6_W_PX = int(A6_W_MM * MM_TO_PX)
A6_H_PX = int(A6_H_MM * MM_TO_PX)
A5_W_PX = int(A5_W_MM * MM_TO_PX)
A5_H_PX = int(A5_H_MM * MM_TO_PX)
A4_W_PX = int(A4_W_MM * MM_TO_PX)
A4_H_PX = int(A4_H_MM * MM_TO_PX)

# Compute scale to fit the stacked left column within the A4 page
max_left_width_px = max(A6_W_PX, A5_W_PX)
total_left_height_px = A6_H_PX + A5_H_PX
scale_w = A4_W_PX / max_left_width_px
scale_h = A4_H_PX / total_left_height_px
SCALE = min(scale_w, scale_h)  # uniform scaling factor for the whole layout

# Scaled dimensions in px (still in page/pixel units before canvas scaling)
A6_W_S = int(A6_W_PX * SCALE)
A6_H_S = int(A6_H_PX * SCALE)
A5_W_S = int(A5_W_PX * SCALE)
A5_H_S = int(A5_H_PX * SCALE)

# Column widths in px (page units)
LEFT_COL_W_PX = max(A6_W_S, A5_W_S)   # width of left column (widest image)
RIGHT_COL_W_PX = A4_W_PX - LEFT_COL_W_PX  # remaining width for right column

# Fixed window size for the GUI (canvas)
CANVAS_W_PX = 900
CANVAS_H_PX = 600

# Scale to fit the whole A4 page into the canvas
PAGE_W_PX = A4_W_PX
PAGE_H_PX = A4_H_PX
CANVAS_SCALE = min(CANVAS_W_PX / PAGE_W_PX, CANVAS_H_PX / PAGE_H_PX)

# Points conversion for PDF
MM_TO_PT = INCH_TO_POINT * MM_TO_INCH

MAX_IMAGES = 4


class ImageCollageApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Collage – A6/A5 left column, matching heights right column")
        self.root.geometry(f"{CANVAS_W_PX + 200}x{CANVAS_H_PX + 50}")
        self.root.minsize(CANVAS_W_PX + 200, CANVAS_H_PX + 50)

        # State: one dict per slot, or None
        self.slots: list[dict | None] = [None] * MAX_IMAGES  # 0:top-left,1:bottom-left,2:top-right,3:bottom-right
        self.next_slot = 0

        # For optional dragging within a slot
        self.dragging_slot = None
        self.drag_start_x = 0
        self.drag_start_y = 0

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

        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Bereit – Bilder per Drag & Drop auf die Slots ziehen")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_events(self):
        self.canvas.drop_target_register(dnd2.DND_FILES)
        self.canvas.dnd_bind('<<Drop>>', self._on_drop)
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

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
            messagebox.showinfo("Info", "Alle vier Slots sind belegt. Bitte resetten oder ein Bild ersetzen.")
            return
        try:
            pil_img = Image.open(filepath)
        except Exception as e:
            messagebox.showerror("Fehler beim Laden",
                                 f"Konnte Bild nicht laden:\n{filepath}\n{e}")
            return

        slot_idx = self.next_slot
        # Determine slot dimensions in page units (before canvas scaling)
        if slot_idx == 0:
            slot_w_px, slot_h_px = A6_W_S, A6_H_S
        elif slot_idx == 1:
            slot_w_px, slot_h_px = A5_W_S, A5_H_S
        elif slot_idx == 2:
            slot_w_px, slot_h_px = RIGHT_COL_W_PX, A6_H_S
        else:  # idx == 3
            slot_w_px, slot_h_px = RIGHT_COL_W_PX, A5_H_S

        # Scale image to fit slot (preserve aspect, do not upscale)
        img_w_px, img_h_px = pil_img.size
        scale = min(slot_w_px / img_w_px, slot_h_px / img_h_px, 1.0)
        new_w = int(img_w_px * scale)
        new_h = int(img_h_px * scale)
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
            # offset within slot for dragging (in canvas pixels)
            "offset_x": 0,
            "offset_y": 0,
        }
        self.next_slot += 1
        self.status_var.set(f"Bild {slot_idx + 1} platziert (Slot {slot_idx + 1})")
        self._render_canvas()

    # ------------------- Canvas interaction (optional moving) -------------------
    def _on_canvas_click(self, event):
        slot_idx = self._get_slot_at_pos(event.x, event.y)
        if slot_idx is not None and self.slots[slot_idx] is not None:
            self.dragging_slot = slot_idx
            self.drag_start_x = event.x
            self.drag_start_y = event.y
            self.status_var.set(f"Ziehe Bild {slot_idx + 1}")

    def _on_canvas_drag(self, event):
        if self.dragging_slot is None:
            return
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        slot = self.slots[self.dragging_slot]
        slot["offset_x"] += dx
        slot["offset_y"] += dy
        self._render_canvas()

    def _on_canvas_release(self, event):
        if self.dragging_slot is not None:
            self.status_var.set(f"Bild {self.dragging_slot + 1} platziert")
            self.dragging_slot = None

    def _get_slot_at_pos(self, cx, cy):
        """Return slot index (0-3) if canvas point (cx,cy) lies inside that slot's bounding box."""
        # Convert canvas point to page coordinates (unscaled)
        px = cx / CANVAS_SCALE
        py = cy / CANVAS_SCALE
        # Compute slot origins in page coordinates (px) based on our layout
        # Left column x0 = 0
        # Top-left y0 = 0
        # Bottom-left y0 = A6_H_S
        # Right column x0 = LEFT_COL_W_PX
        # Top-right y0 = 0
        # Bottom-right y0 = A6_H_S
        left_x0 = 0
        left_y0_top = 0
        left_y0_bottom = A6_H_S
        right_x0 = LEFT_COL_W_PX
        right_y0_top = 0
        right_y0_bottom = A6_H_S

        # Define slots as (x0, y0, w, h)
        slots = [
            (left_x0, left_y0_top, A6_W_S, A6_H_S),          # slot 0
            (left_x0, left_y0_bottom, A5_W_S, A5_H_S),      # slot 1
            (right_x0, right_y0_top, RIGHT_COL_W_PX, A6_H_S),# slot 2
            (right_x0, right_y0_bottom, RIGHT_COL_W_PX, A5_H_S), # slot 3
        ]
        for idx, (x0, y0, w, h) in enumerate(slots):
            if x0 <= px <= x0 + w and y0 <= py <= y0 + h:
                return idx
        return None

    # ------------------- Rendering -------------------
    def _render_canvas(self):
        self.canvas.delete("all")

        # Draw page background (optional)
        # self.canvas.create_rectangle(0, 0, PAGE_W_PX * CANVAS_SCALE, PAGE_H_PX * CANVAS_SCALE,
        #                            outline="#dddddd", width=1)

        # Compute origins for each slot in canvas coordinates
        origins = [
            (0, 0),                                            # slot0
            (0, A6_H_S * CANVAS_SCALE),                       # slot1
            (LEFT_COL_W_PX * CANVAS_SCALE, 0),                # slot2
            (LEFT_COL_W_PX * CANVAS_SCALE, A6_H_S * CANVAS_SCALE), # slot3
        ]
        slot_sizes = [
            (A6_W_S * CANVAS_SCALE, A6_H_S * CANVAS_SCALE),   # slot0
            (A5_W_S * CANVAS_SCALE, A5_H_S * CANVAS_SCALE),   # slot1
            (RIGHT_COL_W_PX * CANVAS_SCALE, A6_H_S * CANVAS_SCALE), # slot2
            (RIGHT_COL_W_PX * CANVAS_SCALE, A5_H_S * CANVAS_SCALE), # slot3
        ]

        # Draw slot borders (dashed) and labels
        for idx, ((ox, oy), (w, h)) in enumerate(zip(origins, slot_sizes)):
            self.canvas.create_rectangle(ox, oy, ox + w, oy + h,
                                         outline="#888888", dash=(4, 2))
            self.canvas.create_text(ox + 5, oy + 12,
                                    anchor="nw", text=f"Slot {idx + 1}",
                                    fill="#555555", font=("Segoe UI", 9, "bold"))

            # Draw image if present
            slot_data = self.slots[idx]
            if slot_data is not None and slot_data["photo"] is not None:
                # Base center of slot
                slot_cx = ox + w / 2
                slot_cy = oy + h / 2
                # Apply offset
                off_x = slot_data.get("offset_x", 0)
                off_y = slot_data.get("offset_y", 0)
                img_cx = slot_cx + off_x
                img_cy = slot_cy + off_y
                # Clamp to stay within slot (simple)
                half_w = slot_data["display_w"] * CANVAS_SCALE / 2
                half_h = slot_data["display_h"] * CANVAS_SCALE / 2
                min_x = ox + half_w
                max_x = ox + w - half_w
                min_y = oy + half_h
                max_y = oy + h - half_h
                img_cx = max(min_x, min(max_x, img_cx))
                img_cy = max(min_y, min(max_y, img_cy))
                self.canvas.create_image(img_cx, img_cy,
                                         image=slot_data["photo"])

        # Page info
        self.canvas.create_text(CANVAS_W_PX / 2, 15,
                                text=f"DIN A4 Querformat (Scale: {CANVAS_SCALE:.3f})",
                                fill="gray", font=("Segoe UI", 9))

    # ------------------- Slot management -------------------
    def _reset_slots(self):
        self.slots: list[dict | None] = [None] * MAX_IMAGES
        self.next_slot = 0
        self.status_var.set("Alle Slots zurückgesetzt")
        self._render_canvas()

    # ------------------- Project save/load -------------------
    def _save_project(self):
        if all(s is None for s in self.slots):
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
            "slots": []
        }
        for slot in self.slots:
            if slot is None:
                data["slots"].append(None)
            else:
                data["slots"].append({
                    "filepath": slot["filepath"],
                    "offset_x": slot.get("offset_x", 0),
                    "offset_y": slot.get("offset_y", 0),
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
            # Determine slot dimensions to create thumbnail for display
            if idx == 0:
                slot_w_px, slot_h_px = A6_W_S, A6_H_S
            elif idx == 1:
                slot_w_px, slot_h_px = A5_W_S, A5_H_S
            elif idx == 2:
                slot_w_px, slot_h_px = RIGHT_COL_W_PX, A6_H_S
            else:  # idx == 3
                slot_w_px, slot_h_px = RIGHT_COL_W_PX, A5_H_S
            # Scale image to fit slot (preserve aspect, do not upscale)
            img_w_px, img_h_px = pil_img.size
            scale = min(slot_w_px / img_w_px, slot_h_px / img_h_px, 1.0)
            new_w = int(img_w_px * scale)
            new_h = int(img_h_px * scale)
            thumb = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            self.slots[idx] = {
                "filepath": filepath,
                "original": pil_img,
                "thumb": thumb,
                "photo": photo,
                "display_w": new_w,
                "display_h": new_h,
                "offset_x": slot_data.get("offset_x", 0),
                "offset_y": slot_data.get("offset_y", 0),
            }
            if idx + 1 > self.next_slot:
                self.next_slot = idx + 1
        self.status_var.set(f"Projekt geladen: {len([s for s in self.slots if s is not None])} Bilder")
        self._render_canvas()

    # ------------------- PDF Export -------------------
    def _save_pdf(self):
        if not REPORTLAB_AVAILABLE:
            messagebox.showerror("Fehlende Bibliothek",
                                 "Das Paket 'reportlab' ist nicht installiert.\nBitte installieren Sie es mit: pip install reportlab")
            return
        if all(s is None for s in self.slots):
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
            for slot_idx, slot in enumerate(self.slots):
                if slot is None:
                    continue
                img_path = slot["filepath"]
                try:
                    pil_img = Image.open(img_path)
                except Exception:
                    continue
                # Original size in pixels
                img_w_px, img_h_px = pil_img.size
                # Convert to points at 300 DPI
                img_w_pt = img_w_px * MM_TO_PT
                img_h_pt = img_h_px * MM_TO_PT
                # Determine slot dimensions in points (based on our layout)
                if slot_idx == 0:
                    slot_w_pt = A6_W_MM * MM_TO_PT
                    slot_h_pt = A6_H_MM * MM_TO_PT
                elif slot_idx == 1:
                    slot_w_pt = A5_W_MM * MM_TO_PT
                    slot_h_pt = A5_H_MM * MM_TO_PT
                elif slot_idx == 2:
                    slot_w_pt = (A4_W_MM - max(A6_W_MM, A5_W_MM)) * MM_TO_PT  # remaining width
                    slot_h_pt = A6_H_MM * MM_TO_PT
                else:  # slot_idx == 3
                    slot_w_pt = (A4_W_MM - max(A6_W_MM, A5_W_MM)) * MM_TO_PT
                    slot_h_pt = A5_H_MM * MM_TO_PT
                # Scale to fit slot while preserving aspect ratio
                scale = min(slot_w_pt / img_w_pt, slot_h_pt / img_h_pt, 1.0)
                img_w_pt *= scale
                img_h_pt *= scale
                # Position: slot origin in points (top-left of slot)
                # Compute slot origins in points (same logic as in pixel but using PT sizes)
                # We'll compute origins in mm then convert to pt
                origins_mm = []
                # left column x0 = 0
                # top-left y0 = 0
                # bottom-left y0 = A6_H_MM
                # right column x0 = max(A6_W_MM, A5_W_MM)
                # top-right y0 = 0
                # bottom-right y0 = A6_H_MM
                left_x0_mm = 0
                left_y0_top_mm = 0
                left_y0_bottom_mm = A6_H_MM
                right_x0_mm = max(A6_W_MM, A5_W_MM)
                right_y0_top_mm = 0
                right_y0_bottom_mm = A6_H_MM
                if slot_idx == 0:
                    ox_mm, oy_mm = left_x0_mm, left_y0_top_mm
                elif slot_idx == 1:
                    ox_mm, oy_mm = left_x0_mm, left_y0_bottom_mm
                elif slot_idx == 2:
                    ox_mm, oy_mm = right_x0_mm, right_y0_top_mm
                else:
                    ox_mm, oy_mm = right_x0_mm, right_y0_bottom_mm
                ox_pt = ox_mm * MM_TO_PT
                oy_pt = oy_mm * MM_TO_PT
                # In PDF, origin is bottom-left; we need to convert y from top
                # So y1 = height - (oy_pt + img_h_pt/2) for center alignment
                # We'll place image centered at (ox_pt + slot_w_pt/2, oy_pt + slot_h_pt/2)
                center_x = ox_pt + slot_w_pt / 2
                center_y = oy_pt + slot_h_pt / 2
                x1 = center_x - img_w_pt / 2
                y1 = height - (center_y + img_h_pt / 2)  # flip y
                c.drawImage(ImageReader(pil_img), x1, y1,
                            width=img_w_pt, height=img_h_pt,
                            preserveAspectRatio=True, mask='auto')
            c.showPage()
            c.save()
            messagebox.showinfo("PDF exportiert",
                                f"PDF gespeichert unter:\n{filepath}\nSeiten: 1")
        except Exception as e:
            messagebox.showerror("Exportfehler",
                                 f"Konnte PDF nicht erzeugen:\n{e}")

def main():
    root = dnd2.Tk()
    app = ImageCollageApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()