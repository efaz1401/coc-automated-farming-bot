"""Interactive region selection / template cropping dialog."""
from __future__ import annotations
import os
import tkinter as tk
from tkinter import messagebox, ttk
import cv2
import numpy as np
from PIL import Image, ImageTk

from .theme import COLORS, FONTS


class CropDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        image_bgr: np.ndarray,
        target_name: str,
        target_type: str = "button",  # "button" | "digit" | "loot_box"
        on_saved: callable[[str, dict], None] | None = None,
    ):
        super().__init__(parent)
        self.title(f"Crop & Calibrate — {target_name} ({target_type})")
        self.configure(bg=COLORS["bg_main"])
        self.transient(parent)
        self.grab_set()

        self.img_orig = image_bgr
        self.target_name = target_name
        self.target_type = target_type
        self.on_saved = on_saved

        self.orig_h, self.orig_w = self.img_orig.shape[:2]
        # Display scale: fit 1080x608 or similar
        self.disp_w = min(1080, self.orig_w)
        self.disp_h = int(self.disp_w * (self.orig_h / self.orig_w))
        self.scale_x = self.orig_w / self.disp_w
        self.scale_y = self.orig_h / self.disp_h

        self.start_x = None
        self.start_y = None
        self.cur_rect = None
        self.roi = None  # (orig_x, orig_y, orig_w, orig_h)

        self._build_ui()
        self.geometry(f"{self.disp_w + 300}x{self.disp_h + 80}")
        self.minsize(900, 500)

    def _build_ui(self):
        # Top instructions bar
        top_bar = tk.Frame(self, bg=COLORS["bg_header"], height=40)
        top_bar.pack(side=tk.TOP, fill=tk.X)
        
        info_text = f"Target: {self.target_name}  |  Click and drag on the screen to select the rectangle"
        lbl_info = tk.Label(top_bar, text=info_text, bg=COLORS["bg_header"], fg=COLORS["accent_gold"], font=FONTS["heading"])
        lbl_info.pack(side=tk.LEFT, padx=15, pady=8)

        # Main horizontal split: Canvas (left) + Preview/Controls (right)
        body = tk.Frame(self, bg=COLORS["bg_main"])
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Canvas
        canvas_frame = tk.Frame(body, bg=COLORS["bg_card"], bd=1, relief="solid")
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_frame,
            width=self.disp_w,
            height=self.disp_h,
            bg="#000000",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(anchor=tk.CENTER)

        # Convert image to RGB PIL PhotoImage
        disp_bgr = cv2.resize(self.img_orig, (self.disp_w, self.disp_h))
        disp_rgb = cv2.cvtColor(disp_bgr, cv2.COLOR_BGR2RGB)
        self.pil_img = ImageTk.PhotoImage(Image.fromarray(disp_rgb))
        self.canvas.create_image(0, 0, image=self.pil_img, anchor=tk.NW)

        # Canvas mouse events
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Right Panel
        right_panel = tk.Frame(body, bg=COLORS["bg_card"], width=280)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_panel.pack_propagate(False)

        lbl_side = tk.Label(right_panel, text="Selection Preview", bg=COLORS["bg_card"], fg=COLORS["accent_blue"], font=FONTS["subtitle"])
        lbl_side.pack(anchor=tk.W, padx=15, pady=(15, 10))

        # Preview box
        self.preview_canvas = tk.Canvas(right_panel, width=240, height=140, bg="#11111b", highlightthickness=1, highlightbackground=COLORS["border"])
        self.preview_canvas.pack(padx=15, pady=5)
        self.preview_tk = None

        # Info Labels
        self.lbl_dims = tk.Label(right_panel, text="Size: -- x -- px", bg=COLORS["bg_card"], fg=COLORS["text_secondary"], font=FONTS["body"])
        self.lbl_dims.pack(anchor=tk.W, padx=15, pady=(10, 2))

        self.lbl_frac = tk.Label(right_panel, text="Fractional: [0.0, 0.0, 0.0, 0.0]", bg=COLORS["bg_card"], fg=COLORS["text_muted"], font=FONTS["small"])
        self.lbl_frac.pack(anchor=tk.W, padx=15, pady=2)

        # Separator
        sep = tk.Frame(right_panel, bg=COLORS["border"], height=1)
        sep.pack(fill=tk.X, padx=15, pady=15)

        # Save Button
        self.btn_save = ttk.Button(right_panel, text="💾 Save Template", style="Primary.TButton", command=self._on_save)
        self.btn_save.pack(fill=tk.X, padx=15, pady=5)

        btn_cancel = ttk.Button(right_panel, text="Cancel", command=self.destroy)
        btn_cancel.pack(fill=tk.X, padx=15, pady=5)

    def _on_mouse_down(self, event):
        self.start_x = max(0, min(event.x, self.disp_w))
        self.start_y = max(0, min(event.y, self.disp_h))
        if self.cur_rect:
            self.canvas.delete(self.cur_rect)
        self.cur_rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#00ffcc", width=2, dash=(4, 2)
        )

    def _on_mouse_drag(self, event):
        if self.start_x is None:
            return
        cur_x = max(0, min(event.x, self.disp_w))
        cur_y = max(0, min(event.y, self.disp_h))
        self.canvas.coords(self.cur_rect, self.start_x, self.start_y, cur_x, cur_y)

    def _on_mouse_up(self, event):
        if self.start_x is None:
            return
        end_x = max(0, min(event.x, self.disp_w))
        end_y = max(0, min(event.y, self.disp_h))

        x1, x2 = sorted([self.start_x, end_x])
        y1, y2 = sorted([self.start_y, end_y])
        dw = x2 - x1
        dh = y2 - y1

        if dw < 4 or dh < 4:
            return

        orig_x = int(x1 * self.scale_x)
        orig_y = int(y1 * self.scale_y)
        orig_w = int(dw * self.scale_x)
        orig_h = int(dh * self.scale_y)
        orig_w = min(orig_w, self.orig_w - orig_x)
        orig_h = min(orig_h, self.orig_h - orig_y)

        self.roi = (orig_x, orig_y, orig_w, orig_h)
        self.lbl_dims.config(text=f"Size: {orig_w} x {orig_h} px")

        fx = orig_x / self.orig_w
        fy = orig_y / self.orig_h
        fw = orig_w / self.orig_w
        fh = orig_h / self.orig_h
        self.lbl_frac.config(text=f"Frac: [{fx:.3f}, {fy:.3f}, {fw:.3f}, {fh:.3f}]")

        # Update preview canvas
        crop_bgr = self.img_orig[orig_y:orig_y + orig_h, orig_x:orig_x + orig_w]
        if crop_bgr.size > 0:
            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            pil_crop = Image.fromarray(crop_rgb)
            # Scale preview to fit 240x140 keeping aspect ratio
            pil_crop.thumbnail((230, 130))
            self.preview_tk = ImageTk.PhotoImage(pil_crop)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(120, 70, image=self.preview_tk, anchor=tk.CENTER)

    def _on_save(self):
        if not self.roi or self.roi[2] < 3 or self.roi[3] < 3:
            messagebox.showwarning("No Selection", "Please drag a rectangle around the target first.", parent=self)
            return

        ox, oy, ow, oh = self.roi
        crop_bgr = self.img_orig[oy:oy + oh, ox:ox + ow]

        saved_info = {
            "roi": self.roi,
            "frac": [ox / self.orig_w, oy / self.orig_h, ow / self.orig_w, oh / self.orig_h],
        }

        if self.target_type == "button":
            path = os.path.join("assets", f"{self.target_name}.png")
            os.makedirs("assets", exist_ok=True)
            cv2.imwrite(path, crop_bgr)
            saved_info["path"] = path
            messagebox.showinfo("Saved", f"Saved template '{self.target_name}' to {path}", parent=self)

        elif self.target_type == "digit":
            os.makedirs(os.path.join("assets", "digits"), exist_ok=True)
            path = os.path.join("assets", "digits", f"{self.target_name}.png")
            cv2.imwrite(path, crop_bgr)
            saved_info["path"] = path
            messagebox.showinfo("Saved", f"Saved digit '{self.target_name}' to {path}", parent=self)

        elif self.target_type == "loot_box":
            saved_info["box"] = [
                round(ox / self.orig_w, 3),
                round(oy / self.orig_h, 3),
                round(ow / self.orig_w, 3),
                round(oh / self.orig_h, 3),
            ]
            messagebox.showinfo(
                "Calibrated",
                f"Calibrated {self.target_name} box to {saved_info['box']}",
                parent=self,
            )

        if self.on_saved:
            self.on_saved(self.target_name, saved_info)

        self.destroy()
