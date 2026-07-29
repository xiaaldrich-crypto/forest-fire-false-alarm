"""基于 OpenCV 特征的误报规则初判（安全优先：宁可转人工，避免漏报）。"""
from __future__ import annotations

from typing import Optional

from app.config import load_rules
from app.schemas import Decision, OpenCVFeatures, RuleResult, RuleScore


def evaluate_rules(
    features: OpenCVFeatures,
    person_nearby: Optional[bool] = None,
) -> RuleResult:
    cfg = load_rules()
    th = cfg["thresholds"]
    scores: list[RuleScore] = []
    notes: list[str] = []

    # 强光误报：高亮 + 锐利 + 低烟低火
    matched = []
    score = 0.0
    if features.bright_ratio >= th["bright_ratio_strong_light"]:
        matched.append("高亮区域占比较高")
        score += 0.4
    if features.edge_sharpness >= th["edge_sharpness_high"]:
        matched.append("边缘锐利")
        score += 0.25
    if features.smoke_area_ratio < th["smoke_area_ratio_small"]:
        matched.append("无明显烟雾")
        score += 0.25
    if features.fire_area_ratio < th["fire_area_ratio_small"]:
        matched.append("无明显火点")
        score += 0.1
    # 若烟雾其实不低，强光置信大幅下降
    if features.smoke_area_ratio >= th["smoke_area_ratio_small"]:
        score *= 0.35
        matched.append("存在烟雾区域，降低强光误报置信")
    scores.append(
        RuleScore(
            type="强光误报",
            score=round(min(score, 1.0), 3),
            matched_rules=matched,
            reason="；".join(matched) or "特征不足",
        )
    )

    # 云雾误报：大面积灰白、无火、纹理弱、且烟柱形态弱（更像铺开雾带）
    matched = []
    score = 0.0
    if features.smoke_area_ratio >= th["smoke_area_ratio_large"]:
        matched.append("大面积灰白区域")
        score += 0.3
    if features.fire_area_ratio < th["fire_area_ratio_small"]:
        matched.append("无火点")
        score += 0.2
    if features.edge_sharpness < th["edge_sharpness_high"] * 0.55:
        matched.append("边界偏模糊/纹理弱")
        score += 0.15
    if features.smoke_plume_score < 0.35:
        matched.append("缺少烟柱形态，更像铺开云雾/灰背景")
        score += 0.25
    if features.media_type == "video" and features.smoke_persistence >= 0.5 and features.smoke_plume_score >= 0.45:
        score *= 0.35
        matched.append("视频烟雾持续且呈烟柱形态，降低云雾误报置信")
    scores.append(
        RuleScore(
            type="云雾误报",
            score=round(min(score, 1.0), 3),
            matched_rules=matched,
            reason="；".join(matched) or "特征不足",
        )
    )

    # 工厂排气
    matched = []
    score = 0.0
    if th["smoke_area_ratio_small"] <= features.smoke_area_ratio < th["smoke_area_ratio_large"]:
        matched.append("存在中等面积烟雾/蒸汽样区域")
        score += 0.35
    if features.fire_area_ratio < th["fire_area_ratio_small"]:
        matched.append("火点不明显")
        score += 0.25
    if 0 < len(features.smoke_boxes) <= 3:
        matched.append("烟源区域相对集中，疑似固定排放源")
        score += 0.25
    scores.append(
        RuleScore(
            type="工厂排气误报",
            score=round(min(score, 1.0), 3),
            matched_rules=matched,
            reason="；".join(matched) or "特征不足",
        )
    )

    # 祭祀用火
    matched = []
    score = 0.0
    if 0 < features.fire_area_ratio <= th["fire_area_ratio_small"] * 2:
        matched.append("火点偏小")
        score += 0.35
    if features.smoke_area_ratio < th["smoke_area_ratio_small"] * 1.5:
        matched.append("烟雾有限，短时烟火特征")
        score += 0.2
    if features.media_type == "video" and 0 < features.fire_persistence < 0.45:
        matched.append("视频中火点持续性偏低（短时）")
        score += 0.2
    if person_nearby is True:
        matched.append("画面中火点附近疑似有人（辅助）")
        score += 0.25
        notes.append("祭祀用火：附近有人仅为辅助证据，不能单独定论")
    elif person_nearby is False:
        score *= 0.7
        matched.append("附近未见明显人员（降低祭祀用火置信）")
    scores.append(
        RuleScore(
            type="祭祀用火误报",
            score=round(min(score, 1.0), 3),
            matched_rules=matched,
            reason="；".join(matched) or "特征不足",
        )
    )

    # 农业用火
    matched = []
    score = 0.0
    if features.smoke_area_ratio >= th["smoke_area_ratio_small"]:
        matched.append("存在明显烟雾")
        score += 0.35
    if features.fire_area_ratio >= th["fire_area_ratio_small"]:
        matched.append("存在火点/燃烧区域")
        score += 0.2
    if person_nearby is True:
        matched.append("烟源附近疑似有人/活动（辅助）")
        score += 0.25
        notes.append("农业用火：人员/车辆仅为辅助，农用火也可能接近林地")
    scores.append(
        RuleScore(
            type="农业用火误报",
            score=round(min(score, 1.0), 3),
            matched_rules=matched,
            reason="；".join(matched) or "特征不足",
        )
    )

    scores.sort(key=lambda s: s.score, reverse=True)
    top = scores[0] if scores else None
    top_type = top.type if top and top.score >= 0.45 else None

    # ---------- 最终决策（安全优先）----------
    decision: Decision
    strong_light = (
        top is not None
        and top.type == "强光误报"
        and top.score >= th["confidence_high"]
        and features.smoke_area_ratio < th["smoke_area_ratio_small"]
        and features.fire_area_ratio < th["fire_area_ratio_small"]
        and features.bright_ratio >= th["bright_ratio_strong_light"]
    )
    factory_clear = (
        top is not None
        and top.type == "工厂排气误报"
        and top.score >= th["confidence_high"]
        and features.fire_area_ratio < th["fire_area_ratio_small"]
        and features.smoke_area_ratio < th["smoke_area_ratio_large"]
    )
    clear_fire = features.fire_area_ratio >= th["fire_area_ratio_large"]
    # 大面积“火焰色”：更像阳光眩光/暖色反射，而非林地火点
    glare_like = features.fire_area_ratio >= 0.08 and (
        features.fire_area_ratio >= 0.22
        or (features.mean_brightness >= 110 and features.bright_ratio >= 0.015)
    )
    if glare_like:
        clear_fire = False
        notes.append("大面积高亮火焰色，疑似阳光眩光，不按明确真火处理")
    persistent_fire = (
        features.media_type == "video"
        and features.fire_persistence >= 0.5
        and features.fire_area_ratio >= th["fire_area_ratio_large"] * 0.7
    )
    # 有明显烟雾：更像烟情/用火，绝不能直接当云雾放行
    notable_smoke = features.smoke_area_ratio >= th["smoke_area_ratio_small"]
    smoke_with_fire = notable_smoke and features.fire_area_ratio >= th["fire_area_ratio_small"]
    persistent_smoke = features.media_type == "video" and features.smoke_persistence >= 0.55
    plume_like = notable_smoke and (
        features.smoke_plume_score >= (0.55 if features.media_type == "video" else 0.45)
    )
    fog_like = (
        features.smoke_area_ratio >= th["smoke_area_ratio_large"]
        and features.smoke_plume_score < 0.35
        and features.fire_area_ratio < th["fire_area_ratio_small"]
    )

    if clear_fire or persistent_fire:
        if top_type in ("祭祀用火误报", "农业用火误报"):
            decision = "建议人工复核"
            notes.append("火点响应存在，但更像用火场景，转人工复核")
        elif glare_like:
            decision = "疑似误报"
            notes.append("大面积火焰色更像阳光眩光，判为强光误报")
        elif features.fire_area_ratio < 0.04 and features.smoke_area_ratio >= th["smoke_area_ratio_small"]:
            decision = "建议人工复核"
            notes.append("小火点+烟雾，真火与农用/祭祀难分，转人工复核")
        else:
            decision = "疑似真实火情"
            notes.append("检测到明显/持续火点，优先按真实火情风险处理")
    elif glare_like:
        decision = "疑似误报"
        notes.append("大面积高亮火焰色，判为强光眩光误报")
    elif plume_like and not glare_like:
        # 烟柱形态明显：基础算法侧按烟情风险处理（领导要求先提基础识别效果）
        if top_type in ("祭祀用火误报", "农业用火误报"):
            decision = "建议人工复核"
            notes.append(f"烟柱明显，但更像{top_type}，转人工复核")
        else:
            decision = "疑似真实火情"
            notes.append("检测到烟柱形态烟雾，优先按真实烟/火情风险处理")
    elif smoke_with_fire:
        # 火烟都有：火点不够大时优先人工，避免农用/祭祀/眩光抬成真火；也不漏报
        if top_type in ("祭祀用火误报", "农业用火误报"):
            decision = "建议人工复核"
            notes.append(f"存在火烟，且更像{top_type}，转人工复核")
        elif features.fire_area_ratio < th["fire_area_ratio_large"]:
            decision = "建议人工复核"
            notes.append("火烟并存但火点规模有限，转人工复核")
        else:
            decision = "疑似真实火情"
            notes.append("检测到较强火烟组合，优先按真实火情风险处理")
    elif notable_smoke or persistent_smoke:
        if strong_light:
            decision = "疑似误报"
            notes.append("强光特征明确且烟雾弱，判为疑似误报")
        elif fog_like:
            decision = "建议人工复核"
            notes.append("灰白区域铺开、烟柱弱，云雾与真实烟难分，转人工复核")
        else:
            decision = "建议人工复核"
            notes.append("存在烟雾/灰白区域，建议人工复核")
    elif strong_light:
        decision = "疑似误报"
        notes.append("强光反射特征较明确，判为疑似误报")
    elif factory_clear:
        decision = "疑似误报"
        notes.append("工厂排气特征较明确，判为疑似误报")
    else:
        decision = "建议人工复核"
        notes.append("特征不确定，按安全原则建议人工复核")

    # 硬约束：大面积烟雾且非眩光/非明确强光时，禁止输出「疑似误报」（防漏报）
    if (
        decision == "疑似误报"
        and not glare_like
        and not strong_light
        and features.smoke_area_ratio >= th["smoke_area_ratio_large"] * 0.6
    ):
        decision = "建议人工复核"
        notes.append("烟雾面积偏大，禁止按误报直接放行，改人工复核")

    return RuleResult(
        top_type=top_type,
        scores=scores,
        preliminary_decision=decision,
        notes=notes,
    )
