# scan-score-to-musescore

把**扫描件 / 位图 PDF 五线谱**变成**可编辑的 MuseScore 工程**的半自动工具链。

不是通用 OMR：脚本负责几何（找五线谱、找符头、按谱线换算音高），节奏、连音线、装饰音、反复结构由人（或 AI agent）看图确认。目标是让「一张扫描谱 → 可编辑乐谱」这件事从几小时手工打谱变成十几分钟校对。

```
 PDF/图片 ──pdf_scan──▶ 每页 PNG + 五线谱行坐标
                             │
                     pitchmap│  符头检测 → 音高候选
                             ▼
                     逐小节 JSON（人工核对节奏/记号）
                             │
                  score_from_json│  MusicXML（和弦/房子/D.S./反复）
                             ▼
                  MuseScore CLI ──▶ .mscz / .pdf / .png / .mp3
```

## 快速开始

依赖：Python 3.10+、`numpy`、`Pillow`、[poppler](https://poppler.freedesktop.org/)（`pdftoppm` / `pdfimages` / `pdfinfo`），以及 [MuseScore 4](https://musescore.org/)（用于排版导出）。

```bash
# 1. 抽页 + 找五线谱行（位图 PDF 会自动抽原生图，不做无意义放大）
python scripts/pdf_scan.py 谱.pdf work

# 2. 检符头、算音高（候选）
python scripts/pitchmap.py work --clef treble --key -1 --x-min 200

# 3. 局部放大 / 字符画，用来核对“线音还是间音”
python scripts/probe.py work/page-1.png 240 820 420 950 --scale 5 --lines 529,544,559,574,589
python scripts/probe.py work/page-1.png 240 820 420 950 --ascii

# 4. 按小节整理成 JSON（模板见 assets/example_score.json），生成 MusicXML
python scripts/score_from_json.py my_score.json out.musicxml

# 5. 交给 MuseScore 排版 + 出图体检
python scripts/verify.py out.musicxml build --pdf --dpi 130
```

`verify.py` 默认调用 DSH 的 `mscore.py`（`~/.dsh/skills/musescore-score/scripts/mscore.py`），可以用 `--mscore PATH` 指向自己的封装；没有封装也可以直接：

```bash
musescore4 -o out.mscz out.musicxml
musescore4 -o out.pdf out.mscz
```

## 它解决的具体问题

| 问题 | 做法 |
|---|---|
| 扫描 PDF 里其实是 72 dpi 位图，按 300 dpi 重渲染只会更糊 | `pdfimages -all` 抽原生图；只有矢量 PDF 才走 `pdftoppm` |
| 符头高度、符杠厚度随扫描分辨率变化，写死像素阈值换张图就崩 | 全部阈值按谱线间距 `spacing` 取相对值 |
| 符头和谱线粘在一起，去除谱线又会破坏符头 | 用「列方向 8~26 px 连续暗段 + 横向 ≥6 列」当符头特征，不做形态学去线 |
| 低分辨率下“线音/间音”只差 7 px，看图容易错 | `probe.py --ascii` 输出带原始 y 坐标的字符画，直接数格子 |
| MusicXML 里房子、D.S.、Coda、拍内换和弦没有现成封装 | `mxml_ext.py` 按正确元素顺序注入，MuseScore 能正确渲染 |

## 目录

```
scripts/pdf_scan.py        PDF/图片 → 每页 PNG + systems.json（原生位图优先）
scripts/pitchmap.py        符头检测 + 音高换算 → notes.json（候选，需人工核对）
scripts/probe.py           局部放大 / ASCII 字符画 / 谱线标尺
scripts/score_from_json.py 逐小节 JSON → MusicXML
scripts/mxml.py            自带的最小 MusicXML 写出器（无第三方依赖）
scripts/mxml_ext.py        和弦符号 / 房子 / D.S. / Coda / 反复 的 MusicXML 注入
scripts/verify.py          编译 + 出图 + meta 体检
references/notation-mapping.md  坐标→音高数学、调号拼写、节奏判定、记号对照表
assets/example_score.json  可直接跑通的 JSON 模板
SKILL.md                   作为 DeepSeek Harness 技能使用时的入口说明
```

## 作为 DSH 技能使用

把整个目录放到 `~/.dsh/skills/scan-score-to-musescore/`（或以 `SKILL.md` 为入口安装），之后说「把这张谱转成 MuseScore」「识谱」就会触发；也可以 `/scan-score-to-musescore` 显式调用。

## 边界（请先读）

- **适合**：单声部旋律 / lead sheet / 独奏谱，扫描 ≥150 dpi，五线谱不倾斜。
- **勉强**：和弦较多的钢琴谱（能出草稿，但需要逐小节改）。
- **不适合**：总谱、双声部对位、简谱、手写谱、<100 dpi 的缩略图。
- 空心符头（二分/全音符）基本检不到；装饰音、连音线、圆滑线需要手工补。
- 没有训练模型、没有训练数据——全部是几何启发式，所以体积小、可解释、可调试。

## 版权与合法使用

**这个仓库只包含工具代码，不包含任何乐谱、扫描件或生成结果。** 请只处理你拥有版权或已获授权、或属于公有领域的乐谱；扫描/转写受版权保护的作品并公开分发，可能构成侵权（各司法辖区规定不同）。工具作者不对使用者的输入与输出主张任何权利，也不承担相关责任。详见 [LICENSE](LICENSE) 与下方说明。

## License

MIT —— 见 [LICENSE](LICENSE)。

第三方：poppler（GPL，仅作为外部可执行文件调用，不链接）、MuseScore（GPL，同样只调用命令行）、NumPy/Pillow（BSD 系）。本仓库不重新分发它们。
