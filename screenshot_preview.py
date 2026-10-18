"""Persistent screenshot viewer for the selected weekday; all processing is local."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageOps, ImageTk


class ScreenshotPreview(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=(16, 0, 0, 0))
        self.image_path = None
        self.picture = None
        self.photo = None
        self.scale = 1.0
        self.fit_mode = True
        self.render_job = None
        self.empty_message = "尚未上传图片\n在左侧为这一天选择截图，即可在这里预览。"
        self.title = tk.StringVar(value="周一 · 截图预览")
        self.filename = tk.StringVar(value="尚未上传")
        self.details = tk.StringVar(value="点击左侧星期，可切换当天截图")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        ttk.Label(self, textvariable=self.title, font=("Microsoft YaHei UI", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.file_label = ttk.Label(self, textvariable=self.filename, style="Small.TLabel", wraplength=320)
        self.file_label.grid(row=1, column=0, sticky="ew", pady=(4, 10))
        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        for text, command, width in (("适应窗口", self.fit, 7), ("缩小", lambda: self.zoom(0.8), 4), ("放大", lambda: self.zoom(1.25), 4)):
            ttk.Button(actions, text=text, width=width, command=command).pack(side="left", padx=(0, 5))
        viewer = ttk.Frame(self)
        viewer.grid(row=3, column=0, sticky="nsew")
        viewer.columnconfigure(0, weight=1)
        viewer.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(viewer, bg="#e7ebef", highlightthickness=0, width=340, height=360)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(viewer, orient="vertical", command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(viewer, orient="horizontal", command=self.canvas.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.canvas.bind("<Configure>", self.schedule_render)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.bind("<Destroy>", self.destroyed, add=True)
        self.bind("<Configure>", lambda event: self.file_label.configure(wraplength=max(180, event.width - 24)))
        ttk.Label(self, textvariable=self.details, style="Small.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 4))

    def show(self, day, path):
        self.title.set(f"{day} · 截图预览")
        self.image_path = Path(path) if path else None
        self.picture = None
        self.photo = None
        self.fit_mode = True
        self.canvas.delete("all")
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.empty_message = f"{day}尚未上传图片\n请在左侧选择当天截图。"
        if self.image_path:
            self.filename.set(self.image_path.name)
            try:
                with Image.open(self.image_path) as source:
                    self.picture = ImageOps.exif_transpose(source).convert("RGB")
            except (OSError, ValueError, Image.DecompressionBombError):
                self.empty_message = "图片无法读取\n文件可能已移动，请重新选择这一天的截图。"
        else:
            self.filename.set("尚未上传")
        self.details.set("点击左侧星期，可切换当天截图")
        self.schedule_render()

    def schedule_render(self, event=None):
        if self.render_job is not None:
            self.after_cancel(self.render_job)
        self.render_job = self.after(40, self.render)

    def render(self):
        if self.render_job is not None:
            self.after_cancel(self.render_job)
            self.render_job = None
        width, height = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        previous = self.canvas.bbox("screenshot")
        center_x = center_y = 0.5
        if previous:
            x0, y0, x1, y1 = previous
            center_x = (self.canvas.canvasx(width / 2) - x0) / max(1, x1 - x0)
            center_y = (self.canvas.canvasy(height / 2) - y0) / max(1, y1 - y0)
        self.canvas.delete("all")
        if self.picture is None:
            self.canvas.configure(scrollregion=(0, 0, width, height))
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
            self.canvas.create_text(width / 2, height / 2, text=self.empty_message,
                fill="#4d5966", font=("Microsoft YaHei UI", 10), justify="center", width=max(80, width - 40), tags="empty")
            return
        source_w, source_h = self.picture.size
        if self.fit_mode:
            self.scale = min(max(1, width - 24) / source_w, max(1, height - 24) / source_h)
        self.scale = min(4.0, max(0.02, self.scale))
        image_w, image_h = max(1, round(source_w * self.scale)), max(1, round(source_h * self.scale))
        # Preserve original pixels for OCR/export; resizing is for display only.
        resized = self.picture.resize((image_w, image_h), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(resized, master=self)
        region_w, region_h = max(width, image_w + 24), max(height, image_h + 24)
        left, top = (region_w - image_w) / 2, (region_h - image_h) / 2
        self.canvas.create_image(left, top, anchor="nw", image=self.photo, tags="screenshot")
        self.canvas.configure(scrollregion=(0, 0, region_w, region_h))
        if self.fit_mode:
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
        else:
            self.canvas.xview_moveto((left + center_x * image_w - width / 2) / region_w)
            self.canvas.yview_moveto((top + center_y * image_h - height / 2) / region_h)
        self.details.set(f"{source_w} × {source_h} 像素　·　缩放 {self.scale:.0%}")

    def fit(self):
        self.fit_mode = True
        self.schedule_render()

    def zoom(self, factor):
        if self.picture is not None:
            self.fit_mode = False
            self.scale *= factor
            self.schedule_render()

    def wheel(self, event):
        if event.delta:
            if event.state & 0x4:
                self.zoom(1.25 if event.delta > 0 else 0.8)
            else:
                self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def destroyed(self, event):
        if event.widget is self and self.render_job is not None:
            self.after_cancel(self.render_job)
            self.render_job = None
