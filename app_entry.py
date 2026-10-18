"""Windows executable entry point and an offline release diagnostic."""
from pathlib import Path
import json
import os
import sys
import traceback


def self_test(result_path):
    import socket
    import time
    import tkinter as tk
    from unittest.mock import patch
    from zipfile import ZipFile
    import rapidocr
    import onnxruntime
    import numpy
    import PIL
    import lxml
    from app import PatrolApp
    from patrol_core import BASE, TEMPLATE, LocalOCR, DayRecord, build_docx, report_filename

    def deny_network(*args, **kwargs):
        raise RuntimeError("Network disabled during offline release diagnostic")

    socket.socket.connect = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    result_path = Path(result_path).resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    fixture = BASE / "resources" / "ocr_fixture.png"
    assert TEMPLATE.is_file() and fixture.is_file()
    frozen = bool(getattr(sys, "frozen", False))
    if frozen:
        bundle_root = Path(sys._MEIPASS).resolve()
        for module in (rapidocr, onnxruntime, numpy, PIL, lxml):
            assert Path(module.__file__).resolve().is_relative_to(bundle_root), "External Python package used"
    root = tk.Tk()
    root.withdraw()
    app = PatrolApp(root)
    try:
        assert (app.start_year.get(), app.end_year.get(), app.semester.get()) == ("2026", "2027", "第一学期")
        app.engine = LocalOCR()
        for index in (0, 2):
            with patch("app.filedialog.askopenfilename", return_value=str(fixture)):
                app.choose_image(index)
            assert app.screenshot_preview.image_path == fixture
        with patch("app.messagebox.showwarning") as warning:
            app.start_ocr()
            deadline = time.monotonic() + 60
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.03)
            assert not app.busy, "OCR timed out"
            for index in (0, 2):
                assert app.rows[index]["department"].get() == "校团委测试部"
                assert app.rows[index]["names"].get() == "张三 李四"
            warning.assert_called_once()
        assert "周一、周三" in app.duplicate_notice.get()
        app.day_selectors[6].invoke()
        assert app.screenshot_preview.picture is None
        app.day_selectors[0].invoke()
        assert app.screenshot_preview.picture is not None
        filename = report_filename("2027", "2028", "第二学期", "7")
        records = [DayRecord(fixture, f"测试部门{i}", "张三 李四", True) for i in range(7)]
        report = build_docx(records, result_path.parent / "synthetic-test-report.docx", overwrite=True)
        with ZipFile(report) as archive:
            assert len([n for n in archive.namelist() if n.startswith("word/media/")]) == 7
        result_path.write_text(json.dumps({
            "ok": True, "packaged": frozen, "network_disabled": True,
            "ocr_department": "校团委测试部", "ocr_names": "张三 李四",
            "preview_switching": True, "duplicate_warning": True,
            "export_seven_images": True, "filename_example": filename,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        if app.busy:
            app.set_busy(False)
        app.close()


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        result_path = Path(sys.argv[2])
        try:
            self_test(result_path)
        except Exception:
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result_path.write_text(json.dumps({"ok": False, "error": traceback.format_exc()}, ensure_ascii=False, indent=2), encoding="utf-8")
            raise
        return
    from app import main as desktop_main
    try:
        desktop_main()
    except Exception:
        from tkinter import messagebox
        log_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "PatrolSummary"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "startup-error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        messagebox.showerror("启动失败", f"错误详情已保存到：\n{log_path}\n\n请完整解压下载包后再启动。")


if __name__ == "__main__":
    main()
