#!/usr/bin/env python3
"""整理桌面报警样本（图片+视频）到 data/samples，并生成标注表。"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"
LABELS = ROOT / "data" / "labels"

SOURCE = Path("/Users/xch200700510/Desktop/烟、火报警视频图片")

CATEGORY_MAP = {
    "光误报": {"label": "强光误报", "is_real_fire": False, "is_false_alarm": True},
    "烟筒误报": {"label": "工厂排气误报", "is_real_fire": False, "is_false_alarm": True},
    "祭祀用火": {"label": "祭祀用火误报", "is_real_fire": False, "is_false_alarm": True},
    "农用火烟报警": {"label": "农业用火误报", "is_real_fire": False, "is_false_alarm": True},
    "正常烟报警（林缘）": {"label": "真实烟情-林缘", "is_real_fire": True, "is_false_alarm": False},
    "正常烟报警（涉林）": {"label": "真实烟情-涉林", "is_real_fire": True, "is_false_alarm": False},
    "火告警": {"label": "真实火情", "is_real_fire": True, "is_false_alarm": False},
}

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT


def unpack_zips(folder: Path) -> None:
    for z in folder.glob("*.zip"):
        target = folder / z.stem
        target.mkdir(exist_ok=True)
        with zipfile.ZipFile(z, "r") as zf:
            zf.extractall(target)
        print(f"unzip: {z.name} -> {target}")


def copy_media() -> list[dict]:
    if SAMPLES.exists():
        for p in SAMPLES.rglob("*"):
            if p.is_file() and p.suffix.lower() in MEDIA_EXT:
                p.unlink()
    SAMPLES.mkdir(parents=True, exist_ok=True)
    LABELS.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    if not SOURCE.exists():
        raise SystemExit(f"源目录不存在: {SOURCE}")

    fire_dir = SOURCE / "火告警"
    if fire_dir.exists():
        unpack_zips(fire_dir)

    for src_name, meta in CATEGORY_MAP.items():
        src = SOURCE / src_name
        if not src.exists():
            print(f"skip missing: {src_name}")
            continue
        dst = SAMPLES / meta["label"]
        dst.mkdir(parents=True, exist_ok=True)

        files = [p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXT]
        for media in files:
            if "__MACOSX" in media.parts or media.name.startswith("."):
                continue
            # 跳过明显副本文件
            if "副本" in media.name:
                continue
            out_name = f"{src_name}_{media.stem}{media.suffix.lower()}"
            out_name = out_name.replace(" ", "_")
            out = dst / out_name
            shutil.copy2(media, out)
            media_type = "video" if media.suffix.lower() in VIDEO_EXT else "image"
            rows.append(
                {
                    "filename": out.name,
                    "rel_path": str(out.relative_to(SAMPLES)),
                    "media_type": media_type,
                    "source_folder": src_name,
                    "label": meta["label"],
                    "is_real_fire": meta["is_real_fire"],
                    "is_false_alarm": meta["is_false_alarm"],
                    "person_nearby": "",
                    "notes": "",
                }
            )
            print(f"copy [{media_type}] {media.name} -> {out.relative_to(SAMPLES)}")
    return rows


def write_excel(rows: list[dict]) -> Path:
    headers = [
        "filename",
        "rel_path",
        "media_type",
        "source_folder",
        "label",
        "is_real_fire",
        "is_false_alarm",
        "person_nearby",
        "notes",
    ]
    try:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "样本标注"
        ws.append(headers)
        for r in rows:
            ws.append([r[h] for h in headers])
        path = LABELS / "样本标注表.xlsx"
        wb.save(path)
        # 同步 csv 方便预览
        import csv

        csv_path = LABELS / "样本标注表.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        return path
    except ImportError:
        import csv

        path = LABELS / "样本标注表.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        return path


def main() -> None:
    rows = copy_media()
    xlsx = write_excel(rows)
    n_img = sum(1 for r in rows if r["media_type"] == "image")
    n_vid = sum(1 for r in rows if r["media_type"] == "video")
    print(f"\n共复制 {len(rows)} 个文件（图片 {n_img}，视频 {n_vid}）")
    print(f"标注表: {xlsx}")
    print(f"样本根目录: {SAMPLES}")


if __name__ == "__main__":
    main()
