"""OpenCV 传统分析：支持报警图片与视频（均匀抽帧 + 特征聚合）。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.schemas import BBox, OpenCVFeatures

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def _boxes_from_mask(mask: np.ndarray, min_area: int = 80) -> list[BBox]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[BBox] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        boxes.append(BBox(x=int(x), y=int(y), w=int(w), h=int(h)))
    boxes.sort(key=lambda b: b.w * b.h, reverse=True)
    return boxes[:8]


def _draw_boxes(image: np.ndarray, boxes: list[BBox], color: tuple[int, int, int]) -> np.ndarray:
    out = image.copy()
    for b in boxes:
        cv2.rectangle(out, (b.x, b.y), (b.x + b.w, b.y + b.h), color, 2)
    return out


def _smoke_plume_score(boxes: list[BBox], frame_w: int, frame_h: int) -> float:
    """根据框位置/长宽比估计是否像烟柱（而非整幅灰蒙蒙背景）。"""
    if not boxes or frame_w <= 0 or frame_h <= 0:
        return 0.0
    best = 0.0
    for b in boxes[:5]:
        if b.w <= 0 or b.h <= 0:
            continue
        aspect = b.h / float(b.w)  # 烟柱通常偏高
        width_ratio = b.w / float(frame_w)
        # 中下部更像烟源；顶部大横条更像云雾/天空
        cy = (b.y + b.h / 2.0) / float(frame_h)
        vertical_bonus = 0.35 if cy >= 0.35 else 0.1
        aspect_bonus = min(aspect / 1.8, 1.0) * 0.4
        # 横向铺满减分（山体/雾带）
        width_penalty = 0.35 if width_ratio >= 0.55 else 0.0
        score = max(0.0, vertical_bonus + aspect_bonus - width_penalty)
        # 面积太小的碎块降权
        area_ratio = (b.w * b.h) / float(frame_w * frame_h)
        if area_ratio < 0.005:
            score *= 0.5
        best = max(best, score)
    return round(min(best, 1.0), 3)


def _analyze_frame(img: np.ndarray) -> dict:
    h, w = img.shape[:2]
    total = float(h * w)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(np.mean(gray))
    bright_mask = (gray >= 220).astype(np.uint8) * 255
    bright_ratio = float(np.count_nonzero(bright_mask) / total)
    edge_sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 90, 130])
    upper_red1 = np.array([18, 255, 255])
    lower_red2 = np.array([162, 90, 130])
    upper_red2 = np.array([180, 255, 255])
    lower_yellow = np.array([18, 90, 150])
    upper_yellow = np.array([40, 255, 255])
    fire_mask = cv2.bitwise_or(
        cv2.inRange(hsv, lower_red1, upper_red1),
        cv2.inRange(hsv, lower_red2, upper_red2),
    )
    fire_mask = cv2.bitwise_or(fire_mask, cv2.inRange(hsv, lower_yellow, upper_yellow))
    fire_mask = cv2.bitwise_and(fire_mask, (gray >= 100).astype(np.uint8) * 255)
    # 强光/反光抑制
    hsv_v = hsv[:, :, 2]
    fire_mask = cv2.bitwise_and(fire_mask, cv2.bitwise_not(bright_mask))
    fire_mask = cv2.bitwise_and(fire_mask, (gray < 220).astype(np.uint8) * 255)
    fire_mask = cv2.bitwise_and(fire_mask, (hsv_v < 240).astype(np.uint8) * 255)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_OPEN, kernel)
    fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_CLOSE, kernel)
    fire_boxes = _boxes_from_mask(fire_mask, min_area=max(80, int(total * 0.0003)))
    fire_area_ratio = float(np.count_nonzero(fire_mask) / total)

    # 烟雾候选：低饱和灰区；天空带削弱；剔除横向铺满的大块（山体/雾带）
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    smoke_mask = (
        (sat <= 50) & (val >= 75) & (val <= 190) & (gray >= 75) & (gray <= 185)
    ).astype(np.uint8) * 255
    smoke_mask = cv2.bitwise_and(smoke_mask, cv2.bitwise_not(bright_mask))
    sky_cut = int(h * 0.32)
    smoke_mask[:sky_cut, :] = (smoke_mask[:sky_cut, :].astype(np.float32) * 0.25).astype(np.uint8)
    smoke_mask = cv2.morphologyEx(smoke_mask, cv2.MORPH_OPEN, kernel)
    smoke_mask = cv2.morphologyEx(
        smoke_mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    )

    raw_boxes = _boxes_from_mask(smoke_mask, min_area=max(250, int(total * 0.0012)))
    kept: list[BBox] = []
    refined = np.zeros_like(smoke_mask)
    for b in raw_boxes:
        width_ratio = b.w / float(w)
        aspect = b.h / float(max(b.w, 1))
        cy = (b.y + b.h / 2.0) / float(h)
        # 过滤：顶部横铺大雾带、接近整幅宽的灰带
        if width_ratio >= 0.7 and aspect < 0.55:
            continue
        if cy < 0.25 and width_ratio >= 0.45:
            continue
        kept.append(b)
        refined[b.y : b.y + b.h, b.x : b.x + b.w] = smoke_mask[b.y : b.y + b.h, b.x : b.x + b.w]
    smoke_boxes = kept[:8]
    smoke_mask = refined
    smoke_area_ratio = float(np.count_nonzero(smoke_mask) / total)
    plume = _smoke_plume_score(smoke_boxes, w, h)

    return {
        "mean_brightness": mean_brightness,
        "bright_ratio": bright_ratio,
        "edge_sharpness": edge_sharpness,
        "fire_area_ratio": fire_area_ratio,
        "smoke_area_ratio": smoke_area_ratio,
        "smoke_plume_score": plume,
        "fire_boxes": fire_boxes,
        "smoke_boxes": smoke_boxes,
        "fire_mask": fire_mask,
        "smoke_mask": smoke_mask,
        "frame": img,
        "score": fire_area_ratio * 2.0 + smoke_area_ratio * 0.5 + plume,
    }


def _save_visuals(
    img: np.ndarray,
    fire_boxes: list[BBox],
    smoke_boxes: list[BBox],
    fire_mask: np.ndarray,
    smoke_mask: np.ndarray,
    output_dir: Path,
    stem: str,
) -> tuple[str, str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fire_vis = _draw_boxes(img, fire_boxes, (0, 0, 255))
    smoke_vis = _draw_boxes(img, smoke_boxes, (255, 180, 0))
    overlay = _draw_boxes(img, fire_boxes, (0, 0, 255))
    overlay = _draw_boxes(overlay, smoke_boxes, (255, 180, 0))
    tint = overlay.copy()
    tint[fire_mask > 0] = (0, 0, 220)
    tint[smoke_mask > 0] = (200, 160, 40)
    overlay = cv2.addWeighted(overlay, 0.65, tint, 0.35, 0)

    vis_fire_path = str(output_dir / f"{stem}_fire.jpg")
    vis_smoke_path = str(output_dir / f"{stem}_smoke.jpg")
    vis_overlay_path = str(output_dir / f"{stem}_overlay.jpg")
    cv2.imwrite(vis_fire_path, fire_vis)
    cv2.imwrite(vis_smoke_path, smoke_vis)
    cv2.imwrite(vis_overlay_path, overlay)
    return vis_fire_path, vis_smoke_path, vis_overlay_path


def analyze_image(
    image_path: str | Path,
    output_dir: Optional[str | Path] = None,
    stem: Optional[str] = None,
) -> OpenCVFeatures:
    image_path = Path(image_path)
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"无法读取图片: {image_path}")

    stem = stem or image_path.stem
    feat = _analyze_frame(img)
    has_fire = feat["fire_area_ratio"] > 0.0005
    has_smoke = feat["smoke_area_ratio"] > 0.005

    vis_fire = vis_smoke = vis_overlay = keyframe = None
    if output_dir is not None:
        out = Path(output_dir)
        vis_fire, vis_smoke, vis_overlay = _save_visuals(
            img,
            feat["fire_boxes"],
            feat["smoke_boxes"],
            feat["fire_mask"],
            feat["smoke_mask"],
            out,
            stem,
        )
        keyframe = str(out / f"{stem}_keyframe.jpg")
        cv2.imwrite(keyframe, img)

    return OpenCVFeatures(
        media_type="image",
        mean_brightness=round(feat["mean_brightness"], 2),
        bright_ratio=round(feat["bright_ratio"], 5),
        edge_sharpness=round(feat["edge_sharpness"], 2),
        fire_area_ratio=round(feat["fire_area_ratio"], 5),
        smoke_area_ratio=round(feat["smoke_area_ratio"], 5),
        fire_boxes=feat["fire_boxes"],
        smoke_boxes=feat["smoke_boxes"],
        smoke_plume_score=float(feat.get("smoke_plume_score", 0.0)),
        frame_count=1,
        sampled_frames=1,
        duration_sec=None,
        fire_persistence=1.0 if has_fire else 0.0,
        smoke_persistence=1.0 if has_smoke else 0.0,
        keyframe_path=keyframe,
        vis_fire_path=vis_fire,
        vis_smoke_path=vis_smoke,
        vis_overlay_path=vis_overlay,
    )


def analyze_video(
    video_path: str | Path,
    output_dir: Optional[str | Path] = None,
    stem: Optional[str] = None,
    max_frames: int = 12,
) -> OpenCVFeatures:
    """均匀抽帧分析视频，聚合时序特征，并导出关键帧可视化。"""
    video_path = Path(video_path)
    stem = stem or video_path.stem
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 25.0
    duration = (total_frames / fps) if total_frames > 0 else None

    if total_frames <= 0:
        # 部分编码器拿不到总帧数，退化为顺序读最多 max_frames 帧
        indices = list(range(max_frames))
    else:
        n = min(max_frames, total_frames)
        if n <= 1:
            indices = [0]
        else:
            indices = [int(i * (total_frames - 1) / (n - 1)) for i in range(n)]

    frame_feats: list[dict] = []
    for idx in indices:
        if total_frames > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        frame_feats.append(_analyze_frame(frame))
    cap.release()

    if not frame_feats:
        raise ValueError(f"视频无有效帧: {video_path}")

    best = max(frame_feats, key=lambda x: x["score"])
    fire_hits = sum(1 for f in frame_feats if f["fire_area_ratio"] > 0.0005)
    smoke_hits = sum(1 for f in frame_feats if f["smoke_area_ratio"] > 0.005)
    n = len(frame_feats)

    mean_brightness = float(np.mean([f["mean_brightness"] for f in frame_feats]))
    bright_ratio = float(np.max([f["bright_ratio"] for f in frame_feats]))
    edge_sharpness = float(np.mean([f["edge_sharpness"] for f in frame_feats]))
    # 用峰值体现瞬时火点，均值体现持续烟雾
    fire_area_ratio = float(np.max([f["fire_area_ratio"] for f in frame_feats]))
    smoke_area_ratio = float(np.mean([f["smoke_area_ratio"] for f in frame_feats]))
    smoke_plume_score = float(np.max([f.get("smoke_plume_score", 0.0) for f in frame_feats]))

    vis_fire = vis_smoke = vis_overlay = keyframe = None
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        keyframe = str(out / f"{stem}_keyframe.jpg")
        cv2.imwrite(keyframe, best["frame"])
        vis_fire, vis_smoke, vis_overlay = _save_visuals(
            best["frame"],
            best["fire_boxes"],
            best["smoke_boxes"],
            best["fire_mask"],
            best["smoke_mask"],
            out,
            stem,
        )

    return OpenCVFeatures(
        media_type="video",
        mean_brightness=round(mean_brightness, 2),
        bright_ratio=round(bright_ratio, 5),
        edge_sharpness=round(edge_sharpness, 2),
        fire_area_ratio=round(fire_area_ratio, 5),
        smoke_area_ratio=round(smoke_area_ratio, 5),
        fire_boxes=best["fire_boxes"],
        smoke_boxes=best["smoke_boxes"],
        smoke_plume_score=round(smoke_plume_score, 3),
        frame_count=total_frames if total_frames > 0 else n,
        sampled_frames=n,
        duration_sec=round(duration, 2) if duration is not None else None,
        fire_persistence=round(fire_hits / n, 3),
        smoke_persistence=round(smoke_hits / n, 3),
        keyframe_path=keyframe,
        vis_fire_path=vis_fire,
        vis_smoke_path=vis_smoke,
        vis_overlay_path=vis_overlay,
    )


def analyze_media(
    media_path: str | Path,
    output_dir: Optional[str | Path] = None,
    stem: Optional[str] = None,
) -> OpenCVFeatures:
    media_path = Path(media_path)
    suffix = media_path.suffix.lower()
    if suffix in IMAGE_EXT:
        return analyze_image(media_path, output_dir=output_dir, stem=stem)
    if suffix in VIDEO_EXT:
        return analyze_video(media_path, output_dir=output_dir, stem=stem)
    raise ValueError(f"不支持的文件类型: {suffix}")
