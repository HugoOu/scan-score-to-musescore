#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 pdf_scan 的系统清单里检测符头并换算音高（半自动：结果需回图核对）。

用法:
    python pitchmap.py outdir --clef treble --key -1 [--x-min 200 --x-max 3400]
    python pitchmap.py outdir --clef bass  --key 0

输入:
    outdir/systems.json, outdir/page-*.png（pdf_scan.py 的产物）
输出:
    outdir/notes.json
    {
      "page":1, "clef":"treble", "key":-1,
      "systems":[{"index":1, "line_ys":[...], "notes":[
          {"x":251,"y":859.8,"step":-1,"pitch":"G5","midi":79}, ...],
        "gaps":[115,115,...]}]
    }

原理：谱线把纵向分成「线/间」，每 1/2 个线距 = 一个音级；符头是实心椭圆，
在列方向上是 8~26px 的连续暗段、且横向连续 6 列以上——比符干（3px 宽）和
谱线（1~2px 高）都「胖」，用这个连通段做检测，能绕开去谱线的麻烦。

注意：连音线里的空心符头（二分/全音符）只用轮廓，会被漏掉；装饰音、和弦、
多声部、跨谱表音符都会让结果变脏。脚本给的是候选，正确性靠 probe.py + 看图。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

DARK = 155
LETTERS = "CDEFGAB"
LETTER_IDX = {c: i for i, c in enumerate(LETTERS)}
SHARPS = "FCGDAEB"
FLATS = "BEADGCF"
# 高音谱表五条线（下→上）、低音谱表五条线
CLEF_LINES = {
    "treble": [("E", 4), ("G", 4), ("B", 4), ("D", 5), ("F", 5)],
    "bass": [("G", 2), ("B", 2), ("D", 3), ("F", 3), ("A", 3)],
}


def diatonic(letter: str, octave: int) -> int:
    return octave * 7 + LETTER_IDX[letter]


def from_diatonic(d: int) -> tuple[str, int]:
    return LETTERS[d % 7], d // 7


def key_alters(fifths: int) -> dict[str, int]:
    alt: dict[str, int] = {c: 0 for c in LETTERS}
    if fifths > 0:
        for c in SHARPS[:fifths]:
            alt[c] = 1
    elif fifths < 0:
        for c in FLATS[: -fifths]:
            alt[c] = -1
    return alt


def pitch_name(letter: str, octave: int, alt: int) -> str:
    return f"{letter}{'#' if alt > 0 else 'b' if alt < 0 else ''}{octave}"


def midi(letter: str, octave: int, alt: int) -> int:
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[letter]
    return 12 * (octave + 1) + base + alt


def refine_lines(img: np.ndarray, sysinfo: dict) -> list[float]:
    """用谱线附近几行的暗度重心把 5 条线定到亚像素。"""
    dark = (img < DARK).astype(float)
    out = []
    for y in sysinfo["line_ys"]:
        lo, hi = int(y) - 3, int(y) + 4
        seg = dark[lo:hi, :].sum(axis=1)
        if seg.sum() < 1:
            out.append(float(y))
            continue
        yy = np.arange(lo, hi)
        out.append(float((seg * yy).sum() / seg.sum()))
    return out


def detect_heads(img: np.ndarray, lines: list[float], x_min: int, x_max: int) -> list[dict]:
    dark = img < DARK
    h, w = dark.shape
    spacing = (lines[-1] - lines[0]) / 4.0
    run_min, run_max = max(5, int(0.35 * spacing)), int(1.15 * spacing)
    min_cols = max(5, int(0.35 * spacing))
    max_width = 1.6 * spacing
    y0 = max(0, int(lines[0] - 2.8 * spacing))
    y1 = min(h, int(lines[-1] + 1.6 * spacing))
    sub = dark[y0:y1, :]
    pts = []
    for x in range(x_min, min(x_max, w)):
        col = sub[:, x]
        y = 0
        while y < len(col):
            if col[y]:
                y2 = y
                while y2 + 1 < len(col) and col[y2 + 1]:
                    y2 += 1
                run = y2 - y + 1
                if run_min <= run <= run_max:
                    pts.append((x, y0 + (y + y2) / 2.0, run))
                y = y2 + 1
            else:
                y += 1
    pts.sort()
    clusters: list[list[tuple]] = []
    for x, y, run in pts:
        for c in clusters:
            if abs(c[-1][0] - x) <= 1 and abs(c[-1][1] - y) <= 4:
                c.append((x, y, run))
                break
        else:
            clusters.append([(x, y, run)])
    heads = []
    for c in clusters:
        xs = [p[0] for p in c]
        if len(c) >= min_cols and 6 <= max(xs) - min(xs) <= max_width:
            heads.append({"x": int(np.mean(xs)), "y": float(np.mean([p[1] for p in c]))})
    return heads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--clef", choices=["treble", "bass"], default="treble")
    ap.add_argument("--key", type=int, default=0, help="fifths：0=C, -1=F, 1=G ...")
    ap.add_argument("--pages", default="", help="只处理这些页，如 1,2；默认全部")
    ap.add_argument("--x-min", type=int, default=120)
    ap.add_argument("--x-max", type=int, default=10 ** 6)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    pages = json.loads((outdir / "systems.json").read_text(encoding="utf-8"))
    want = {int(p) for p in args.pages.split(",") if p.strip()} if args.pages else None
    alters = key_alters(args.key)
    top_letter, top_oct = CLEF_LINES[args.clef][-1]
    d_top = diatonic(top_letter, top_oct)

    result = []
    for pg in pages:
        if want and pg["page"] not in want:
            continue
        img = np.array(Image.open(outdir / pg["image"]).convert("L"))
        sys_out = []
        for s in pg["systems"]:
            lines = refine_lines(img, s)
            spacing = (lines[-1] - lines[0]) / 4.0
            heads = detect_heads(img, lines, args.x_min, args.x_max)
            notes = []
            for hd in heads:
                step = int(round((hd["y"] - lines[0]) / (spacing / 2.0)))
                letter, octave = from_diatonic(d_top - step)
                alt = alters[letter]
                notes.append({
                    "x": hd["x"],
                    "y": round(hd["y"], 1),
                    "step": step,
                    "pitch": pitch_name(letter, octave, alt),
                    "midi": midi(letter, octave, alt),
                })
            notes.sort(key=lambda n: n["x"])
            # 同一个符头常被拆成两三个簇：同音高且横向相距 < 1.2 个线距就合并
            merged = []
            for n in notes:
                if merged and n["x"] - merged[-1]["x"] <= 1.2 * spacing:
                    continue  # 同一符头/装饰音造成的重复簇
                merged.append(n)
            notes = merged
            gaps = [notes[i + 1]["x"] - notes[i]["x"] for i in range(len(notes) - 1)]
            sys_out.append({
                "index": s["index"],
                "line_ys": [round(v, 2) for v in lines],
                "spacing": round(spacing, 2),
                "notes": notes,
                "gaps": gaps,
            })
            print(f"page {pg['page']} system {s['index']}: {len(notes)} 个候选符头", flush=True)
        result.append({
            "page": pg["page"], "image": pg["image"],
            "clef": args.clef, "key": args.key, "systems": sys_out,
        })

    (outdir / "notes.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(outdir / "notes.json")


if __name__ == "__main__":
    main()
