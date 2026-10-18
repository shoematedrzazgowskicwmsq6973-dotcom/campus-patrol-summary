"""A small Windows desktop tool; screenshots are processed only on this PC."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import queue
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk
from patrol_core import BASE, DAYS, TEMPLATE, WORD_IMAGE_FORMATS, DayRecord, LocalOCR, build_docx, find_duplicate_departments, parse_fields, report_filename
from screenshot_preview import ScreenshotPreview


class PatrolApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("公共区域巡查汇总")
        root.geometry(f"{min(1280, root.winfo_screenwidth() - 60)}x{min(800, root.winfo_screenheight() - 100)}")
        root.minsize(980, 600)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.engine = None
        self.busy = False
        self.rows = []
        self.controls = []
        self.entries = []
        self.checks = []
        self.last_output = None
        self.selected_day = tk.IntVar(value=0)
        self.preview_day = None
        self.day_selectors = []
        style = ttk.Style(root)
        style.theme_use("vista" if "vista" in style.theme_names() else "clam")
        style.configure("TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("TButton", font=("Microsoft YaHei UI", 10), padding=(8, 5))
        style.configure("Heading.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Small.TLabel", font=("Microsoft YaHei UI", 9), foreground="#555555")
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 9))
        style.configure("Day.Toolbutton", font=("Microsoft YaHei UI", 10, "bold"), padding=(8, 5))
        body = ttk.Frame(root, padding=20)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(5, weight=1)
        ttk.Label(body, text="公共区域巡查汇总", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="① 选好每天的截图　② 识别部门和姓名　③ 对照截图勾选已核对　④ 导出 Word",
                  padding=(0, 10, 0, 6)).grid(row=1, column=0, sticky="w")
        ttk.Label(body, text="点击左侧星期切换预览；选图后立即显示。图片仅在本机处理。",
                  style="Small.TLabel").grid(row=2, column=0, sticky="w")
        options = ttk.Frame(body, padding=(0, 16, 0, 12))
        options.grid(row=3, column=0, sticky="ew")
        options.columnconfigure(0, weight=1)
        metadata = ttk.Frame(options)
        metadata.grid(row=0, column=0, sticky="w")
        self.start_year = tk.StringVar(value="2026")
        self.end_year = tk.StringVar(value="2027")
        self.semester = tk.StringVar(value="第一学期")
        ttk.Label(metadata, text="学年").pack(side="left")
        self.start_year_entry = ttk.Entry(metadata, textvariable=self.start_year, width=6)
        self.start_year_entry.pack(side="left", padx=(8, 6))
        ttk.Label(metadata, text="至").pack(side="left")
        self.end_year_entry = ttk.Entry(metadata, textvariable=self.end_year, width=6)
        self.end_year_entry.pack(side="left", padx=(6, 16))
        self.entries.extend((self.start_year_entry, self.end_year_entry))
        ttk.Label(metadata, text="学期").pack(side="left")
        self.semester_box = ttk.Combobox(metadata, textvariable=self.semester, state="readonly",
                                       values=("第一学期", "第二学期"), width=10)
        self.semester_box.pack(side="left", padx=(8, 16))
        self.controls.append(self.semester_box)
        ttk.Label(metadata, text="周次").pack(side="left")
        self.week = tk.StringVar()
        self.week_entry = ttk.Entry(metadata, textvariable=self.week, width=5)
        self.week_entry.pack(side="left", padx=(8, 10))
        self.entries.append(self.week_entry)
        ttk.Label(metadata, text="如 7", style="Small.TLabel").pack(side="left")
        actions = ttk.Frame(options)
        actions.grid(row=0, column=1, sticky="e", padx=(16, 0))
        self.export_button = ttk.Button(actions, text="导出 Word…", command=self.export)
        self.export_button.pack(side="right")
        self.controls.append(self.export_button)
        self.recognize_button = ttk.Button(actions, text="识别未核对的截图", command=self.start_ocr)
        self.recognize_button.pack(side="right", padx=(0, 8))
        self.controls.append(self.recognize_button)
        self.toolbar_stacked = False

        def fit_toolbar(event):
            stacked = event.width < metadata.winfo_reqwidth() + actions.winfo_reqwidth() + 16
            if stacked != self.toolbar_stacked:
                self.toolbar_stacked = stacked
                actions.grid_configure(row=1 if stacked else 0, column=0 if stacked else 1,
                    padx=(0, 0) if stacked else (16, 0), pady=(8, 0) if stacked else (0, 0))

        options.bind("<Configure>", fit_toolbar)
        self.duplicate_notice = tk.StringVar()
        self.duplicate_label = ttk.Label(body, textvariable=self.duplicate_notice,
            foreground="#8a3d13", wraplength=900, padding=(0, 0, 0, 10))
        self.duplicate_label.grid(row=4, column=0, sticky="ew")
        self.duplicate_label.grid_remove()
        body.bind("<Configure>", lambda event: self.duplicate_label.configure(wraplength=max(200, event.width - 40)))
        self.panes = ttk.Panedwindow(body, orient="horizontal")
        self.panes.grid(row=5, column=0, sticky="nsew")
        list_area = ttk.Frame(self.panes)
        self.panes.add(list_area, weight=3)
        self.screenshot_preview = ScreenshotPreview(self.panes)
        self.panes.add(self.screenshot_preview, weight=2)
        self.raw_button = ttk.Button(self.screenshot_preview, text="原文更正", width=7,
                                    command=lambda: self.preview(self.selected_day.get()))
        self.raw_button.grid(row=0, column=0, sticky="e")
        self.controls.append(self.raw_button)
        list_area.rowconfigure(0, weight=1)
        list_area.columnconfigure(0, weight=1)
        self.table_viewport = tk.Canvas(list_area, highlightthickness=0,
                                       width=620, height=400,
                                       background=style.lookup("TFrame", "background"))
        self.table_viewport.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(list_area, orient="vertical", command=self.table_viewport.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(list_area, orient="horizontal", command=self.table_viewport.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.table_viewport.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        table = ttk.Frame(self.table_viewport)
        table_window = self.table_viewport.create_window((0, 0), window=table, anchor="nw")

        def fit_table(event=None):
            self.table_viewport.itemconfigure(table_window,
                width=max(table.winfo_reqwidth(), self.table_viewport.winfo_width()),
                height=max(table.winfo_reqheight(), self.table_viewport.winfo_height()))
            self.table_viewport.configure(scrollregion=self.table_viewport.bbox("all"))

        table.bind("<Configure>", lambda event: self.table_viewport.configure(scrollregion=self.table_viewport.bbox("all")))
        self.table_viewport.bind("<Configure>", fit_table)
        table.columnconfigure(1, weight=1)
        for column, title in enumerate(("日期 / 截图", "部门与姓名", "状态", "已核对")):
            ttk.Label(table, text=title, padding=(4, 6)).grid(row=0, column=column, sticky="w")
        for index, day in enumerate(DAYS):
            rownum = index + 1
            table.rowconfigure(rownum, weight=1, minsize=91)
            imagebox = ttk.Frame(table)
            imagebox.grid(row=rownum, column=0, padx=(0, 12), sticky="ew")
            buttons = ttk.Frame(imagebox)
            buttons.pack(anchor="w")
            day_button = ttk.Radiobutton(buttons, text=day, variable=self.selected_day,
                value=index, style="Day.Toolbutton", command=lambda i=index: self.select_day(i))
            day_button.pack(side="left", padx=(0, 5))
            self.day_selectors.append(day_button)
            choose = ttk.Button(buttons, text="选图片", command=lambda i=index: self.choose_image(i), width=7)
            choose.pack(side="left")
            self.controls.append(choose)
            filename = tk.StringVar(value="未选择")
            filename_label = ttk.Label(imagebox, textvariable=filename, style="Small.TLabel", width=20)
            filename_label.pack(anchor="w", pady=(4, 0))
            filename_label.bind("<Button-1>", lambda event, i=index: self.select_day(i))
            dept, names = tk.StringVar(), tk.StringVar()
            fields = ttk.Frame(table)
            fields.grid(row=rownum, column=1, sticky="ew", padx=(0, 12), pady=8)
            fields.columnconfigure(1, weight=1)
            ttk.Label(fields, text="部门", style="Small.TLabel").grid(row=0, column=0, padx=(0, 6), sticky="w")
            ttk.Label(fields, text="姓名", style="Small.TLabel").grid(row=1, column=0, padx=(0, 6), sticky="w", pady=(6, 0))
            dept_entry = ttk.Entry(fields, textvariable=dept, width=26, font=("Microsoft YaHei UI", 10))
            dept_entry.grid(row=0, column=1, sticky="ew")
            name_entry = ttk.Entry(fields, textvariable=names, width=26, font=("Microsoft YaHei UI", 10))
            name_entry.grid(row=1, column=1, sticky="ew", pady=(6, 0))
            for entry in (dept_entry, name_entry):
                entry.bind("<FocusIn>", lambda event, i=index: self.select_day(i))
            self.entries.extend((dept_entry, name_entry))
            status = tk.StringVar(value="待选图片")
            label = ttk.Label(table, textvariable=status, width=9, style="Status.TLabel")
            label.grid(row=rownum, column=2, padx=(0, 8), sticky="w")
            label.bind("<Button-1>", lambda event, i=index: self.select_day(i))
            checked = tk.BooleanVar()
            check = ttk.Checkbutton(table, variable=checked, command=lambda i=index: self.check_row(i))
            check.grid(row=rownum, column=3)
            self.checks.append(check)
            self.rows.append(dict(image=None, department=dept, names=names, checked=checked,
                                  filename=filename, status=status, raw="", warnings=[], label=label))
            dept.trace_add("write", lambda *_args, i=index: self.department_changed(i))
            names.trace_add("write", lambda *_args, i=index: self.invalidate(i))
        bottom = ttk.Frame(body, padding=(0, 15, 0, 0))
        bottom.grid(row=6, column=0, sticky="ew")
        self.status = tk.StringVar(value="请选择周一到周日各一张截图。")
        ttk.Label(bottom, textvariable=self.status, wraplength=780).pack(side="left", anchor="w")
        ttk.Label(body, text="模板：随程序附带的原始模板　|　模板及原截图不会被修改　|　生僻字请逐一核对",
                  style="Small.TLabel", padding=(0, 10, 0, 0)).grid(row=7, column=0, sticky="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.select_day(0, force=True)
        self.poll_job = root.after(100, self.poll)

    def select_day(self, index, *, force=False):
        if not 0 <= index < len(DAYS):
            return
        self.selected_day.set(index)
        if force or self.preview_day != index:
            self.preview_day = index
            self.screenshot_preview.show(DAYS[index], self.rows[index]["image"])

    def invalidate(self, index):
        row = self.rows[index]
        row["checked"].set(False)
        if row["image"]:
            row["status"].set("待核对")
            row["label"].configure(foreground="#805400")

    def duplicate_departments(self):
        return find_duplicate_departments([row["department"].get() for row in self.rows])

    @staticmethod
    def duplicate_summary(duplicates):
        return "\n".join(f"{'、'.join(days)}：{department}" for department, days in duplicates.items())

    def update_duplicate_notice(self):
        duplicates = self.duplicate_departments()
        if duplicates:
            self.duplicate_notice.set("发现巡查部门重复，请核对：\n" + self.duplicate_summary(duplicates))
            self.duplicate_label.grid()
        else:
            self.duplicate_notice.set("")
            self.duplicate_label.grid_remove()
        return duplicates

    def department_changed(self, index):
        self.invalidate(index)
        self.update_duplicate_notice()

    def check_row(self, index):
        self.select_day(index)
        row = self.rows[index]
        if row["checked"].get():
            if not row["image"] or not row["department"].get().strip() or not row["names"].get().strip():
                row["checked"].set(False)
                messagebox.showinfo("尚未补齐", f"请先选择{DAYS[index]}的图片，并填写部门和姓名。", parent=self.root)
                return
            row["status"].set("已核对")
            row["label"].configure(foreground="#28613a")
        else:
            self.invalidate(index)

    def choose_image(self, index):
        if self.busy:
            return
        self.select_day(index)
        path = filedialog.askopenfilename(parent=self.root, title=f"选择{DAYS[index]}的微信截图",
                   filetypes=[("截图（原图嵌入 Word）", "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with Image.open(path) as image:
                if image.format not in WORD_IMAGE_FORMATS:
                    messagebox.showerror("此格式无法原样写入 Word", "请选择原始 PNG/JPG 截图，或 BMP、GIF、TIFF 图片。程序不会为了导出而转换、压缩原图。", parent=self.root)
                    return
                image.verify()
        except Exception:
            messagebox.showerror("图片无法读取", "请选择正常的 PNG、JPG 或其他常用图片。", parent=self.root)
            return
        row = self.rows[index]
        row.update(image=Path(path), raw="", warnings=[])
        row["filename"].set(Path(path).name if len(Path(path).name) < 28 else Path(path).stem[:22] + "…")
        row["department"].set("")
        row["names"].set("")
        row["status"].set("待识别")
        self.select_day(index, force=True)
        self.status.set("选好图片后点击“识别未核对的截图”；也可直接手动填写。")

    def set_busy(self, value):
        self.busy = value
        for widget in self.controls + self.checks:
            widget.configure(state="disabled" if value else ("readonly" if isinstance(widget, ttk.Combobox) else "normal"))
        for widget in self.entries:
            widget.configure(state="readonly" if value else "normal")

    def start_ocr(self):
        if self.busy:
            return
        targets = [(i, row["image"]) for i, row in enumerate(self.rows) if row["image"] and not row["checked"].get()]
        if not targets:
            messagebox.showinfo("没有待识别图片", "请先选择截图。已核对的行会跳过；重新选图可重新识别。", parent=self.root)
            return
        self.set_busy(True)
        self.status.set("正在加载本地 OCR，首次启动需要稍等…")
        self.executor.submit(self.ocr_worker, targets)

    def ocr_worker(self, targets):
        try:
            if self.engine is None:
                self.engine = LocalOCR()
            for index, path in targets:
                self.events.put(("progress", f"正在识别{DAYS[index]}…"))
                try:
                    result = self.engine.recognize(path)
                    self.events.put(("result", (index, result)))
                except Exception as exc:
                    self.events.put(("row_error", (index, str(exc))))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("done", None))

    def poll(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "progress":
                    self.status.set(payload)
                elif kind == "result":
                    index, result = payload
                    row = self.rows[index]
                    row.update(raw=result.raw_text, warnings=result.warnings)
                    row["department"].set(result.department)
                    row["names"].set(result.names)
                    row["status"].set("需检查原文" if result.warnings else "待核对")
                elif kind == "row_error":
                    index, detail = payload
                    row = self.rows[index]
                    row["status"].set("识别失败")
                    row["warnings"] = [f"识别失败：{detail}。可以手动填写。"]
                elif kind == "error":
                    messagebox.showerror("本地识别暂不可用", payload + "\n\n可以先手动填写，也可重新运行安装脚本。", parent=self.root)
                elif kind == "done":
                    self.set_busy(False)
                    self.status.set("识别结束。点击星期对照右侧截图核对姓名；“原文更正”可查看警告和更正原文。")
                    duplicates = self.update_duplicate_notice()
                    if duplicates:
                        messagebox.showwarning("巡查部门重复", self.duplicate_summary(duplicates)
                            + "\n\n同一个巡查部门出现在多天，请核对对应日期的截图和部门填写。", parent=self.root)
        except queue.Empty:
            pass
        self.poll_job = self.root.after(100, self.poll)

    def preview(self, index):
        row = self.rows[index]
        if not row["image"]:
            messagebox.showinfo("尚未选图", f"请先选择{DAYS[index]}的截图。", parent=self.root)
            return
        win = tk.Toplevel(self.root)
        win.title(f"{DAYS[index]} · 修改识别原文")
        win.geometry("950x780")
        win.transient(self.root)
        win.grab_set()
        left = ttk.Frame(win, padding=12)
        left.pack(side="left", fill="both", expand=True)
        canvas = tk.Canvas(left, bg="#eeeeee", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        try:
            with Image.open(row["image"]) as source:
                picture = ImageOps.exif_transpose(source).convert("RGB")
            # Screen-sized preview; use the original file for pixel-level review.
            picture.thumbnail((440, max(300, self.root.winfo_screenheight() - 160)), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(picture)
            canvas.image = photo
            canvas.create_image(0, 0, anchor="nw", image=photo)
        except Exception as exc:
            messagebox.showerror("图片无法读取", str(exc), parent=win)
            win.destroy()
            return
        right = ttk.Frame(win, padding=12, width=440)
        right.pack(side="right", fill="both", expand=True)
        ttk.Label(right, text="OCR 原文（可粘贴微信原文更正）").pack(anchor="w")
        text = tk.Text(right, width=44, height=24, wrap="word", font=("Microsoft YaHei UI", 10), undo=True)
        text.pack(fill="both", expand=True, pady=8)
        text.insert("1.0", row["raw"])
        ttk.Label(right, text="\n".join(row["warnings"]) or "请重点检查部门及每一个姓名用字。", wraplength=380,
                  foreground="#805400").pack(anchor="w", pady=(4, 12))

        def apply():
            result = parse_fields(text.get("1.0", "end-1c"))
            row.update(raw=result.raw_text, warnings=result.warnings)
            row["department"].set(result.department)
            row["names"].set(result.names)
            row["status"].set("需检查原文" if result.warnings else "待核对")
            win.destroy()

        ttk.Button(right, text="从上面的原文提取部门和姓名", command=apply).pack(anchor="w")
        ttk.Button(right, text="关闭", command=win.destroy).pack(anchor="w", pady=(8, 0))

    def export(self):
        if self.busy:
            return
        try:
            filename = report_filename(self.start_year.get(), self.end_year.get(), self.semester.get(), self.week.get())
            records = []
            for day, row in zip(DAYS, self.rows):
                if not row["image"]:
                    raise ValueError(f"请先选择{day}的截图")
                if not row["checked"].get():
                    raise ValueError(f"请核对{day}的部门和姓名，勾选“已核对”后再导出")
                records.append(DayRecord(row["image"], row["department"].get(), row["names"].get(), True))
            duplicates = self.update_duplicate_notice()
            if duplicates and not messagebox.askyesno("巡查部门重复，是否继续导出？",
                    self.duplicate_summary(duplicates)
                    + "\n\n请核对日期、截图和部门填写。确认信息无误，仍要继续导出吗？",
                    icon="warning", default=messagebox.NO, parent=self.root):
                return
            path = filedialog.asksaveasfilename(parent=self.root, title="导出巡查汇总 Word",
                defaultextension=".docx", filetypes=[("Word 文档", "*.docx")],
                initialfile=filename)
            if not path:
                return
            # The Windows save dialog handles the explicit overwrite question.
            self.last_output = build_docx(records, Path(path), overwrite=True)
            self.status.set(f"已导出：{self.last_output.name}")
            messagebox.showinfo("导出完成", f"已保存到：\n{self.last_output}\n\n请用 Word 打开，最后检查分页、图片和姓名。", parent=self.root)
        except PermissionError:
            messagebox.showerror("无法保存", "文件可能正在 Word 中打开。请关闭该文件，或换一个文件名。", parent=self.root)
        except Exception as exc:
            messagebox.showerror("未能导出", str(exc), parent=self.root)

    def close(self):
        if self.busy:
            messagebox.showinfo("正在识别", "请等当前识别完成后再关闭。", parent=self.root)
            return
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.after_cancel(self.poll_job)
        self.root.destroy()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    PatrolApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        (BASE / "startup-error.log").write_text(traceback.format_exc(), encoding="utf-8")
        try:
            messagebox.showerror("启动失败", "程序未能启动。错误详情已写入程序文件夹中的 startup-error.log。\n可尝试双击 install.cmd 重新安装组件。")
        except Exception:
            pass
        raise
