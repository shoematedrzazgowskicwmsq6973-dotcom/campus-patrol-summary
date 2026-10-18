"""Local field extraction and a narrowly scoped patch of the supplied Word template."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile

from lxml import etree as ET
from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent
TEMPLATE = BASE / "resources" / "template.docx"
DAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
DEPT = re.compile(r"部\s*门\s*[:：]")
NAME = re.compile(r"姓\s*名\s*[:：]")
STOP = re.compile(r"(?:开始\s*[-—－~～至到]?\s*结束\s*时间|开始时间|结束时间|巡查范围|巡查情况|巡查时间|日期)\s*[:：]?")


@dataclass
class Fields:
    department: str = ""
    names: str = ""
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class DayRecord:
    image: Path
    department: str
    names: str
    reviewed: bool = False


def find_duplicate_departments(departments: list[str]) -> dict[str, list[str]]:
    """Compare full organization/department names, ignoring whitespace only."""
    groups = {}
    for day, department in zip(DAYS, departments):
        normalized = re.sub(r"\s+", "", department)
        if normalized:
            groups.setdefault(normalized, []).append(day)
    return {department: days for department, days in groups.items() if len(days) > 1}


def parse_fields(text: str) -> Fields:
    """Read explicit labels only; never infer people from WeChat nicknames."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    result = Fields(raw_text=text)
    depts, names = list(DEPT.finditer(text)), list(NAME.finditer(text))
    if len(depts) > 1 or len(names) > 1:
        result.warnings.append("截图里出现多组部门或姓名，请对照截图手动填写")
        return result
    if len(depts) != 1 or len(names) != 1:
        result.warnings.append("未找到完整的“部门：”“姓名：”标签，请对照截图手动填写")
        return result
    dm, nm = depts[0], names[0]
    if nm.start() <= dm.end():
        result.warnings.append("部门和姓名顺序异常，请对照截图手动填写")
        return result
    result.department = re.sub(r"\s+", "", text[dm.end():nm.start()]).strip("，,；;。")
    rest = text[nm.end():]
    stop = STOP.search(rest)
    # Without a known following field, accept just the first nonempty name line.
    # This avoids treating chat messages below the report as names.
    if stop:
        raw_names = rest[:stop.start()]
    else:
        raw_names = next((line.strip() for line in rest.splitlines() if line.strip()), "")
        result.warnings.append("未识别到姓名栏之后的时间标签，请检查姓名是否完整")
    # In the supplied format punctuation separates people; a newline may split
    # a single name (e.g. 测试\n丁). Only join an obvious one-character fragment,
    # and disclose that normalization for review rather than guessing identities.
    def join_line(match):
        before = raw_names[:match.start()]
        after = raw_names[match.end():]
        left = re.split(r"[\s、，,；;：:]+", before)[-1]
        right = re.split(r"[\s、，,；;：:]+", after)[0]
        if left and right and min(len(left), len(right)) == 1 and len(left + right) <= 4:
            result.warnings.append("姓名中有跨行片段，已连接，请对照截图核对")
            return ""
        return " "

    raw_names = raw_names.strip()
    raw_names = re.sub(r"[ \t]*\n[ \t]*", join_line, raw_names)
    if re.search(r"[:：]", raw_names):
        result.warnings.append("姓名中的冒号已按分隔符处理，请检查")
    result.names = " ".join(s for s in re.split(r"[\s、，,；;：:•]+", raw_names.strip(" 。；;,，")) if s)
    if not result.department or not result.names:
        result.warnings.append("部门或姓名为空，请手动补齐")
    if result.department and (len(result.department) > 35 or not result.department.endswith(("部", "会", "队", "中心", "处"))):
        result.warnings.append("部门识别结果需要检查")
    if result.names and not re.fullmatch(r"[\u3400-\u9fff\uF900-\uFAFF\U00020000-\U000323AF· ]+", result.names):
        result.warnings.append("姓名中有非中文字符，请检查")
    return result


