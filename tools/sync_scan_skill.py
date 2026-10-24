#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本仓库的扫描技能文件同步到 dsh-musescore-skills 合集，或校验两边是否一致。

用法:
    python tools/sync_scan_skill.py --bundle ../dsh-musescore-skills
    python tools/sync_scan_skill.py --bundle ../dsh-musescore-skills --check

约定:
  * 本仓库（scan-score-to-musescore）是扫描技能的源码真源；
  * 合集里 skills/scan-score-to-musescore/ 必须与下面 FILES 逐字节一致；
  * --check 只比对、不写文件，有漂移时退出码 1（可直接放进 CI）。
"""
from __future__ import annotations

import argparse
import filecmp
import shutil
import sys
from pathlib import Path

# 相对仓库根目录，也是相对技能目录的路径（两边布局相同）
FILES = (
    "SKILL.md",
    "scripts/mxml.py",
    "scripts/mxml_ext.py",
    "scripts/pdf_scan.py",
    "scripts/pitchmap.py",
    "scripts/probe.py",
    "scripts/score_from_json.py",
    "scripts/verify.py",
    "references/notation-mapping.md",
    "assets/example_score.json",
)


def find_skill_dir(bundle: Path) -> Path:
    for candidate in (bundle / "skills" / "scan-score-to-musescore", bundle):
        if (candidate / "SKILL.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    sys.exit(f"在 {bundle} 下找不到技能目录（skills/scan-score-to-musescore/）")


def main() -> None:
    ap = argparse.ArgumentParser(description="sync/check the vendored scan skill")
    ap.add_argument("--bundle", default="../dsh-musescore-skills",
                    help="dsh-musescore-skills checkout 路径（默认同级目录）")
    ap.add_argument("--check", action="store_true", help="只校验，不写入")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[1]
    bundle = Path(args.bundle)
    if not bundle.is_absolute():
        bundle = (Path.cwd() / bundle).resolve()
    skill = find_skill_dir(bundle)

    missing, drift = [], []
    for rel in FILES:
        src = root / rel
        dst = skill / rel
        if not src.is_file():
            sys.exit(f"源文件缺失: {src}")
        if not dst.is_file():
            missing.append(rel)
        elif not filecmp.cmp(src, dst, shallow=False):
            drift.append(rel)

    extras = []
    known = set(FILES)
    for path in sorted(skill.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(skill).as_posix()
        if rel not in known:
            extras.append(rel)

    if args.check:
        for rel in missing:
            print(f"MISSING {rel}")
        for rel in drift:
            print(f"DRIFT   {rel}")
        for rel in extras:
            print(f"EXTRA   {rel}")
        if missing or drift or extras:
            sys.exit(f"\n技能副本与源不一致（{len(missing)} missing, {len(drift)} drift, "
                     f"{len(extras)} extra）；运行不带 --check 的命令同步。")
        print(f"OK: {len(FILES)} 个文件与 {skill} 一致")
        return

    for rel in FILES:
        dst = skill / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel in missing or rel in drift:
            shutil.copyfile(root / rel, dst)
            print(f"updated {rel}")
    if extras:
        print("注意：合集里有本仓库没有的文件（未自动删除）: " + ", ".join(extras))
    print(f"synced {len(FILES)} files -> {skill}")


if __name__ == "__main__":
    main()
