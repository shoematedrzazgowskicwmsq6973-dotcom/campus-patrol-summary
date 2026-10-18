# 广东工业大学（大学城校区）公共区域巡查汇总 GDUT

面向 **广东工业大学（大学城校区） / GDUT** 的日常公共区域巡查汇总工具。将周一到周日各一张微信巡查截图填入 Word 模板，自动提取“部门”和“姓名”，核对后导出，按该校区现有汇总格式生成文档。

## 普通用户下载使用

1. 打开本仓库的 **Releases**，下载 `PatrolSummary-v1.0.1-windows-x64.zip`。不要下载 GitHub 自动提供的 `Source code` 来直接运行。
2. 将 ZIP **完整解压**到普通文件夹，例如“文档”或 D 盘。
3. 双击解压文件夹中的 **PatrolSummary.exe**。请保留旁边的 `_internal` 文件夹，不要只复制 EXE。

程序包含 Python 运行环境、中文 OCR 模型和模板；无需另装 Python、配置 API Key、启动服务器或单独部署模型。识别和导出在本机完成，正常使用不需要联网。不需要安装 Word 才能导出，查看 `.docx` 可使用 Word、WPS 等兼容软件。

当前提供 **Windows x64** 程序包，在 Windows 11 x64 本机验证。尚未在一台全新、未安装 Python 的独立电脑上验证；本机已使用独立解压目录和受限环境变量测试，不等同于独立设备验证。其他操作系统需要自行从源码配置和打包。

## 每周操作

1. 设置学年、学期、周次。默认是 **2026 至 2027 学年、第一学期**，周次填数字，如 `7`。
2. 按周一到周日分别选择一张原始截图。选图后右侧立即预览，点击星期或当天输入框即可切换。
3. 点击“识别未核对的截图”，对照预览逐字核对部门及姓名。可直接在输入框修改。
4. 每天核对后勾选“已核对”，再点击顶部“导出 Word”。七天都齐全后才能导出。

例如选择 2027 至 2028 学年、第二学期、第 7 周，将建议文件名：

`广东工业大学2027-2028学年第二学期第七周公共区域巡查汇总.docx`

图片预览支持放大、缩小、滚动以及 Ctrl + 滚轮缩放。拖动中间分隔条可调整宽度。点击“原文更正”可以粘贴微信原文重新提取字段。

## 识别及核对规则

- 只读取正文的 `部门：` 和 `姓名：`，不从群昵称推测身份；时间、范围和巡查情况不写入姓名栏。
- **OCR 可能识别错字，尤其是姓名生僻字。** 请使用原始截图，导出前逐字核对。没有警告也不代表识别完全正确。
- 多天组织和部门全称相同会提醒，比较时忽略空格；不同组织下同名部门不算重复。识别结束弹窗，手动修改实时更新，导出前可以返回检查或确认后继续。
- 修改文字或重新选图，会取消该天的“已核对”。已核对的行不会被批量识别覆盖。
- v1.0.1 起，PNG、JPG、BMP、GIF、TIFF 原文件直接嵌入 Word，不重新编码、不缩减像素，保留透明度和原文件数据。仅调整图片在表格中的显示尺寸，并关闭文档的自动图片压缩设置。不兼容的格式（如 WebP）会提示选择原始 PNG/JPG，不会静默转换。
- 七天截图放在一页横向表格中，页面上每张图显示较小。请放大 Word 页面查看细节；屏幕上文字小不等于原图被降像素。识别和软件预览使用的缩放副本不会用来导出。
- 不支持缺图或未巡查原因填写。
- 关闭前请先导出；当前不自动保存未导出的填写内容。
- 学年、学期、周次只用于文件名；学校固定为广东工业大学。结束年份需比开始年份大 1。

公开模板已去除原有聊天截图、真实姓名、作者和自定义文档属性，仅保留表格布局及无信息占位图。测试数据均为虚构。

## 从源码运行

推荐 **64 位 Python 3.12**，安装时保留 Tcl/Tk 和 Python Launcher。首次安装需要联网。

```powershell
git clone https://github.com/shoematedrzazgowskicwmsq6973-dotcom/campus-patrol-summary.git
cd campus-patrol-summary
.\install.cmd
.\start.cmd
```

或下载源码 ZIP，解压后双击 `install.cmd`，安装完成再双击 `启动巡查汇总.cmd`。安装器创建项目专用的 `.venv`，并验证离线 OCR 模型。不要从其他电脑复制 `.venv`，它依赖原来的安装位置。

如果已安装 Python 3.12 而没有 `py` 启动器，可手动运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe verify_install.py
.\.venv\Scripts\python.exe app.py
```

## 测试和构建

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe app_entry.py --self-test .\diagnostic\result.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_windows.ps1
```

构建结果位于 `dist/PatrolSummary`。完整目录才是可分发程序；发布 ZIP 前运行下面的打包后诊断，检查真实 OCR、预览切换、重复部门提醒和七图导出。诊断使用虚构截图并禁用进程网络连接。

```powershell
.\dist\PatrolSummary\PatrolSummary.exe --self-test .\diagnostic\packaged-result.json
```

第三方运行组件和模型的版权、许可证见程序包中的 `THIRD_PARTY_LICENSES`。本仓库当前未另行指定项目源码的开源许可证。
