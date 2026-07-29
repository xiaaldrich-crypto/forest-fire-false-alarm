"""FastAPI 原型：支持图片/视频上传分析、批量测试、结果展示。"""
from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.config import LABELS_DIR, RESULTS_DIR, SAMPLES_DIR, UPLOADS_DIR, ensure_dirs
from app.media_utils import ensure_mp4_faststart
from app.opencv_analyzer import IMAGE_EXT, VIDEO_EXT
from app.pipeline import run_pipeline

ensure_dirs()

app = FastAPI(title="Forest Fire False-Alarm Secondary Verification", version="0.2.0")
BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
EN_WEB = ROOT / "english_web"
templates = Jinja2Templates(directory=str(BASE / "templates"))
en_templates = Jinja2Templates(directory=str(EN_WEB / "templates"))

# 英文静态资源用独立前缀，避免与 /en 页面路由互相干扰
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
app.mount("/static-en", StaticFiles(directory=str(EN_WEB / "static")), name="static_en")
app.mount("/results", StaticFiles(directory=str(RESULTS_DIR)), name="results")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

MEDIA_EXT = IMAGE_EXT | VIDEO_EXT


def _to_results_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return "/results/" + str(Path(path).relative_to(RESULTS_DIR)).replace("\\", "/")


def _parse_person(person_nearby: Optional[str]) -> Optional[bool]:
    if person_nearby in (None, "", "unknown"):
        return None
    if person_nearby in ("true", "1", "yes", "有"):
        return True
    return False


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/en", response_class=HTMLResponse)
@app.get("/en/", response_class=HTMLResponse)
async def index_en(request: Request):
    """English UI (files live in english_web/). Chinese UI at / is unchanged."""
    return en_templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    person_nearby: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(400, "未选择文件")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in MEDIA_EXT:
        raise HTTPException(400, f"仅支持图片 {sorted(IMAGE_EXT)} 或视频 {sorted(VIDEO_EXT)}")

    person = _parse_person(person_nearby)
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    job_dir = RESULTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    save_path = UPLOADS_DIR / f"{job_id}{suffix}"
    with save_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # 便于浏览器拖动进度条浏览完整视频（moov 前置）
    if suffix in VIDEO_EXT:
        try:
            ensure_mp4_faststart(save_path)
        except Exception:  # noqa: BLE001
            pass

    result = await run_pipeline(save_path, output_dir=job_dir, person_nearby=person)
    payload = result.model_dump()
    payload["image_name"] = result.media_name  # 兼容旧字段
    for key in ("vis_fire_path", "vis_smoke_path", "vis_overlay_path", "keyframe_path"):
        payload["opencv"][key] = _to_results_url(payload["opencv"].get(key))
    payload["upload_url"] = f"/uploads/{save_path.name}"
    payload["job_id"] = job_id
    payload["is_video"] = suffix in VIDEO_EXT

    (job_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


@app.post("/api/batch")
async def batch(person_nearby: Optional[str] = Form("unknown")):
    """对 data/samples 下所有图片与视频批量分析并导出 Excel。"""
    from openpyxl import Workbook

    person = _parse_person(person_nearby)
    media_files = sorted(
        [p for p in SAMPLES_DIR.rglob("*") if p.is_file() and p.suffix.lower() in MEDIA_EXT]
    )
    if not media_files:
        raise HTTPException(400, "data/samples 下没有图片/视频，请先运行 scripts/prepare_samples.py")

    wb = Workbook()
    ws = wb.active
    ws.title = "批量测试"
    ws.append(
        [
            "相对路径",
            "媒体类型",
            "类别文件夹",
            "最终结论",
            "规则初判",
            "规则Top类型",
            "亮度均值",
            "高亮占比",
            "火焰面积比",
            "烟雾面积比",
            "火焰持续性",
            "烟雾持续性",
            "抽帧数",
            "多模态启用",
            "多模态置信度",
            "理由",
        ]
    )

    batch_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_batch"
    # 批量测试只导出 Excel，不在 results 下为每个样本建可视化子文件夹

    for media in media_files:
        rel = str(media.relative_to(SAMPLES_DIR))
        category = media.parent.name
        try:
            result = await run_pipeline(
                media,
                output_dir=None,
                person_nearby=person,
                save_visuals=False,
            )
            ws.append(
                [
                    rel,
                    result.media_type,
                    category,
                    result.final_decision,
                    result.rules.preliminary_decision,
                    result.rules.top_type or "",
                    result.opencv.mean_brightness,
                    result.opencv.bright_ratio,
                    result.opencv.fire_area_ratio,
                    result.opencv.smoke_area_ratio,
                    result.opencv.fire_persistence,
                    result.opencv.smoke_persistence,
                    result.opencv.sampled_frames,
                    result.multimodal.enabled and not result.multimodal.degraded,
                    result.multimodal.confidence or "",
                    result.final_reason,
                ]
            )
        except Exception as e:  # noqa: BLE001
            ws.append(
                [rel, media.suffix.lower(), category, "失败", "", "", "", "", "", "", "", "", "", "", "", str(e)]
            )

    xlsx_path = LABELS_DIR / f"批量测试_{batch_id}.xlsx"
    wb.save(xlsx_path)
    return {
        "count": len(media_files),
        "excel": str(xlsx_path),
        "excel_url": f"/api/download?path={xlsx_path.name}",
        "batch_id": batch_id,
    }


@app.get("/api/download")
async def download(path: str):
    target = (LABELS_DIR / Path(path).name).resolve()
    if not str(target).startswith(str(LABELS_DIR.resolve())) or not target.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(target, filename=target.name)


@app.get("/health")
async def health():
    return {"ok": True, "supports": {"image": sorted(IMAGE_EXT), "video": sorted(VIDEO_EXT)}}
