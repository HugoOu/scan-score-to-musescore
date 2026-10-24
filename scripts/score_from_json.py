#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「逐小节的 JSON」写成 MusicXML（含和弦符号、房子、D.S./Coda、反复、多小节休止）。

用法:
    python score_from_json.py score.json out.musicxml

JSON 结构（最小可用）:
{
  "title": "示例：小步舞", "subtitle": "score_from_json.py 的最小示例",
  "composer": "DSH", "lyricist": "",
  "key": -1, "time": [3, 4], "tempo": 120,
  "instrument": {"name": "Flute", "program": 74},
  "sections": [
    {"name": "Intro", "system_break": true, "measures": [
        {"multi_rest": 3, "marks": ["rehearsal:Intro"], "events": [["R", 3]]},
        {"events": [["R", 1], ["R", 1], ["F5", 0.5], ["G5", 0.5]]}
    ]},
    {"name": "A", "measures": [
        {"chord": "C", "events": [["G5", 1], ["C6", 1], ["G5", 1]],
         "marks": ["rehearsal:A", "repeat_start", "segno"]},
        {"chord": "Gm", "chord_changes": [[2.0, "C"]],
         "events": [["G5", 1.5], ["G5", 0.5], ["F5", 1]]},
        {"chord": "F", "events": [["F5", 3, "tie_start"]]}
    ]}
  ]
}

约定:
* events 里 ["R", 拍数] 是休止；["F5", 拍数] 是音符；第三项 "tie_start"/"tie_stop" 加延音线。
* 拍数单位是四分音符：1=四分，0.5=八分，1.5=附点四分，2=二分，3=附点二分。
* 一个小节内所有 events 的拍数之和必须等于拍号分子（4/4 时是 4），否则 MuseScore 会静默错位。
* marks 可选项见下方 MARKS；"rehearsal:X" 是排练记号，X 任意文字。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mxml_ext import (  # noqa: E402
    coda_xml, ending_start, ending_stop, extra, harmony_xml, repeat_end,
    repeat_start, segno_xml, words_xml,
)
import mxml  # noqa: E402

MARK_HELP = "rehearsal:*, repeat_start, repeat_end, segno, coda, to_coda, ds_al_coda, " \
            "ending1_start, ending1_stop, ending2_start, ending2_stop, " \
            "system_break, page_break, final_bar"


def add_marks(m, marks: list[str]) -> None:
    for mk in marks:
        if mk.startswith("rehearsal:"):
            m.mark(mk.split(":", 1)[1])
        elif mk == "repeat_start":
            extra(m, repeat_start())
        elif mk == "repeat_end":
            extra(m, repeat_end())
        elif mk == "segno":
            extra(m, segno_xml())
        elif mk == "coda":
            extra(m, coda_xml())
        elif mk == "to_coda":
            extra(m, words_xml("To Coda", placement="below", italic=True))
        elif mk == "ds_al_coda":
            extra(m, words_xml("D.S. al Coda", placement="below", italic=True))
        elif mk == "ending1_start":
            extra(m, ending_start(1))
        elif mk == "ending1_stop":
            extra(m, ending_stop(1))
        elif mk == "ending2_start":
            extra(m, ending_start(2))
        elif mk == "ending2_stop":
            extra(m, ending_stop(2))
        elif mk == "system_break":
            m.system_break()
        elif mk == "page_break":
            m.page_break()
        elif mk == "final_bar":
            m.barlines.append("light-heavy")
        else:
            raise SystemExit(f"未知 mark: {mk}（可用：{MARK_HELP}）")


def build(data: dict) -> mxml.Score:
    inst = data.get("instrument", {"name": "Flute", "program": 74})
    score = mxml.Score(
        title=data.get("title", "Untitled"),
        composer=data.get("composer", ""),
        subtitle=data.get("subtitle", ""),
        key=int(data.get("key", 0)),
        time=tuple(data.get("time", [4, 4])),
        tempo=data.get("tempo"),
    )
    part = score.add_part(inst.get("name", "Flute"), program=int(inst.get("program", 74)))
    multi_rest_measures: list[int] = []

    for sec in data.get("sections", []):
        if sec.get("page_break"):
            pass  # 由首小节 marks 控制
        for meas in sec.get("measures", []):
            m = part.add_measure()
            if meas.get("chord"):
                extra(m, harmony_xml(meas["chord"]))
            for change in meas.get("chord_changes", []):
                beat, ch = change
                extra(m, harmony_xml(ch, offset=int(round(float(beat) * 8))))
            add_marks(m, meas.get("marks", []))
            if meas.get("multi_rest"):
                m.attributes.append(
                    f'<measure-style><multiple-rest>{int(meas["multi_rest"])}</multiple-rest></measure-style>')
                multi_rest_measures.append(m.number)
            notes = []
            for ev in meas.get("events", [["R", 3]]):
                pitch, beats = ev[0], float(ev[1])
                tie = ev[2] if len(ev) > 2 else None
                if pitch.upper() in ("R", "REST"):
                    n = m.rest(beats)
                else:
                    n = m.note(pitch, beats)
                if tie:
                    n.tie = tie
                notes.append(n)
            if meas.get("fermata") and notes:
                notes[-1].fermata = True
    return score


def postprocess(xml: str, multi_rest_measures: list[int]) -> str:
    """mxml 写不出 <rest measure=\"yes\"/>：这里按小节号补上，MuseScore 才会当整小节休止。"""
    if not multi_rest_measures:
        return xml
    parts = xml.split("<measure ")
    out = [parts[0]]
    for seg in parts[1:]:
        mnum = int(re.match(r'number="(\d+)"', seg).group(1))
        if mnum in multi_rest_measures:
            seg = seg.replace("<rest/>", '<rest measure="yes"/>')
        out.append(seg)
    return "<measure ".join(out)


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    score = build(data)
    xml = score.to_xml()
    mr = [m.number for p in score.parts for m in p.measures
          if any("multiple-rest" in a for a in getattr(m, "attributes", []))]
    xml = postprocess(xml, mr)
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(xml, encoding="utf-8", newline="\n")
    print(f"wrote {sys.argv[2]}（{sum(len(p.measures) for p in score.parts)} 小节）")


if __name__ == "__main__":
    main()
