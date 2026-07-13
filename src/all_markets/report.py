from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .analyzer import AnalysisResult, MarketLeader


@dataclass
class ReportBundle:
    date_label: str
    title: str
    short_text: str
    markdown: str
    payload: dict


def _join_names(leaders: list[MarketLeader], fallback: str) -> str:
    names = [item.name for item in leaders[:2]]
    return "、".join(names) if names else fallback


def _format_leaders(title: str, leaders: list[MarketLeader]) -> str:
    lines = [f"### {title}"]
    for item in leaders:
        lines.append(
            f"- {item.name}（{item.symbol}）日涨跌 {item.daily_return:+.2f}%，5日 {item.weekly_return:+.2f}%，原因：{item.reason}"
        )
    return "\n".join(lines)


def _table_markdown(rows: list[dict], include_asset_class: bool = False) -> str:
    if include_asset_class:
        lines = [
            "| 资产类别 | 标的 | 代码 | 日涨跌 | 5日涨跌 |",
            "| --- | --- | --- | ---: | ---: |",
        ]
        for row in rows:
            lines.append(
                f"| {row['asset_class']} | {row['name']} | {row['symbol']} | {row['daily_return']:+.2f}% | {row['weekly_return']:+.2f}% |"
            )
        return "\n".join(lines)

    lines = ["| 标的 | 代码 | 日涨跌 | 5日涨跌 |", "| --- | --- | ---: | ---: |"]
    for row in rows:
        lines.append(
            f"| {row['name']} | {row['symbol']} | {row['daily_return']:+.2f}% | {row['weekly_return']:+.2f}% |"
        )
    return "\n".join(lines)


def _weak_reason(item: MarketLeader, macro_flags: list[str]) -> str:
    if any("美元走强" in flag for flag in macro_flags):
        return "美元偏强削弱了非美资产的风险承受力。"
    if any("高利率" in flag or "长债走弱" in flag for flag in macro_flags):
        return "利率抬升压制估值扩张，弱势市场承压更明显。"
    return "短期缺少增量叙事，资金流向更强的相对收益方向。"


def build_report(brand: str, timezone: str, analysis: AnalysisResult) -> ReportBundle:
    now = datetime.now(ZoneInfo(timezone))
    date_label = now.strftime("%Y-%m-%d")
    effective_brand = brand.strip() or "全球资金流向早报"
    best_regions = _join_names(analysis.top_regions, "全球强势市场")
    best_themes = _join_names(analysis.top_themes, "成长主线")

    title = f"{date_label} | {analysis.regime}"
    summary = f"今日全球资金偏向{best_regions}与{best_themes}，整体处于“{analysis.regime}”框架。"

    weakest_lines = [
        f"- {item.name}（{item.symbol}）日涨跌 {item.daily_return:+.2f}%，解释：{_weak_reason(item, analysis.macro_flags)}"
        for item in analysis.weakest_markets
    ]
    macro_lines = "\n".join(f"- {flag}" for flag in analysis.macro_flags) or "- 宏观变量波动有限，市场更关注相对收益。"

    markdown = "\n".join(
        [
            f"# {title}",
            "",
            "## 今日一句话",
            summary,
            "",
            "## 四分法结论",
            f"- 叙事判断：{analysis.narrative}",
            "- 业绩判断：强势市场集中在盈利确定性更高的龙头与半导体链。",
            f"- 交易判断：最强方向是{best_regions}与{best_themes}，弱势市场则面临相对收益流失。",
            f"- {analysis.positioning}",
            "",
            "## 资金流向地图",
            _format_leaders("强势区域", analysis.top_regions),
            "",
            _format_leaders("强势主题", analysis.top_themes),
            "",
            "## 为什么其他市场跌",
            *weakest_lines,
            "",
            "## 宏观因子",
            macro_lines,
            "",
            "## 全球基准表现",
            _table_markdown(analysis.benchmark_table),
            "",
            "## 主题表现",
            _table_markdown(analysis.theme_table),
            "",
            "## 跨资产表现",
            _table_markdown(analysis.cross_asset_table, include_asset_class=True),
        ]
    )

    short_text = "\n".join(
        [
            title,
            f"一句话：{summary}",
            f"叙事判断：{analysis.narrative}",
            f"交易判断：领涨方向为{best_regions}、{best_themes}。",
            f"仓位判断：{analysis.positioning.replace('仓位判断：', '')}",
        ]
    )

    payload = {
        "date": date_label,
        "title": title,
        "report_brand": effective_brand,
        "summary": summary,
        "analysis": asdict(analysis),
        "markdown": markdown,
    }
    json.loads(json.dumps(payload, ensure_ascii=False))
    return ReportBundle(
        date_label=date_label,
        title=title,
        short_text=short_text,
        markdown=markdown,
        payload=payload,
    )