class LocalOCR:
    """Use packaged model files explicitly, so inference never auto-downloads."""

    def __init__(self):
        import rapidocr
        from rapidocr import RapidOCR

        models = Path(rapidocr.__file__).parent / "models"
        # The installer verifies the exact models shipped in the pinned wheel.
        def model(kind: str) -> str:
            candidates = sorted(models.glob(f"*{kind}*.onnx"))
            if len(candidates) != 1:
                raise RuntimeError(f"本地 OCR 的 {kind} 模型不完整，请重新运行安装脚本。")
            return str(candidates[0])

        self.engine = RapidOCR(params={
            "Det.model_path": model("det"),
            "Cls.model_path": model("cls"),
            "Rec.model_path": model("rec"),
        })

    def recognize(self, path: Path) -> Fields:
        import numpy as np
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            # Embedded Word examples are small. Enlarge for OCR only; the actual
            # output screenshot remains full-frame and keeps its aspect ratio.
            if image.width < 900:
                ratio = min(3.0, 900 / image.width)
                image = image.resize((round(image.width * ratio), round(image.height * ratio)), Image.Resampling.LANCZOS)
            if image.width > 2400:
                image.thumbnail((2400, 12000), Image.Resampling.LANCZOS)
            bgr = np.asarray(image)[:, :, ::-1].copy()
        output = self.engine(bgr)
        lines = list(output.txts) if output.txts is not None else []
        result = parse_fields("\n".join(lines))
        if output.scores is not None and len(output.scores) and min(output.scores) < 0.85:
            result.warnings.append("图片中有低置信度文字，请重点核对姓名")
        return result


def week_label(value: str) -> str:
    value = value.strip()
    if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 30:
        raise ValueError("周次请输入 1 到 30 的数字")
    number = int(value)
    digits = "零一二三四五六七八九"
    if number < 10:
        return digits[number]
    tens, ones = divmod(number, 10)
    return (digits[tens] if tens > 1 else "") + "十" + (digits[ones] if ones else "")


def report_filename(start_year: str, end_year: str, semester: str, week: str) -> str:
    start_year, end_year = start_year.strip(), end_year.strip()
    if not all(re.fullmatch(r"[1-9][0-9]{3}", year) for year in (start_year, end_year)):
        raise ValueError("学年起止年份请输入4位数字，例如 2026 和 2027")
    if int(end_year) != int(start_year) + 1:
        raise ValueError("学年结束年份应比开始年份大1，例如 2026 至 2027 学年")
    if semester not in ("第一学期", "第二学期"):
        raise ValueError("请选择第一学期或第二学期")
    return f"广东工业大学{start_year}-{end_year}学年{semester}第{week_label(week)}周公共区域巡查汇总.docx"


def _xml(data: bytes):
    return ET.fromstring(data, parser=ET.XMLParser(resolve_entities=False, no_network=True))


def _serialized(root) -> bytes:
    return ET.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _text(cell, value: str):
    nodes = cell.xpath(".//w:t", namespaces=NS)
    if not nodes:
        raise ValueError("模板中的文字位置无法识别，请重新选择原模板")
    nodes[0].text = value
    nodes[0].set(XML_SPACE, "preserve")
    for node in nodes[1:]:
        node.text = ""


