from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


DEFAULT_REPORT_BRAND = "全球资金流向早报"


@dataclass
class RuntimeConfig:
    workspace: Path
    timezone: str
    lookback_days: int
    top_regions: int
    top_themes: int
    top_losers: int
    config_data: dict[str, Any]
    deepseek_api_key: str | None
    deepseek_model: str
    feishu_app_id: str | None
    feishu_app_secret: str | None
    feishu_chat_id: str | None
    feishu_report_folder: str | None
    report_brand: str
    news_sources: dict[str, Any]
    event_calendar: dict[str, Any]


def _clean_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _load_yaml_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _load_optional_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _load_yaml_file(path)


def load_runtime_config(workspace: Path | None = None) -> RuntimeConfig:
    workspace = workspace or Path.cwd()
    load_dotenv(workspace / ".env")

    config_path = workspace / "config" / "markets.yaml"
    config_data = _load_yaml_file(config_path)
    news_sources = _load_optional_yaml(workspace / "config" / "news_sources.yaml")
    event_calendar = _load_optional_yaml(workspace / "config" / "event_calendar.yaml")

    return RuntimeConfig(
        workspace=workspace,
        timezone=config_data.get("timezone", "Asia/Shanghai"),
        lookback_days=int(config_data.get("lookback_days", 15)),
        top_regions=int(config_data.get("top_regions", 4)),
        top_themes=int(config_data.get("top_themes", 4)),
        top_losers=int(config_data.get("top_losers", 4)),
        config_data=config_data,
        deepseek_api_key=_clean_env("DEEPSEEK_API_KEY"),
        deepseek_model=_clean_env("DEEPSEEK_MODEL") or "deepseek-v4-flash",
        feishu_app_id=_clean_env("FEISHU_APP_ID"),
        feishu_app_secret=_clean_env("FEISHU_APP_SECRET"),
        feishu_chat_id=_clean_env("FEISHU_CHAT_ID"),
        feishu_report_folder=_clean_env("FEISHU_REPORT_FOLDER"),
        report_brand=_clean_env("REPORT_BRAND") or DEFAULT_REPORT_BRAND,
        news_sources=news_sources,
        event_calendar=event_calendar,
    )
