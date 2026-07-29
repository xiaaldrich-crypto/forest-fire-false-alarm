"""应用路径与环境配置。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
SAMPLES_DIR = DATA_DIR / "samples"
UPLOADS_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"
LABELS_DIR = DATA_DIR / "labels"
RULES_PATH = ROOT_DIR / "config" / "rules.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT_DIR / ".env"), extra="ignore")

    llm_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen-vl-max"
    llm_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_rules() -> dict:
    with RULES_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs() -> None:
    for p in (SAMPLES_DIR, UPLOADS_DIR, RESULTS_DIR, LABELS_DIR):
        p.mkdir(parents=True, exist_ok=True)
