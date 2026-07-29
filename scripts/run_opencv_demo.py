#!/usr/bin/env python3
"""对 data/samples 抽图片/视频跑 OpenCV 可视化。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.opencv_analyzer import IMAGE_EXT, VIDEO_EXT, analyze_media
from app.rules_engine import evaluate_rules

SAMPLES = ROOT / "data" / "samples"
OUT = ROOT / "data" / "results" / "opencv_demo"
MEDIA_EXT = IMAGE_EXT | VIDEO_EXT


def main() -> None:
    media_files = sorted(
        [p for p in SAMPLES.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXT]
    )
    if not media_files:
        raise SystemExit("无样本，请先运行: python scripts/prepare_samples.py")
    OUT.mkdir(parents=True, exist_ok=True)
    # 各类型各取若干，避免视频全量太慢
    picked: list[Path] = []
    by_cat: dict[str, list[Path]] = {}
    for p in media_files:
        by_cat.setdefault(p.parent.name, []).append(p)
    for files in by_cat.values():
        picked.extend(files[:3])

    for media in picked:
        feat = analyze_media(media, output_dir=OUT / media.parent.name, stem=media.stem)
        rules = evaluate_rules(feat)
        print(
            f"{media.relative_to(SAMPLES)} [{feat.media_type}] -> "
            f"{rules.preliminary_decision} / {rules.top_type} "
            f"(fire_p={feat.fire_persistence}, smoke_p={feat.smoke_persistence})"
        )
        (OUT / media.parent.name / f"{media.stem}_features.json").write_text(
            json.dumps(
                {"opencv": feat.model_dump(), "rules": rules.model_dump()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    print(f"可视化输出: {OUT}")


if __name__ == "__main__":
    main()
