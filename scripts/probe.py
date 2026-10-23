#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""局部放大 + ASCII 打印，用来人工核对某个符头到底是线音还是间音。

用法:
    python probe.py page-1.png 240 820 400 950                 # 出 crop.png
    python probe.py page-1.png 240 820 400 950 --scale 6       # 放大 6 倍
    python probe.py page-1.png 240 820 400 950 --ascii         # 直接打印字符画
    python probe.py page-1.png 240 820 400 950 --lines 529,544,559,574,589   # 画红线

为什么需要它：低分辨率扫描里「线音 / 间音」只差 7~8 个像素，模型看缩略图会看错；
把这一小块放大（或直接字符化）能一眼确认。字符画每行带原始 y 坐标，方便对谱线。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

CHARS = "#+. "  # <120 / <170 / <220 / else


def ascii_art(img: np.ndarray, max_cols: int = 110, y_offset: int = 0) -> str:
    h, w = img.shape
    step = max(1, w // max_cols)
    out = []
    for y in range(h):
        row = ""
        for x in range(0, w - step + 1, step):
            v = int(img[y, x:x + step].min())
            row += "#" if v < 120 else "+" if v < 170 else "." if v < 220 else " "
        out.append(f"{y + y_offset:4d} |{row}")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("x0", type=int)
    ap.add_argument("y0", type=int)
    ap.add_argument("x1", type=int)
    ap.add_argument("y1", type=int)
    ap.add_argument("--scale", type=float, default=4.0)
    ap.add_argument("--ascii", action="store_true")
    ap.add_argument("--lines", default="", help="谱线 y 坐标，逗号分隔；给了就画红线")
    ap.add_argument("--out", default="crop.png")
    args = ap.parse_args()

    im = Image.open(args.image).convert("L")
    box = (args.x0, args.y0, args.x1, args.y1)
    crop = ImageOps.autocontrast(im.crop(box), cutoff=1)
    if args.ascii:
        arr = np.array(crop)
        print(ascii_art(arr, y_offset=args.y0))
        return

    big = crop.resize((int(crop.width * args.scale), int(crop.height * args.scale)), Image.LANCZOS).convert("RGB")
    if args.lines:
        d = ImageDraw.Draw(big)
        for part in args.lines.split(","):
            try:
                y = float(part)
            except ValueError:
                continue
            yy = int((y - args.y0) * args.scale)
            if 0 <= yy < big.height:
                d.line([(0, yy), (big.width, yy)], fill=(255, 60, 60), width=1)
    big.save(args.out)
    print(f"{args.out}  {big.width}x{big.height}")


if __name__ == "__main__":
    main()
