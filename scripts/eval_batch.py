#!/usr/bin/env python3
"""按领导建议：图片/视频分开评估基础算法效果（默认只跑图片）。"""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook

from app.config import LABELS_DIR, SAMPLES_DIR, get_settings
from app.opencv_analyzer import IMAGE_EXT, VIDEO_EXT
from app.pipeline import run_pipeline


def load_labels() -> dict[str, dict]:
    path = LABELS_DIR / "样本标注表.csv"
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            out[row["rel_path"].replace("\\", "/")] = row
    return out


def is_real_gt(lab: dict) -> bool:
    return str(lab.get("is_real_fire", "")).lower() in ("true", "1", "yes")


def pred_bucket(decision: str) -> str:
    if "真实火情" in decision:
        return "real"
    if "误报" in decision:
        return "false"
    return "review"


async def run_eval(media_filter: str) -> Path:
    get_settings.cache_clear()
    labels = load_labels()
    if media_filter == "image":
        exts = IMAGE_EXT
    elif media_filter == "video":
        exts = VIDEO_EXT
    else:
        exts = IMAGE_EXT | VIDEO_EXT

    media_files = sorted(
        [p for p in SAMPLES_DIR.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "批量测试"
    ws.append(
        [
            "相对路径",
            "媒体类型",
            "类别文件夹",
            "最终结论",
            "规则Top类型",
            "火焰面积比",
            "烟雾面积比",
            "烟柱分",
            "理由",
        ]
    )

    stats: Counter = Counter()
    by_label: dict[str, Counter] = defaultdict(Counter)

    for media in media_files:
        rel = str(media.relative_to(SAMPLES_DIR)).replace("\\", "/")
        result = await run_pipeline(media, output_dir=None, person_nearby=None, save_visuals=False)
        ws.append(
            [
                rel,
                result.media_type,
                media.parent.name,
                result.final_decision,
                result.rules.top_type or "",
                result.opencv.fire_area_ratio,
                result.opencv.smoke_area_ratio,
                result.opencv.smoke_plume_score,
                result.final_reason,
            ]
        )
        lab = labels.get(rel)
        if not lab:
            continue
        stats["total"] += 1
        gt_real = is_real_gt(lab)
        pc = pred_bucket(result.final_decision)
        by_label[lab["label"]][result.final_decision] += 1
        if gt_real:
            stats["gt_real"] += 1
            if pc == "false":
                stats["漏报"] += 1
            elif pc == "real":
                stats["真火判对"] += 1
            else:
                stats["真火转人工"] += 1
        else:
            stats["gt_false"] += 1
            if pc == "false":
                stats["误报判对"] += 1
            elif pc == "real":
                stats["误报判成真火"] += 1
            else:
                stats["误报转人工"] += 1

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{media_filter}"
    xlsx = LABELS_DIR / f"批量测试_{batch_id}.xlsx"
    wb.save(xlsx)

    n = stats["total"] or 1
    print(f"=== 基础算法评估（仅{media_filter}）===")
    print("excel:", xlsx)
    print(dict(stats))
    if stats["gt_real"]:
        print(f"漏报率: {stats['漏报']}/{stats['gt_real']} = {stats['漏报']/stats['gt_real']:.1%}")
        print(
            f"真火安全覆盖: {(stats['真火判对']+stats['真火转人工'])}/{stats['gt_real']} = "
            f"{(stats['真火判对']+stats['真火转人工'])/stats['gt_real']:.1%}"
        )
        print(f"真火检出(判真实火情): {stats['真火判对']}/{stats['gt_real']} = {stats['真火判对']/stats['gt_real']:.1%}")
    if stats["gt_false"]:
        print(f"误报过滤率: {stats['误报判对']}/{stats['gt_false']} = {stats['误报判对']/stats['gt_false']:.1%}")
        print(f"误报抬真火: {stats['误报判成真火']}/{stats['gt_false']} = {stats['误报判成真火']/stats['gt_false']:.1%}")
    strict = stats["真火判对"] + stats["误报判对"]
    print(f"严格分类准确率: {strict}/{n} = {strict/n:.1%}")
    print("按类别:", {k: dict(v) for k, v in by_label.items()})
    return xlsx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--media",
        choices=["image", "video", "all"],
        default="image",
        help="领导建议先把图片基础识别做好；默认只评估图片",
    )
    args = parser.parse_args()
    asyncio.run(run_eval(args.media))


if __name__ == "__main__":
    main()
