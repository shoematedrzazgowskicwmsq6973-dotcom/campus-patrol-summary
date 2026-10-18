import hashlib
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lxml import etree as ET
from PIL import Image
from patrol_core import DAYS, NS, TEMPLATE, DayRecord, build_docx, find_duplicate_departments, parse_fields, report_filename, week_label

MESSAGE = """大学城校区日常公共区域巡查
部门： 校团委社团管理部
姓名: 测试甲、测试乙、测试丙、测试丁
开始-结束时间：2026年10月17日12：00-12：44 22：00-22：45
巡查范围：教学楼，架空层，校道、体育馆，文化活动中心周围
巡查情况：无异常"""


class FieldTests(unittest.TestCase):
    def test_report_filename_uses_selected_years_and_semester(self):
        self.assertEqual(report_filename("2026", "2027", "第一学期", "7"),
                         "广东工业大学2026-2027学年第一学期第七周公共区域巡查汇总.docx")
        self.assertEqual(report_filename(" 2028 ", " 2029 ", "第二学期", "12"),
                         "广东工业大学2028-2029学年第二学期第十二周公共区域巡查汇总.docx")

    def test_report_filename_rejects_invalid_years_or_semester(self):
        for start, end, semester in (("", "2027", "第一学期"), ("2026", "2026", "第一学期"),
                ("2026", "2028", "第一学期"), ("2027", "2026", "第一学期"),
                ("20/6", "2027", "第一学期"), ("２０２６", "2027", "第一学期"),
                ("2026", "2027", "第三学期")):
            with self.subTest(start=start, end=end, semester=semester), self.assertRaises(ValueError):
                report_filename(start, end, semester, "7")

    def test_duplicate_departments_ignore_whitespace_and_group_all_days(self):
        result = find_duplicate_departments([
            "校团委社团管理部", "", " 校团委 社团管理部 ", "校研会文体部",
            "校研会文体部", "\u3000", "校团委\t社团管理部"])
        self.assertEqual(result, {"校团委社团管理部": ["周一", "周三", "周日"], "校研会文体部": ["周四", "周五"]})

    def test_same_department_suffix_in_different_organizations_is_not_duplicate(self):
        self.assertEqual(find_duplicate_departments(["校团委文体部", "校研会文体部", "", " ", "\u3000"]), {})

    def test_user_message(self):
        result = parse_fields(MESSAGE)
        self.assertEqual(result.department, "校团委社团管理部")
        self.assertEqual(result.names, "测试甲 测试乙 测试丙 测试丁")
        self.assertEqual(result.warnings, [])

    def test_names_wrap_and_colon_variants(self):
        result = parse_fields("群昵称不应提取\n部 门 : 校团委社团\n管理部\n姓 名 ： 测试甲 测试乙\n测试丙、测试丁\n开始—结束时间：12:00\n姓名不相关")
        self.assertEqual(result.department, "校团委社团管理部")
        self.assertEqual(result.names, "测试甲 测试乙 测试丙 测试丁")

    def test_ambiguous_multiple_messages_requires_manual(self):
        result = parse_fields(MESSAGE + "\n" + MESSAGE)
        self.assertEqual((result.department, result.names), ("", ""))
        self.assertTrue(result.warnings)

    def test_wrapped_name_fragments_and_ocr_separator(self):
        result = parse_fields("部门：校团委社团管理部\n姓名：测试甲、测试乙、测试丙：测试\n丁\n开始-结束时间：12:00")
        self.assertEqual(result.names, "测试甲 测试乙 测试丙 测试丁")
        self.assertTrue(result.warnings)

    def test_no_nickname_inference(self):
        result = parse_fields("大学城校团委社团管理部张三\n没有巡查正文")
        self.assertEqual((result.department, result.names), ("", ""))

    def test_missing_stop_does_not_swallow_chat(self):
        result = parse_fields("部门：校团委社团管理部\n姓名：测试甲、测试乙\n收到，谢谢！")
        self.assertEqual(result.names, "测试甲 测试乙")
        self.assertTrue(result.warnings)

    def test_week_validation(self):
        for raw, expected in (("7", "七"), ("10", "十"), ("11", "十一"), ("20", "二十"), ("30", "三十")):
            self.assertEqual(week_label(raw), expected)
        for raw in ("", "0", "31", "..", "7/1", "七", "７"):
            with self.assertRaises(ValueError):
                week_label(raw)


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.template_hash = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest()
        self.records = []
        for index in range(7):
            path = self.folder / f"{index}.png"
            # Include a wide screenshot to verify aspect-fit rather than stretch.
            image = Image.new("RGB", (1000, 200) if index == 6 else (282 + index, 613), (index * 30, 200, 250))
            image.save(path)
            self.records.append(DayRecord(path, f"测试部门{index}", "测试甲 测试乙", True))

    def test_package_fidelity_and_seven_images(self):
        target = build_docx(self.records, self.folder / "汇总.docx")
        with ZipFile(TEMPLATE) as source, ZipFile(target) as output:
            source_data = {name: source.read(name) for name in source.namelist()}
            output_data = {name: output.read(name) for name in output.namelist()}
        changed = {"word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"}
        for name in source_data:
            if name not in changed and not name.startswith("word/media/"):
                self.assertEqual(source_data[name], output_data[name], name)
        self.assertFalse(set(n for n in source_data if n.startswith("word/media/")) & output_data.keys())
        self.assertEqual(len([n for n in output_data if n.startswith("word/media/")]), 7)
        root = ET.fromstring(output_data["word/document.xml"])
        old = ET.fromstring(source_data["word/document.xml"])
        for path in ("//w:sectPr", "//w:tblPr", "//w:tblGrid", "//w:tcPr", "//w:trPr"):
            self.assertEqual([ET.tostring(n) for n in old.xpath(path, namespaces=NS)],
                             [ET.tostring(n) for n in root.xpath(path, namespaces=NS)])
        rows = root.xpath("//w:tbl/w:tr", namespaces=NS)
        for i, record in enumerate(self.records, 1):
            cell = rows[1].findall("w:tc", NS)[i]
            self.assertEqual("".join(cell.xpath(".//w:t/text()", namespaces=NS)), f"{record.department} {record.names}")
            image_cell = rows[2].findall("w:tc", NS)[i]
            self.assertEqual(len(image_cell.xpath(".//a:blip", namespaces=NS)), 1)
            extent = image_cell.find(".//wp:extent", NS)
            ratio = int(extent.get("cx")) / int(extent.get("cy"))
            with Image.open(record.image) as image:
                self.assertAlmostEqual(ratio, image.width / image.height, places=5)
                with Image.open(BytesIO(output_data[f"word/media/patrol_day{i}.png"])) as embedded:
                    self.assertEqual(image.size, embedded.size)
                    self.assertEqual(image.tobytes(), embedded.tobytes())
        self.assertNotIn("Text", "".join(root.xpath("//w:t/text()", namespaces=NS)))
        ids = root.xpath("//wp:docPr/@id", namespaces=NS)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(), self.template_hash)

    def test_refuse_incomplete_or_unreviewed(self):
        target = self.folder / "result.docx"
        with self.assertRaises(ValueError):
            build_docx(self.records[:6], target)
        self.records[0].reviewed = False
        with self.assertRaises(ValueError):
            build_docx(self.records, target)
        self.assertFalse(target.exists())

    def test_existing_file_and_template_are_protected(self):
        path = self.folder / "existing.docx"
        path.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            build_docx(self.records, path)
        self.assertEqual(path.read_bytes(), b"existing")
        with self.assertRaises(ValueError):
            build_docx(self.records, TEMPLATE, overwrite=True)


if __name__ == "__main__":
    unittest.main()
