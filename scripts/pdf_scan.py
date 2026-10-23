#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF / 图片 → 每页 PNG + 五线谱系统清单。

用法:
    python pdf_scan.py 谱.pdf outdir              # 位图 PDF 自动抽原生图；矢量 PDF 按 150dpi 渲染
    python pdf_scan.py 谱.pdf outdir --dpi 300    # 矢量 PDF 渲染 dpi
    python pdf_scan.py 扫描页.png outdir

输出:
    outdir/page-1.png ...
    outdir/systems.json = [
      {"page":1, "image":"page-1.png", "width":.., "height":..,
       "systems":[{"index":1,"line_ys":[..5 个..],"spacing":15.2,
                   "top":..,"bottom":..}]}
    ]

关键：扫描件 PDF 的内嵌位图往往只有 72~150 dpi，把它按 300 dpi 重新渲染只会得到
更糊的放大图。本脚本优先用 pdfimages 抽原生位图；只有矢量 PDF 才走 pdftoppm。

依赖：标准库 + numpy + Pillow；PDF 需要 poppler 的 pdfimages/pdftoppm/pdfinfo。
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

DARK = 155  # 灰度阈值：< DARK 视为墨


def find_exe(name: str) -> str | None:
    p = shutil.which(name)
    if p:
        return p
    for pat in (rf"C:\texlive\*\bin\windows\{name}.exe",
                rf"C:\Program Files\poppler*\bin\{name}.exe",
                rf"C:\Program Files\*\bin\{name}.exe"):
        hits = glob.glob(pat)
        if hits:
            return sorted(hits)[-1]
    return None


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def pdf_native_images(pdf: Path, outdir: Path) -> list[Path] | None:
    """扫描件 PDF：一页一张位图 -> 直接抽出原图。不适用时返回 None。"""
    exe = find_exe("pdfimages")
    info = find_exe("pdfinfo")
    if not exe or not info:
        return None
    try:
        listing = run([exe, "-list", str(pdf)]).stdout
        meta = run([info, str(pdf)]).stdout
    except Exception:
        return None

    per_page: dict[int, list[int]] = {}
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].isdigit():
            per_page.setdefault(int(parts[0]), []).append(int(parts[3]))
    if not per_page or any(len(v) != 1 for v in per_page.values()):
        return None

    page_sizes = [ln for ln in meta.splitlines() if ln.startswith("Page size")]
    if not page_sizes:
        return None
    page_w = float(page_sizes[0].split()[2])
    if any(v[0] > page_w * 1.15 for v in per_page.values()):
        return None  # 大图 = 高清扫描或矢量导出，交给 pdftoppm

    run([exe, "-all", str(pdf), str(outdir / "native")])
    files = sorted(outdir.glob("native-*"))
    pages = []
    for i, f in enumerate(files, 1):
        dst = outdir / f"page-{i}.png"
        Image.open(f).convert("L").save(dst)
        f.unlink()
        pages.append(dst)
    return pages


def pdf_to_png(pdf: Path, outdir: Path, dpi: int) -> list[Path]:
    exe = find_exe("pdftoppm")
    if not exe:
        sys.exit("找不到 pdftoppm（poppler）。Windows 可装 TeX Live / poppler，或先把 PDF 导出成 PNG 再跑本脚本。")
    run([exe, "-png", "-r", str(dpi), str(pdf), str(outdir / "page")])
    return sorted(outdir.glob("page-*.png"))


def native_resolution_note(pdf: Path) -> None:
    exe = find_exe("pdfimages")
    if not exe:
        return
    try:
        listing = run([exe, "-list", str(pdf)]).stdout
    except Exception:
        return
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].isdigit():
            w = int(parts[3])
            if w < 1200:
                print(f"[注意] 内嵌位图仅 {w}px 宽 —— 低分辨率扫描。不要靠提高 dpi 求清晰度，"
                      f"按原生像素识谱，并接受个别符头需要人工确认。", file=sys.stderr)
            return


def line_groups(dark_frac: np.ndarray) -> list[float]:
    rows = np.where(dark_frac > 0.45)[0]
    groups: list[list[int]] = []
    for r in rows:
        if groups and r - groups[-1][-1] <= 2:
            groups[-1].append(int(r))
        else:
            groups.append([int(r)])
    return [float(np.mean(g)) for g in groups]


def find_systems(img: np.ndarray) -> list[dict]:
    h, w = img.shape
    dark = img < DARK
    lines = line_groups(dark.sum(axis=1) / w)
    systems, i = [], 0
    while i + 4 < len(lines):
        ys = lines[i:i + 5]
        spac = np.diff(ys)
        if 6 <= spac.min() and spac.max() <= 40 and spac.max() - spac.min() <= 3:
            systems.append({
                "index": len(systems) + 1,
                "line_ys": [round(float(y), 2) for y in ys],
                "spacing": round(float(spac.mean()), 2),
                "top": round(float(ys[0] - 2 * spac.mean()), 1),
                "bottom": round(float(ys[-1] + 2 * spac.mean()), 1),
            })
            i += 5
        else:
            i += 1
    return systems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="PDF 或单张图片")
    ap.add_argument("outdir")
    ap.add_argument("--dpi", type=int, default=150, help="矢量 PDF 的渲染 dpi")
    ap.add_argument("--force-raster", action="store_true", help="强制按 dpi 光栅化，不用内嵌原图")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    out = Path(args.outdir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        sys.exit(f"源文件不存在: {src}")
    for old in list(out.glob("page-*.png")) + list(out.glob("native-*")):
        old.unlink()

    if src.suffix.lower() == ".pdf":
        native_resolution_note(src)
        pages = None if args.force_raster else pdf_native_images(src, out)
        if pages:
            print(f"[提示] 抽取 PDF 内嵌原生位图 {len(pages)} 页（不放大）", file=sys.stderr)
        else:
            pages = pdf_to_png(src, out, args.dpi)
    else:
        dst = out / "page-1.png"
        shutil.copyfile(src, dst)
        pages = [dst]

    result = []
    for idx, page in enumerate(pages, 1):
        img = np.array(Image.open(page).convert("L"))
        systems = find_systems(img)
        result.append({
            "page": idx,
            "image": page.name,
            "width": int(img.shape[1]),
            "height": int(img.shape[0]),
            "systems": systems,
        })
        print(f"{page.name}: {img.shape[1]}x{img.shape[0]}, 检出 {len(systems)} 行五线谱", file=sys.stderr)

    (out / "systems.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(out / "systems.json")


if __name__ == "__main__":
    main()
