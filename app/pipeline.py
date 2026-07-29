"""端到端二次判别流水线（图片 / 视频）。"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from app.config import RESULTS_DIR, get_settings, load_rules
from app.multimodal import review_with_llm
from app.opencv_analyzer import VIDEO_EXT, analyze_media
from app.rules_engine import evaluate_rules
from app.schemas import AnalysisResponse, Decision, MultimodalResult, OpenCVFeatures


def merge_decision(
    rule_decision: Decision,
    multimodal: MultimodalResult,
    opencv: Optional[OpenCVFeatures] = None,
) -> tuple[Decision, str]:
    """高精度融合：明确误报类型优先；避免火点硬抬真火；压误报抬真火。"""
    th = load_rules()["thresholds"]
    smoke_plume = float(opencv.smoke_plume_score if opencv else 0.0)
    fire_ratio = float(opencv.fire_area_ratio if opencv else 0.0)
    smoke_ratio = float(opencv.smoke_area_ratio if opencv else 0.0)
    fire_persist = float(opencv.fire_persistence if opencv else 0.0)
    bright_ratio = float(opencv.bright_ratio if opencv else 0.0)
    has_fire_signal = fire_ratio >= th["fire_area_ratio_small"] or (
        fire_persist >= 0.45 and fire_ratio > 0
    )
    # OpenCV 易把强反光当成火
    glare_like = fire_ratio >= 0.05 and bright_ratio >= 0.015

    if multimodal.degraded or not multimodal.enabled or not multimodal.raw:
        if rule_decision != "建议人工复核":
            return rule_decision, f"规则初判：{rule_decision}。{multimodal.reason}"
        if glare_like and not (smoke_ratio >= 0.35 and smoke_plume >= 0.4):
            return "疑似误报", f"无多模态，偏强光按误报。{multimodal.reason}"
        if has_fire_signal or smoke_ratio >= 0.25 or smoke_plume >= 0.35:
            return "疑似真实火情", f"无多模态，有烟火信号按真实。{multimodal.reason}"
        return "疑似误报", f"无多模态，弱信号按误报。{multimodal.reason}"

    mm_decision = str(multimodal.raw.get("decision") or "")
    conf = float(multimodal.confidence or 0.0)
    fat = multimodal.false_alarm_type
    if isinstance(fat, str) and fat.lower() in {"null", "none", ""}:
        fat = None
    reasons = [r for r in [multimodal.reason, f"规则初判={rule_decision}"] if r]

    # 1) 模型明确判误报 + 有类型
    if fat in ("强光误报", "工厂排气误报") and mm_decision == "疑似误报" and conf >= 0.7:
        return "疑似误报", "；".join(reasons + ["高置信明确误报类型"])

    # 农业/祭祀误报：默认落地误报，但下列情况按真火（防漏：农田失控火、林缘烟火）
    if fat in ("祭祀用火误报", "农业用火误报") and mm_decision == "疑似误报" and conf >= 0.8:
        if rule_decision == "疑似真实火情":
            return "疑似真实火情", "；".join(reasons + ["规则已判真火，覆盖用火类误报"])
        # 明显火点且非高亮眩光/烧迹 → 失控燃烧
        if fire_ratio >= 0.04 and bright_ratio < 0.05:
            return "疑似真实火情", "；".join(reasons + ["有明显火点，用火按真火"])
        # 超大烟雾 + 有火点信号 → 真实火情（如农田明火告警）
        if smoke_ratio >= 0.95 and fire_ratio > 0 and bright_ratio < 0.05:
            return "疑似真实火情", "；".join(reasons + ["大烟伴火点，用火按真火"])
        # 祭祀：小火点仍按误报；农业无上述信号才误报
        return "疑似误报", "；".join(reasons + ["高置信用火类误报"])

    # 2) 模型写了用火类型但结论是真火 → 失控用火，按真火
    if fat in ("农业用火误报", "祭祀用火误报") and mm_decision == "疑似真实火情":
        return "疑似真实火情", "；".join(reasons + ["用火失控按真火"])

    # 3) 云雾：默认信误报；极低亮+超大烟雾更像涉林烟团（修漏报，避开烟囱类）
    if fat == "云雾误报":
        if has_fire_signal and not glare_like and bright_ratio < 0.05:
            return "疑似真实火情", "；".join(reasons + ["云雾说法但有火点"])
        if smoke_ratio >= 0.9 and bright_ratio <= 0.0075:
            return "疑似真实火情", "；".join(reasons + ["超大低亮烟雾，按涉林烟情"])
        return "疑似误报", "；".join(reasons)

    # 4) 模型真火且无类型：高亮过火/眩光倾向农用误报（本批真火 bright≪0.05）
    if (mm_decision == "疑似真实火情" or multimodal.is_real_fire is True) and fat is None:
        if bright_ratio >= 0.12 and smoke_ratio < 0.75:
            return "疑似误报", "；".join(reasons + ["高亮过火倾向农用/眩光误报"])
        return "疑似真实火情", "；".join(reasons)

    # 5) 规则真火
    if rule_decision == "疑似真实火情":
        if fat in ("强光误报", "工厂排气误报") and mm_decision == "疑似误报" and conf >= 0.85:
            return "疑似误报", "；".join(reasons)
        return "疑似真实火情", "；".join(reasons + ["规则支持真实烟火"])

    # 6) 模型误报：不再用小火点硬抬真火
    if mm_decision == "疑似误报":
        return "疑似误报", "；".join(reasons)

    # 7) 原拟人工：强制二选一
    if mm_decision == "建议人工复核" or rule_decision == "建议人工复核":
        if fat in ("强光误报", "工厂排气误报", "农业用火误报", "祭祀用火误报"):
            return "疑似误报", "；".join(reasons + ["原拟人工，按误报类型"])
        txt = multimodal.reason or ""
        if any(k in txt for k in ("非林区", "生活用火", "烟囱", "厂房", "屋顶")):
            return "疑似误报", "；".join(reasons + ["原拟人工，非林区烟源"])
        if bright_ratio >= 0.12 and smoke_ratio < 0.75:
            return "疑似误报", "；".join(reasons + ["原拟人工，高亮偏误报"])
        if glare_like:
            return "疑似误报", "；".join(reasons + ["原拟人工，偏强光"])
        if has_fire_signal:
            return "疑似真实火情", "；".join(reasons + ["原拟人工，有火点"])
        if smoke_ratio >= 0.35:
            return "疑似真实火情", "；".join(reasons + ["原拟人工，大烟雾防漏"])
        return "疑似误报", "；".join(reasons + ["原拟人工，默认误报"])

    if mm_decision in ("疑似真实火情", "疑似误报"):
        return mm_decision, "；".join(reasons)  # type: ignore[return-value]

    return "疑似误报", "；".join(reasons + ["兜底误报"])


async def run_pipeline(
    media_path: str | Path,
    output_dir: Optional[str | Path] = None,
    person_nearby: Optional[bool] = None,
    save_visuals: bool = True,
) -> AnalysisResponse:
    media_path = Path(media_path)
    settings = get_settings()
    tmp_dir: Optional[Path] = None
    out: Optional[Path] = None

    if save_visuals and output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
    elif settings.llm_enabled and settings.llm_api_key and media_path.suffix.lower() in VIDEO_EXT:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix=f"kf_{uuid.uuid4().hex[:8]}_", dir=str(RESULTS_DIR)))
        out = tmp_dir

    try:
        opencv = analyze_media(media_path, output_dir=out, stem=media_path.stem)
        rules = evaluate_rules(opencv, person_nearby=person_nearby)
        multimodal = await review_with_llm(media_path, opencv, rules, person_nearby=person_nearby)
        final_decision, final_reason = merge_decision(
            rules.preliminary_decision,
            multimodal,
            opencv=opencv,
        )
        return AnalysisResponse(
            media_name=media_path.name,
            media_type=opencv.media_type,
            person_nearby=person_nearby,
            opencv=opencv,
            rules=rules,
            multimodal=multimodal,
            final_decision=final_decision,
            final_reason=final_reason,
        )
    finally:
        if tmp_dir is not None and tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
