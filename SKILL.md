---
name: scan-score-to-musescore
description: 把扫描件或位图 PDF 五线谱转成可编辑的 MuseScore 谱：抽原生位图、拟合五线谱与小节、按符头位置换算音高、按横向间距判节奏，生成 MusicXML 后无头排版并回图逐行核对。当用户给五线谱图片/PDF 说“识谱”“转成 MuseScore”“重新排版”“补成完整谱”时使用；矢量 PDF 直接解析、简谱、密集和弦/多声部总谱不适用。
---

# 扫描谱 → MuseScore（半自动识谱）

## 目的与边界

产出物是**可编辑的 MuseScore 工程 + 打印谱**：把一张/几张五线谱扫描图变成 `.musicxml → .mscz → .pdf/.png/.mp3`。

这是**半自动**流程：脚本负责“几何”——找五线谱行、找符头、按谱线换算音高；**节奏、连音线、装饰音、反复结构必须人（模型）看图确认**。不要把它当成通用 OMR：单声部旋律/lead sheet 效果最好，钢琴双声部、和弦密集、总谱请直接说明做不到或只做草稿。

排版/导出那半段复用 `musescore-score` 技能：本技能只负责“图 → MusicXML”，之后交给 `mscore.py`。两个技能建议一起装。

## 前置条件

- **MuseScore 4** 与本机可用的 `mscore.py`（`~/.dsh/skills/musescore-score/scripts/mscore.py`）。找不到就停下告诉用户装什么，别硬跑。
- **Python 3.10+**，需要 `numpy`、`Pillow`（DSH 自带的 python 里都有）。
- **poppler**：`pdftoppm` / `pdfimages` / `pdfinfo`。Windows 上 TeX Live 自带（`C:\texlive\*\bin\windows\`），脚本会自动去那里找；实在没有就让用户先把 PDF 导出成 PNG。
- 源文件最好是 **≥150 dpi 的灰度/黑白扫描**。低于 100 dpi 的整页缩略图基本没法识谱，直接说明。

## 流程

工作目录约定：`<工作目录>/<曲名>/`，下面放 `pages/`（抽出的页图）、`notes.json`、`score.json`、`.musicxml/.mscz/.pdf`。别把几十张中间图摊在仓库根目录。

### 1. 抽页 + 找五线谱行

```powershell
& $PY scripts/pdf_scan.py 谱.pdf 曲名/pages
```

看两个输出：

- `system.json` 里每页 `systems` 数量对不对（对照原图数一下有几行谱）；
- stderr 里的分辨率提示。**位图 PDF 会自动抽原生图**（`pdfimages -all`），不会按 dpi 放大——这是关键，低分辨率扫描放大只会更糊。

如果 `systems` 数量明显不对（少了/多了），先别往下走：多半是页面倾斜、双谱表粘连或扫描噪声。用 `probe.py` 看整页局部，必要时先裁掉页眉/边框再跑。

### 2. 确认谱号、调号、拍号

脚本不会认谱号。打开页面原图（或 `probe.py` 裁左上角放大）确认：

- 谱号：高音 `--clef treble`，低音 `--clef bass`（目前只支持这两种）；
- 调号：数升降号 → `--key`（0=C，-1=F，1=G，2=D，-2=Bb…）；
- 拍号与速度：记下来，后面写进 `score.json`。

### 3. 检符头、算音高（只得到候选）

```powershell
& $PY scripts/pitchmap.py 曲名/pages --clef treble --key -1 --x-min 200
```

`--x-min` 用来跳过谱号/调号区域（先看 `probe.py` 里谱号占多少像素）。输出 `notes.json`：每个系统一串 `{x, y, pitch}` 和相邻间距 `gaps`。

**这一步的产出必须当“候选”用**：实心符头识别率约 85–95%，空心符头（二分/全音符）基本识别不到，装饰音、和弦、跨谱表音符会出错。漏检比错检更常见。

### 4. 逐小节核对（最花时间，也决定成败）

两种核对手段：

```powershell
# 放大看：出来一张 crop.png，用 read_image 打开
& $PY scripts/probe.py pages/page-1.png 240 820 420 950 --scale 5 --lines 529,544,559,574,589

# 字符画：精确到像素，用来判断“线音还是间音”
& $PY scripts/probe.py pages/page-1.png 240 820 420 950 --ascii
```

字符画里 `#` 是墨、`.` 是浅灰，左边是**原始 y 坐标**；照着 `systems.json` 里的 5 条谱线 y 值数格子：线到相邻间差半个线距（spacing/2），音高就确定了。低分辨率下模型看缩略图会把相邻的线/间看错，**有疑问就 `--ascii`，不要猜**。

把核对结果写成逐小节 JSON（模板：`assets/example_score.json`），一个小节的 events 拍数必须正好等于拍号分子：

```json
{"chord": "Dm", "events": [["F5", 0.5], ["D5", 0.5], ["A5", 1.5], ["F5", 0.5]]}
```

节奏判定（3/4 为例，一拍≈小节宽/3）：

- 相邻音间距 ≈ 1 拍 → 四分；≈ 0.5 拍 → 八分（通常有符杠）；≈ 1.5 拍 → 附点四分；
- 小节开头没音 → 补 `["R", n]`；音符后面的空隙用休止补齐；
- 附点、连音线、装饰音只在放大图上能看到，逐个补。

