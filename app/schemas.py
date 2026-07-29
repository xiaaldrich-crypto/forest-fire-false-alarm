"""结构化输出模型。"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

Decision = Literal["疑似真实火情", "疑似误报", "建议人工复核"]
MediaType = Literal["image", "video"]


class BBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class OpenCVFeatures(BaseModel):
    media_type: MediaType = "image"
    mean_brightness: float
    bright_ratio: float
    edge_sharpness: float
    fire_area_ratio: float
    smoke_area_ratio: float
    fire_boxes: list[BBox] = Field(default_factory=list)
    smoke_boxes: list[BBox] = Field(default_factory=list)
    # 烟柱形态分：越高越像“烟柱/烟团”，越低越像整幅山体灰/雾
    smoke_plume_score: float = 0.0
    # 视频时序特征（图片时 persistence=1.0 或 0）
    frame_count: int = 1
    sampled_frames: int = 1
    duration_sec: Optional[float] = None
    fire_persistence: float = 0.0
    smoke_persistence: float = 0.0
    keyframe_path: Optional[str] = None
    vis_fire_path: Optional[str] = None
    vis_smoke_path: Optional[str] = None
    vis_overlay_path: Optional[str] = None


class RuleScore(BaseModel):
    type: str
    score: float
    matched_rules: list[str] = Field(default_factory=list)
    reason: str


class RuleResult(BaseModel):
    top_type: Optional[str] = None
    scores: list[RuleScore] = Field(default_factory=list)
    preliminary_decision: Decision
    notes: list[str] = Field(default_factory=list)


class MultimodalResult(BaseModel):
    enabled: bool
    is_real_fire: Optional[bool] = None
    false_alarm_type: Optional[str] = None
    confidence: Optional[float] = None
    reason: str = ""
    raw: Optional[dict[str, Any]] = None
    degraded: bool = False


class AnalysisResponse(BaseModel):
    media_name: str
    media_type: MediaType = "image"
    person_nearby: Optional[bool] = None
    opencv: OpenCVFeatures
    rules: RuleResult
    multimodal: MultimodalResult
    final_decision: Decision
    final_reason: str
