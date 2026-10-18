from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from app import PatrolApp
from patrol_core import Fields


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.image = Path(self.directory.name) / "截图.png"
        Image.new("RGB", (750, 1620), "white").save(self.image)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = PatrolApp(self.root)
        self.addCleanup(self.app.close)

    def select(self, index):
        with patch("app.filedialog.askopenfilename", return_value=str(self.image)):
            self.app.choose_image(index)

    def test_edit_and_image_change_invalidate_review(self):
        self.select(0)
        row = self.app.rows[0]
        row["department"].set("校团委社团管理部")
        row["names"].set("测试甲 测试乙 测试丙 测试丁")
        row["checked"].set(True)
        self.app.check_row(0)
        self.assertTrue(row["checked"].get())
        row["names"].set("测试甲")
        self.assertFalse(row["checked"].get())
        row["checked"].set(True)
        self.select(0)
        self.assertFalse(row["checked"].get())
        self.assertEqual(row["names"].get(), "")

    def test_empty_fields_cannot_be_checked_or_exported(self):
        self.select(0)
        row = self.app.rows[0]
        row["checked"].set(True)
        with patch("app.messagebox.showinfo"):
            self.app.check_row(0)
        self.assertFalse(row["checked"].get())
        self.app.week.set("7")
        with patch("app.messagebox.showerror") as error, patch("app.filedialog.asksaveasfilename") as dialog:
            self.app.export()
        self.assertTrue(error.called)
        dialog.assert_not_called()

    def test_export_dialog_after_seven_reviews(self):
        for index in range(7):
            self.select(index)
            row = self.app.rows[index]
            row["department"].set(f"测试部门{index}")
            row["names"].set("测试甲 测试乙")
            row["checked"].set(True)
            self.app.check_row(index)
        self.app.week.set("7")
        self.app.start_year.set("2028")
        self.app.end_year.set("2029")
        self.app.semester.set("第二学期")
        target = Path(self.directory.name) / "巡查汇总.docx"
        with patch("app.filedialog.asksaveasfilename", return_value=str(target)) as dialog, patch("app.messagebox.showinfo") as info:
            self.app.export()
        self.assertTrue(target.is_file())
        self.assertTrue(info.called)
        self.assertEqual(dialog.call_args.kwargs["initialfile"],
                         "广东工业大学2028-2029学年第二学期第七周公共区域巡查汇总.docx")

    def test_academic_period_defaults_and_readonly_semester_after_ocr(self):
        self.assertEqual(self.app.start_year.get(), "2026")
        self.assertEqual(self.app.end_year.get(), "2027")
        self.assertEqual(self.app.semester.get(), "第一学期")
        self.app.set_busy(True)
        self.assertEqual(str(self.app.semester_box.cget("state")), "disabled")
        self.app.set_busy(False)
        self.assertEqual(str(self.app.semester_box.cget("state")), "readonly")

    def test_invalid_academic_period_stops_before_save_dialog(self):
        self.app.week.set("7")
        self.app.start_year.set("2026")
        self.app.end_year.set("2026")
        with patch("app.messagebox.showerror") as error, patch("app.filedialog.asksaveasfilename") as dialog:
            self.app.export()
        error.assert_called_once()
        self.assertIn("结束年份", error.call_args.args[1])
        dialog.assert_not_called()

    def test_duplicate_notice_updates_and_clears_after_correction(self):
        self.select(0)
        self.select(2)
        self.app.rows[0]["department"].set("校团委社团管理部")
        self.app.rows[0]["names"].set("测试甲")
        self.app.rows[0]["checked"].set(True)
        self.app.rows[2]["department"].set("校团委 社团管理部")
        self.assertIn("周一、周三", self.app.duplicate_notice.get())
        self.assertIn("校团委社团管理部", self.app.duplicate_notice.get())
        self.assertEqual(self.app.duplicate_label.winfo_manager(), "grid")
        self.assertTrue(self.app.rows[0]["checked"].get())
        self.app.rows[2]["department"].set("校团委校园文化部")
        self.assertEqual(self.app.duplicate_notice.get(), "")
        self.assertEqual(self.app.duplicate_label.winfo_manager(), "")

    def test_ocr_completion_shows_one_warning_for_duplicate_departments(self):
        self.app.set_busy(True)
        self.app.events.put(("result", (0, Fields("校团委社团管理部", "测试甲"))))
        self.app.events.put(("result", (2, Fields("校团委社团管理部", "测试乙"))))
        self.app.events.put(("done", None))
        self.root.after_cancel(self.app.poll_job)
        with patch("app.messagebox.showwarning") as warning:
            self.app.poll()
        warning.assert_called_once()
        self.assertIn("周一、周三", warning.call_args.args[1])
        self.assertFalse(self.app.busy)

    def test_duplicate_export_can_be_cancelled_or_explicitly_continued(self):
        for index in range(7):
            self.select(index)
            row = self.app.rows[index]
            row["department"].set("重复测试部门" if index in (0, 2, 6) else f"其他部门{index}")
            row["names"].set("测试甲 测试乙")
            row["checked"].set(True)
        self.app.week.set("7")
        with patch("app.messagebox.askyesno", return_value=False) as confirm, patch("app.filedialog.asksaveasfilename") as dialog:
            self.app.export()
        confirm.assert_called_once()
        self.assertIn("周一、周三、周日", confirm.call_args.args[1])
        dialog.assert_not_called()
        self.assertTrue(all(row["checked"].get() for row in self.app.rows))
        target = Path(self.directory.name) / "已确认重复部门.docx"
        with patch("app.messagebox.askyesno", return_value=True), patch("app.filedialog.asksaveasfilename", return_value=str(target)), patch("app.messagebox.showinfo"):
            self.app.export()
        self.assertTrue(target.is_file())

    def test_selecting_images_and_weekdays_updates_preview_without_editing_data(self):
        other = Path(self.directory.name) / "另一张截图.png"
        Image.new("RGB", (400, 900), "navy").save(other)
        self.select(0)
        self.assertEqual(self.app.selected_day.get(), 0)
        self.assertEqual(self.app.screenshot_preview.picture.size, (750, 1620))
        self.app.rows[0]["department"].set("测试部门")
        self.app.rows[0]["names"].set("测试甲")
        self.app.rows[0]["checked"].set(True)
        with patch("app.filedialog.askopenfilename", return_value=str(other)):
            self.app.choose_image(3)
        self.assertEqual(self.app.selected_day.get(), 3)
        self.assertEqual(self.app.screenshot_preview.image_path, other)
        self.assertEqual(self.app.screenshot_preview.picture.getpixel((0, 0)), (0, 0, 128))
        # Exercise the real weekday control rather than directly assigning state.
        self.app.day_selectors[0].invoke()
        self.assertEqual(self.app.screenshot_preview.image_path, self.image)
        self.assertEqual(self.app.screenshot_preview.picture.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(self.app.rows[0]["names"].get(), "测试甲")
        self.assertTrue(self.app.rows[0]["checked"].get())
        self.app.day_selectors[6].invoke()
        self.app.screenshot_preview.render()
        self.assertIsNone(self.app.screenshot_preview.picture)
        self.assertFalse(self.app.screenshot_preview.canvas.find_withtag("screenshot"))
        self.assertIn("周日", self.app.screenshot_preview.empty_message)

    def test_replaced_image_and_missing_file_do_not_show_stale_preview(self):
        self.select(2)
        # Reusing the same filename should refresh its pixels as well.
        Image.new("RGB", (600, 300), "red").save(self.image)
        self.select(2)
        self.assertEqual(self.app.screenshot_preview.picture.size, (600, 300))
        self.assertEqual(self.app.screenshot_preview.picture.getpixel((0, 0)), (255, 0, 0))
        self.app.select_day(0)
        self.image.unlink()
        self.app.select_day(2)
        self.assertIsNone(self.app.screenshot_preview.picture)
        self.assertIn("无法读取", self.app.screenshot_preview.empty_message)


if __name__ == "__main__":
    unittest.main()
