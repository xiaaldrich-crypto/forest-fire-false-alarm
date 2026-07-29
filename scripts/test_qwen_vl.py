#!/usr/bin/env python3
"""测试通义千问 VL 是否配置成功（单张样本）。"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.pipeline import run_pipeline


async def main() -> None:
    get_settings.cache_clear()
    s = get_settings()
    print("LLM_ENABLED =", s.llm_enabled)
    print("LLM_API_BASE =", s.llm_api_base)
    print("LLM_MODEL    =", s.llm_model)
    print("LLM_API_KEY  =", (s.llm_api_key[:8] + "...") if s.llm_api_key else "(空)")
    if not s.llm_enabled or not s.llm_api_key or "换成" in s.llm_api_key:
        raise SystemExit("请先在 .env 填入真实 Key，并设置 LLM_ENABLED=true")

    sample = next(Path("data/samples").rglob("*.jpg"), None)
    if not sample:
        raise SystemExit("没有样本图片，请先 python scripts/prepare_samples.py")

    result = await run_pipeline(sample, output_dir=None, save_visuals=True)
    # 需要 keyframe：对单测临时开 visuals
    out = ROOT / "data" / "results" / "_llm_probe"
    result = await run_pipeline(sample, output_dir=out, save_visuals=True)
    print("样本:", sample)
    print("最终结论:", result.final_decision)
    print("多模态启用:", result.multimodal.enabled, "降级:", result.multimodal.degraded)
    print("多模态理由:", result.multimodal.reason)
    print("置信度:", result.multimodal.confidence)


if __name__ == "__main__":
    asyncio.run(main())
