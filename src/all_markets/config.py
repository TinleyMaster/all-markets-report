from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


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
    feishu_webhook_url: str | None
    feishu_app_id: str | None
    feishu_app_secret: str | None
    feishu_doc_id: str | None
    report_brand: str


def load_runtime_config(workspace: Path | None = None) -> RuntimeConfig:
    workspace = workspace or Path.cwd()
    load_dotenv(workspace / ".env")

    config_path = workspace / "config" / "markets.yaml"
    with config_path.open("r", encoding="utf-8") as file:
        config_data = yaml.safe_load(file)

    return RuntimeConfig(
        workspace=workspace,
        timezone=config_data.get("timezone", "Asia/Shanghai"),
        lookback_days=int(config_data.get("lookback_days", 15)),
        top_regions=int(config_data.get("top_regions", 4)),
        top_themes=int(config_data.get("top_themes", 4)),
        top_losers=int(config_data.get("top_losers", 4)),
        config_data=config_data,
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL"),
        feishu_app_id=os.getenv("FEISHU_APP_ID"),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET"),
        feishu_doc_id=os.getenv("FEISHU_DOC_ID"),
        report_brand=os.getenv("REPORT_BRAND", "全球资金风格流向早报"),
    )