def build_docx(records: list[DayRecord], output: Path, template: Path = TEMPLATE, *, overwrite: bool = False) -> Path:
    """Change seven text cells and seven images, preserving all other parts."""
    output, template = Path(output).resolve(), Path(template).resolve()
    if output == template or output == TEMPLATE.resolve():
        raise ValueError("输出文件不能覆盖模板")
    if output.suffix.lower() != ".docx":
        raise ValueError("输出文件必须是 .docx 格式")
    if len(records) != 7:
        raise ValueError("请为周一到周日各选择一张截图")
    for day, record in zip(DAYS, records):
        if not record.reviewed:
            raise ValueError(f"请先核对{day}的部门和姓名，并勾选“已核对”")
        if not record.department.strip() or not record.names.strip():
            raise ValueError(f"{day}的部门和姓名不能为空")
        if not record.image.is_file():
            raise ValueError(f"{day}的截图已移动或不存在，请重新选择")
    if output.exists() and not overwrite:
        raise FileExistsError("输出文件已存在，请换一个文件名")

    with ZipFile(template) as archive:
        original_infos = archive.infolist()
        data = {info.filename: archive.read(info.filename) for info in original_infos}
    root = _xml(data["word/document.xml"])
    rels = _xml(data["word/_rels/document.xml.rels"])
    types = _xml(data["[Content_Types].xml"])
    tables = root.xpath("/w:document/w:body/w:tbl", namespaces=NS)
    matches = [t for t in tables if t.xpath("./w:tr[1]/w:tc//w:t/text()", namespaces=NS) == ["时间", *DAYS]]
    if len(matches) != 1:
        raise ValueError("模板结构不匹配，需要包含“时间、周一至周日”的原始表格")
    rows = matches[0].findall("w:tr", NS)
    if len(rows) != 3 or any(len(row.findall("w:tc", NS)) != 8 for row in rows):
        raise ValueError("模板表格应为三行八列，请使用随程序附带的模板")
    text_cells, image_cells = rows[1].findall("w:tc", NS), rows[2].findall("w:tc", NS)
    seed_run = image_cells[1].xpath(".//w:r[w:drawing]", namespaces=NS)
    if len(seed_run) != 1:
        raise ValueError("模板缺少参考图片位置")
    seed_run = deepcopy(seed_run[0])
    seed_extent = seed_run.find(".//wp:extent", NS)
    max_w, max_h = int(seed_extent.get("cx")), int(seed_extent.get("cy"))
    max_id = max([int(n.get("id", "0")) for n in root.xpath("//wp:docPr", namespaces=NS)] + [0])
    used_rel_ids = {n.get("Id") for n in rels}
    added, old_targets = {}, set()

    for index, record in enumerate(records, 1):
        _text(text_cells[index], f"{record.department.strip()} {record.names.strip()}")
        cell = image_cells[index]
        blips = cell.xpath(".//a:blip", namespaces=NS)
        if len(blips) == 1:
            rel_id = blips[0].get(f"{{{NS['r']}}}embed")
            rel = next(n for n in rels if n.get("Id") == rel_id)
            old_targets.add("word/" + rel.get("Target"))
            drawing = cell.find(".//w:drawing", NS)
        elif not blips:
            # Sunday is a text placeholder. Retain its cell/paragraph styling.
            paragraphs = cell.findall("w:p", NS)
            paragraph = paragraphs[0]
            for child in list(paragraph):
                if child.tag != f"{{{NS['w']}}}pPr":
                    paragraph.remove(child)
            for p in paragraphs[1:]:
                cell.remove(p)
            run = deepcopy(seed_run)
            paragraph.append(run)
            drawing = run.find("w:drawing", NS)
            for node in drawing.iter():
                for attr in list(node.attrib):
                    if ET.QName(attr).localname in ("anchorId", "editId"):
                        del node.attrib[attr]
            rel_id = f"rIdPatrol{index}"
            while rel_id in used_rel_ids:
                rel_id += "x"
            used_rel_ids.add(rel_id)
            rel = ET.SubElement(rels, f"{{{NS['rel']}}}Relationship", Id=rel_id,
                                Type=f"{NS['r']}/image", Target="")
            drawing.find(".//a:blip", NS).set(f"{{{NS['r']}}}embed", rel_id)
        else:
            raise ValueError(f"模板{DAYS[index - 1]}的位置含多张图片，无法安全替换")

        with Image.open(record.image) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            width, height = image.size
        name = f"word/media/patrol_day{index}.png"
        added[name] = buffer.getvalue()
        rel.set("Target", name.removeprefix("word/"))
        scale = min(max_w / width, max_h / height)
        cx, cy = round(width * scale), round(height * scale)
        extent = drawing.find(".//wp:extent", NS)
        extent.set("cx", str(cx)); extent.set("cy", str(cy))
        for node in drawing.xpath(".//a:xfrm/a:ext", namespaces=NS):
            node.set("cx", str(cx)); node.set("cy", str(cy))
        docpr = drawing.find(".//wp:docPr", NS)
        docpr.set("id", str(max_id + index))
        docpr.set("name", f"{DAYS[index - 1]}巡查截图")

    if not any(n.get("Extension", "").lower() == "png" for n in types):
        ET.SubElement(types, f"{{{NS['ct']}}}Default", Extension="png", ContentType="image/png")
    # Remove replaced examples, including hidden unused screenshot bytes. Keep
    # an old part only if another package relationship still refers to it.
    still_used = {"word/" + n.get("Target", "") for n in rels}
    import posixpath
    for part, payload in data.items():
        if part.endswith(".rels") and part != "word/_rels/document.xml.rels":
            base = posixpath.dirname(posixpath.dirname(part))
            other = _xml(payload)
            for rel in other:
                target = rel.get("Target", "")
                if rel.get("TargetMode") != "External":
                    still_used.add(posixpath.normpath(posixpath.join(base, target)))
    remove = old_targets - still_used
    for node in list(types):
        if node.get("PartName", "").lstrip("/") in remove:
            types.remove(node)
    data["word/document.xml"] = _serialized(root)
    data["word/_rels/document.xml.rels"] = _serialized(rels)
    data["[Content_Types].xml"] = _serialized(types)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".patrol-", suffix=".docx", delete=False) as handle:
            temporary = Path(handle.name)
        with ZipFile(temporary, "w") as archive:
            for info in original_infos:
                if info.filename not in remove:
                    archive.writestr(info, data[info.filename])
            for name, payload in added.items():
                archive.writestr(name, payload)
        if overwrite:
            temporary.replace(output)
        else:
            # Windows rename refuses an existing destination, even if one
            # appeared after the initial check.
            temporary.rename(output)
        return output
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
