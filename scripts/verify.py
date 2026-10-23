#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编译 + 出图 + 体检：把 MusicXML 交给 MuseScore 无头排版，并打印可核对的元数据。

用法:
    python verify.py score.musicxml outdir [--dpi 130] [--pdf]

做的事:
  1) musicxml -> mscz（mscore.py convert，自带 magic bytes 校验）
  2) mscz -> pdf（--pdf 时）
  3) mscz -> PNG（--dpi）
  4) 打印 meta：页数、小节数、调号、拍号、速度、和弦数

验收标准（缺一不算完成）:
  * 全部输出都是 OK（没有 BAD / 0 字节）
  * 页数、小节数与预期一致
  * 打开 PNG 逐行看图：音符、休止、延音线、和弦符号、反复/房子/D.S. 是否与源谱一致
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_MSCORE = Path(os.path.expanduser(r"~\.dsh\skills\musescore-score\scripts\mscore.py"))


def run(mscore: Path, *args: str) -> None:
    r = subprocess.run([sys.executable, str(mscore), *args])
    if r.returncode != 0:
        sys.exit(f"mscore.py {' '.join(args)} 失败（退出码 {r.returncode}）")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("musicxml")
    ap.add_argument("outdir")
    ap.add_argument("--dpi", type=int, default=130)
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--mscore", default=str(DEFAULT_MSCORE))
    args = ap.parse_args()

    mscore = Path(args.mscore)
    if not mscore.exists():
        sys.exit(f"找不到 mscore.py: {mscore}（先装 musescore-score 技能，或 --mscore 指定路径）")
    src = Path(args.musicxml).resolve()
    out = Path(args.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    mscz = out / (src.stem + ".mscz")

    run(mscore, "convert", str(src), str(mscz))
    if args.pdf:
        run(mscore, "convert", str(mscz), str(out / (src.stem + ".pdf")))
    run(mscore, "render", str(mscz), "--dpi", str(args.dpi))

    meta = subprocess.run([sys.executable, str(mscore), "meta", str(mscz)],
                          capture_output=True, text=True)
    try:
        data = json.loads(meta.stdout)
    except Exception:
        print(meta.stdout)
        sys.exit("meta 输出不是 JSON")
    data = data.get("metadata", data)  # mscore.py meta 的 JSON 外面套了一层 metadata

    print("\n== 体检 ==")
    print(f"页数     : {data.get('pages')}")
    print(f"小节数   : {data.get('measures')}")
    print(f"调号     : {data.get('keysig')} (fifths)")
    print(f"拍号     : {data.get('timesig')}")
    print(f"速度     : {data.get('tempo')}")
    parts = data.get("parts", [])
    print(f"乐器     : {[p.get('name') for p in parts]}")
    print(f"和弦符号 : {sum(int(p.get('harmonyCount', 0)) for p in parts)}")
    pngs = sorted(out.glob(src.stem + "-*.png"))
    print(f"预览图   : {[p.name for p in pngs]}")
    print("\n下一步：用 read_image 打开预览图，逐行核对音符/节奏/记号，再决定改哪里。")


if __name__ == "__main__":
    main()
