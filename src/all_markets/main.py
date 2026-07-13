from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .analyzer import analyze_market_data
from .config import load_runtime_config
from .feishu import FeishuCredentials, create_dated_report_document, send_group_message
from .fetcher import fetch_snapshots
from .llm_writer import polish_report_with_deepseek
from .report import build_report


def _save_artifacts(workspace: Path, date_label: str, payload: dict, markdown: str) -> tuple[Path, Path]:
    output_dir = workspace / "outputs" / date_label
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    md_path = output_dir / "report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def main() -> None:
    runtime = load_runtime_config()
    config_data = runtime.config_data

    benchmark_snapshots = fetch_snapshots(config_data["benchmarks"], runtime.lookback_days)
    theme_snapshots = fetch_snapshots(config_data["themes"], runtime.lookback_days)
    macro_snapshots = fetch_snapshots(config_data["macro"], runtime.lookback_days)

    analysis = analyze_market_data(
        benchmark_snapshots=benchmark_snapshots,
        theme_snapshots=theme_snapshots,
        macro_snapshots=macro_snapshots,
        top_regions=runtime.top_regions,
        top_themes=runtime.top_themes,
        top_losers=runtime.top_losers,
    )
    bundle = build_report(runtime.report_brand, runtime.timezone, analysis)

    if runtime.deepseek_api_key:
        try:
            bundle = polish_report_with_deepseek(bundle, runtime.deepseek_api_key, runtime.deepseek_model)
        except Exception as error:  # pragma: no cover - network path
            bundle.payload["llm_error"] = str(error)

    json_path, md_path = _save_artifacts(runtime.workspace, bundle.date_label, bundle.payload, bundle.markdown)

    document = None
    if runtime.feishu_app_id and runtime.feishu_app_secret:
        credentials = FeishuCredentials(
            app_id=runtime.feishu_app_id,
            app_secret=runtime.feishu_app_secret,
        )
        if runtime.feishu_report_folder:
            report_date = datetime.strptime(bundle.date_label, "%Y-%m-%d")
            document = create_dated_report_document(
                credentials=credentials,
                parent_folder_ref=runtime.feishu_report_folder,
                report_date=report_date,
                report_brand=runtime.report_brand,
                markdown=bundle.markdown,
            )
        if runtime.feishu_chat_id:
            send_group_message(
                credentials=credentials,
                chat_id=runtime.feishu_chat_id,
                title=bundle.title,
                text=bundle.short_text,
                document=document,
            )

    print(f"Markdown report saved to: {md_path}")
    print(f"JSON report saved to: {json_path}")
    if document and document.url:
        print(f"Feishu doc created: {document.url}")


if __name__ == "__main__":
    main()
