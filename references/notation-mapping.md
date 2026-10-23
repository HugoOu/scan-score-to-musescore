# 坐标 → 音高 → MusicXML：换算与记谱细节

## 1. 谱线到音高

一行五线谱有 5 条线，线距 `spacing`（`systems.json` 里有）。相邻「线—间—线」是半个 `spacing`，也就是一个音级：

```
step = round((y_head - y_top_line) / (spacing / 2))
```

`step = 0` 是最高那条线上的音，正数往下（音变低），负数往上（加线）。

各谱号最上面一条线的音：

| 谱号 | 五条线（下→上） | 最高线 |
|---|---|---|
| 高音 treble | E4 G4 B4 D5 F5 | F5 |
| 低音 bass | G2 B2 D3 F3 A3 | A3 |

往下推音级：把自己当成音名序列 CDEFGAB 循环，`diatonic = octave*7 + letter_index`，`letter_index: C=0 D=1 E=2 F=3 G=4 A=5 B=6`。

```
d_top = octave*7 + idx(最高线音名)      # F5 -> 5*7+3 = 38
d_note = d_top - step
letter = "CDEFGAB"[d_note % 7]; octave = d_note // 7
```

## 2. 调号拼写

`--key` 用 fifths：`-1` 是 F 大调（一个降号），`1` 是 G 大调（一个升号）。

- 升号顺序 `F C G D A E B`，fifths=+n 时前 n 个音升半音；
- 降号顺序 `B E A D G C F`，fifths=-n 时前 n 个音降半音。

F 大调里所有 B 都写成 `Bb`；G 大调里所有 F 都写 `F#`。扫描谱上印的临时记号（还原号、额外升降）脚本不会认，需要人工在 JSON 里写 `F#5`、`Bb4` 这种拼写。

## 3. 节奏判定

先定「拍宽」：小节线位置差 / 每小节拍数。没有可靠小节线时，用「同一系统里四分音符的典型间距」当拍宽（选出现次数最多的间距，通常 100~130 px @150dpi）。

| 横向间距 / 拍宽 | 时值（拍） | JSON |
|---|---|---|
| ≈ 1.0 | 1（四分） | `1` |
| ≈ 0.5 | 0.5（八分） | `0.5` |
| ≈ 1.5 | 1.5（附点四分） | `1.5` |
| ≈ 2.0 | 2（二分） | `2` |
| ≈ 0.25 | 0.25（十六分） | `0.25` |

- 符杠（beam）连接的一组音都是八分或更短；
- 音符右侧、谱线间的小点是附点，不是跳音；音符**上方/下方**的小点才是跳音；
- 小节开头的空白用 `["R", n]` 补，音符之间的空隙同理；
- 跨小节的音用 `tie_start`/`tie_stop`，圆滑线（slur）脚本不支持，需要手写 `<slur>`。

校验：每小节 `sum(events 拍数) == time[0] * (4 / time[1])`（3/4 时 = 3，4/4 时 = 4）。不相等 MuseScore 会静默错位。

## 4. score.json 里没有、需要手写的记号

`score_from_json.py` 覆盖了常用结构记号；下面这些要直接改 MusicXML 或 `.mscz`：

```xml
<!-- 圆滑线：第一个音 start，最后一个音 stop -->
<notations><slur type="start" number="1"/></notations>

<!-- 装饰音（回音/波音）：MuseScore 认 <ornaments> -->
<notations><ornaments><turn/></ornaments></notations>

<!-- 力度 -->
<direction placement="below"><direction-type><dynamics><mp/></dynamics></direction-type></direction>

<!-- 渐强/渐弱 -->
<direction placement="below"><direction-type><wedge type="crescendo"/></direction-type></direction>
```

MusicXML 的元素顺序很挑：`<note>` 里必须是 `pitch → duration → tie → voice → type → dot → accidental → notations → staff`。顺序错了 MuseScore 不报错但会丢记号。`mxml_ext.py` 的注入片段已经按正确顺序排好，照抄即可。

## 5. 结构记号怎么落

| 原谱记号 | JSON marks | 生成的 MusicXML |
|---|---|---|
| `‖:` | `repeat_start` | `<barline location="left"><repeat direction="forward"/></barline>` |
| `:‖` | `repeat_end` | 同上 `backward` |
| `1.` 房子开始/结束 | `ending1_start` / `ending1_stop` | `<ending number="1" type="start\|stop"/>` |
| `2.` 房子 | `ending2_start` / `ending2_stop` | 同上 number=2 |
| Segno 𝄋 | `segno` | `<direction><segno/></direction>` |
| Coda ⊕ | `coda` | `<direction><coda/></direction>` |
| to Coda | `to_coda` | 文字 "To Coda"（斜体，谱表下方） |
| D.S. al Coda | `ds_al_coda` | 文字 "D.S. al Coda" |
| 排练记号 A/B | `rehearsal:A` | `<rehearsal>A</rehearsal>` |
| 3 小节休止 | `multi_rest: 3` | `<measure-style><multiple-rest>3</multiple-rest>` + `rest measure="yes"` |
| 终止线 | `final_bar` | `<bar-style>light-heavy</bar-style>` |

注意：这些是**打印记号**。MuseScore 播放时不会自动按 D.S. 跳转（需要 `<sound dacapo="yes"/>` 之类），要试听完整结构得展开反复或补 sound 指令——打印谱不需要。

## 6. 一页 A4 的样式参数

`.mscz` 是 zip，里面 `score_style.mss` 是 XML：

```xml
<spatium>1.3</spatium>                     <!-- 线距 mm，1.76 是默认；<1.2 会太小 -->
<pageEvenLeftMargin>0.45</pageEvenLeftMargin>   <!-- 英寸 -->
<pageEvenTopMargin>0.42</pageEvenTopMargin>
<pageEvenBottomMargin>0.35</pageEvenBottomMargin>
<minSystemDistance>6</minSystemDistance>        <!-- 系统间距 mm -->
<maxSystemDistance>18</maxSystemDistance>
<enableVerticalSpread>1</enableVerticalSpread>  <!-- 0=顶部堆叠，1=纵向铺满 -->
```

经验值：A4 一页、单声部、4 小节/行，`spatium 1.3` 能放下约 50 小节（14 行）；再密就得降到 1.2 并去掉结尾休止小节。
