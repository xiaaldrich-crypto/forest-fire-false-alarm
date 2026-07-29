"""多模态大模型二次判别（OpenAI 兼容接口，可降级）。

含标注 few-shot；倾向给出明确结论，减少无必要的人工复核。
"""
from __future__ import annotations

import base64
import json
import mimetypes
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import ROOT_DIR, SAMPLES_DIR, get_settings
from app.opencv_analyzer import VIDEO_EXT
from app.schemas import MultimodalResult, OpenCVFeatures, RuleResult

FEW_SHOT_PATH = ROOT_DIR / "config" / "few_shot.json"


def _encode_image(image_path: Path) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(str(image_path))
    mime = mime or "image/jpeg"
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return mime, data


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("模型未返回可解析 JSON")
    return json.loads(m.group(0))


@lru_cache
def _load_few_shot() -> list[dict[str, Any]]:
    if not FEW_SHOT_PATH.exists():
        return []
    data = json.loads(FEW_SHOT_PATH.read_text(encoding="utf-8"))
    return list(data.get("examples") or [])


PROMPT_TEMPLATE = """你是森林火灾监控二次判别专家。请给出明确结论（尽量只要真火/误报两档）。

【目标】在防漏报前提下提高准确率：类型明确的误报必须判「疑似误报」。

【疑似真实火情】
- 林区/林缘烟柱、烟团、涉林烟雾（大面积灰白在林区也不要轻易说云雾）
- 林地燃烧、火情告警

【疑似误报】（高置信时必须判误报，不要抬成真火）
- 强光误报：反光/太阳眩光，金属高亮，无持续烟柱
- 工厂排气：烟囱厂房白烟蒸汽
- 农业用火：农田、田埂、荒地烧荒；红褐色过火迹在耕地/荒地也算农用火，不是森林火灾
- 祭祀用火：墓地、很小火点、短时烟
- 云雾：均匀铺开、无烟源、无火；但若在密林且像升起烟雾，改判真实烟情

【禁止】
- 把强光眩光、墓地小火、农田烧荒抬成「疑似真实火情」
- 把涉林真实烟雾判成云雾误报
- 习惯性「建议人工复核」

先看【已标注示例】，再判当前样本。

【当前样本-媒体类型】{media_type}
【OpenCV特征】
{opencv_json}
【规则初判】
{rules_json}
【人员辅助】{person_text}

只输出 JSON：
{{
  "is_real_fire": true/false/null,
  "false_alarm_type": "强光误报|祭祀用火误报|农业用火误报|工厂排气误报|云雾误报|null",
  "confidence": 0.0到1.0,
  "decision": "疑似真实火情|疑似误报|建议人工复核",
  "reason": "简短中文理由"
}}
"""


def _build_few_shot_content(exclude_name: Optional[str] = None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for i, ex in enumerate(_load_few_shot(), start=1):
        rel = ex.get("rel_path") or ""
        path = SAMPLES_DIR / rel
        if not path.exists():
            continue
        if exclude_name and path.name == exclude_name:
            continue
        mime, b64 = _encode_image(path)
        gold = ex.get("gold_decision")
        gtype = ex.get("gold_type")
        note = ex.get("note") or ""
        blocks.append(
            {
                "type": "text",
                "text": f"【已标注示例{i}】标准答案 decision={gold}，false_alarm_type={gtype}。{note}",
            }
        )
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            }
        )
    if blocks:
        blocks.append({"type": "text", "text": "【当前待判别样本】请给出明确 JSON 结论（尽量不要人工复核）："})
    return blocks


async def review_with_llm(
    media_path: str | Path,
    opencv: OpenCVFeatures,
    rules: RuleResult,
    person_nearby: Optional[bool] = None,
) -> MultimodalResult:
    settings = get_settings()
    media_path = Path(media_path)

    if not settings.llm_enabled or not settings.llm_api_key:
        return MultimodalResult(
            enabled=False,
            degraded=True,
            reason="未配置多模态 API（LLM_ENABLED/LLM_API_KEY），按安全原则降级为依赖规则与人工复核",
        )

    if opencv.keyframe_path and Path(opencv.keyframe_path).exists():
        vision_path = Path(opencv.keyframe_path)
    else:
        vision_path = media_path

    if not vision_path.exists() or vision_path.suffix.lower() in VIDEO_EXT:
        return MultimodalResult(
            enabled=True,
            degraded=True,
            reason="缺少可用关键帧图片，多模态已降级",
        )

    person_text = {True: "有", False: "无", None: "未知/未标注"}[person_nearby]
    prompt = PROMPT_TEMPLATE.format(
        media_type=opencv.media_type,
        opencv_json=opencv.model_dump_json(
            indent=2,
            exclude={
                "vis_fire_path",
                "vis_smoke_path",
                "vis_overlay_path",
                "keyframe_path",
                "fire_boxes",
                "smoke_boxes",
            },
        ),
        rules_json=rules.model_dump_json(indent=2),
        person_text=person_text,
    )

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.extend(_build_few_shot_content(exclude_name=vision_path.name))
    mime, b64 = _encode_image(vision_path)
    content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    payload = {
        "model": settings.llm_model,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    url = settings.llm_api_base.rstrip("/") + "/chat/completions"

    last_err: Optional[Exception] = None
    data = None
    # 先直连（避开坏代理 403），失败再走系统代理
    for trust_env in (False, True):
        try:
            async with httpx.AsyncClient(timeout=120.0, trust_env=trust_env) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                raw_content = resp.json()["choices"][0]["message"]["content"]
                data = _extract_json(raw_content)
                break
        except Exception as e:  # noqa: BLE001
            last_err = e
    if data is None:
        return MultimodalResult(
            enabled=True,
            degraded=True,
            reason=f"多模态调用失败，已降级：{last_err}",
        )

    decision = str(data.get("decision") or "")
    fat = data.get("false_alarm_type")
    if isinstance(fat, str) and fat.lower() in {"null", "none", ""}:
        fat = None
        data["false_alarm_type"] = None

    # 后处理：强光/工厂类型优先误报；农用/祭祀若模型已判真火则保留（失控用火）
    if fat in ("强光误报", "工厂排气误报"):
        decision = "疑似误报"
        data["decision"] = decision
        data["is_real_fire"] = False
    elif fat in ("农业用火误报", "祭祀用火误报"):
        if decision != "疑似真实火情" and data.get("is_real_fire") is not True:
            decision = "疑似误报"
            data["decision"] = decision
            data["is_real_fire"] = False
    elif fat == "云雾误报" and decision == "建议人工复核":
        decision = "疑似误报"
        data["decision"] = decision
        data["is_real_fire"] = False

    if decision == "建议人工复核":
        if data.get("is_real_fire") is True:
            decision = "疑似真实火情"
        elif data.get("is_real_fire") is False or fat:
            decision = "疑似误报"
        else:
            decision = "疑似误报"
        data["decision"] = decision

    if decision not in ("疑似真实火情", "疑似误报", "建议人工复核"):
        decision = "疑似误报" if fat else "疑似真实火情"
        data["decision"] = decision

    return MultimodalResult(
        enabled=True,
        degraded=False,
        is_real_fire=data.get("is_real_fire"),
        false_alarm_type=data.get("false_alarm_type"),
        confidence=data.get("confidence"),
        reason=str(data.get("reason") or ""),
        raw=data,
    )