### 5. 生成 MusicXML

```powershell
& $PY scripts/score_from_json.py 曲名/score.json 曲名/曲名.musicxml
```

支持：和弦符号、拍内换和弦（`chord_changes`）、反复、1./2. 房子、Segno/Coda、D.S. al Coda、多小节休止、延音线（event 第三项 `tie_start`/`tie_stop`）、排练记号、强制换行/换页、终止线。全部 key 见文件头 docstring。

结构不确定时**先按原谱写标记，不要自己展开反复**；展开会让打印谱和原谱对不上。

### 6. 编译、看图、迭代

```powershell
& $PY scripts/verify.py 曲名/曲名.musicxml 曲名/out --pdf --dpi 130
```

然后**一定要用 `read_image` 打开 PNG 逐行看**：MuseScore 遇到不合法 MusicXML 不报错，只会静默丢内容。检查：音符对不对、休止位置、延音线成对、和弦符号有没有挤、反复/房子/D.S. 有没有渲染出来、有没有整行空白。

改 JSON → 重跑第 5、6 步，直到图和原谱对得上。验收 = 全部 OK + meta 数字对 + 图对，三者缺一不算完成。

## 压成一页 A4（用户常要）

MuseScore 默认会把 40~50 小节排成 3 页。要一页：

1. 在 `score.json` 里去掉 `page_break`，保留每 4 小节一个 `system_break`（或干脆不加）；
2. 编译出 `.mscz` 后改 `score_style.mss`（`.mscz` 是 zip）：`<spatium>1.3</spatium>`、页边距 `0.45/0.42/0.35` 英寸、`<minSystemDistance>6</minSystemDistance>`、`<maxSystemDistance>18</maxSystemDistance>`、`<enableVerticalSpread>1</enableVerticalSpread>`；
3. 重新 render 检查页数 = 1，再打开看字号是否还能读（spatium < 1.2 一般就偏小了）。

做法：编出 `.mscz` 后改 zip 里的 `score_style.mss`（`<spatium>`、页边距、`minSystemDistance`、`enableVerticalSpread`），再 render 确认页数；具体键值见 `references/notation-mapping.md` 第 6 节。

## 坑（每条都踩过）

- **把 72 dpi 扫描按 300 dpi 渲染**：得到 4 倍大的糊图，符头连成一片，检测反而更差。先用 `pdfimages -list` 看原生宽度，按原生像素处理。
- **检测阈值写死像素**：符头高度、符杠厚度都和线距成正比。按 `spacing` 取相对值（符头高 ≈ 0.3–1.15×spacing，簇宽 ≤ 1.6×spacing），换一张扫描件就要重调。
- **和弦符号/歌词/谱号被当成符头**：`--x-min` 跳谱号区；和弦文字在谱线上方 3–4 个线距，`y` 窗口别放太宽。
- **多小节休止**：一根粗横杠既不是符头也不是休止符，会被检成一堆假音；那段直接手写 `multi_rest`。
- **空心符头漏检**：二分/全音符只有轮廓，列扫描抓不到，靠看图补。
- **拍数不齐**：一个小节 events 之和 ≠ 拍号，MuseScore 会从下一小节开始整体错位，而且不报错。生成后一定核对每小节。
- **同一个符头被拆成 2–3 个簇**：装饰音、升降号、符杠都会造成，按“同 x 距离 < 1.2×spacing 只留一个”合并。
- **反复/房子跨系统**：1 房子跨小节时，`ending1_start` 放第一小节、`ending1_stop` 放最后一小节；房子与 `repeat_end` 的顺序影响播放，打印不受影响。
- **`read_image` 的分辨率会骗人**：低 DPI 下相邻三度会糊成黑块，看着像错音。先 `--dpi 300` 重渲染或 `probe.py` 放大确认再改。

## 失败处理

- 同一处连续改两次还不对：退回最小可编译片段（1 小节 1 个音）确认链路通，再逐步加回。
- 扫描质量太差（<100 dpi、页面倾斜 >3°、五线谱粘连）：停下说明“这份图不适合自动识谱”，给出可行替代（重扫 300 dpi、或用户提供 MusicXML/MIDI）。
- 三次仍不通：报告卡在哪一步、`systems.json` 片段、最后一份可编译文件路径。

## 资源

- `scripts/pdf_scan.py`：PDF/图片 → 每页 PNG + 系统清单（优先抽原生位图）。
- `scripts/pitchmap.py`：符头检测 + 音高换算（候选，需人工核对）。
- `scripts/probe.py`：局部放大 / ASCII 字符画，核对线音与间音。
- `scripts/score_from_json.py`：逐小节 JSON → MusicXML（和弦/房子/D.S./反复/多小节休止）。
- `scripts/mxml.py`：自带的最小 MusicXML 写出器（无第三方依赖）。
- `scripts/mxml_ext.py`：给 `mxml` 补和弦符号/房子/D.S./反复等记谱元素（被 `score_from_json.py` 调用）。
- `scripts/verify.py`：编译 + 出图 + meta 体检。
- `assets/example_score.json`：可直接跑通的 `score.json` 模板。
- `references/notation-mapping.md`：坐标→音高的数学、调号拼写、节奏判定细则、MusicXML 注入片段。
