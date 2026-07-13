from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from .analyzer import AnalysisResult, MarketLeader
from .weekly_signals import WeeklySignal, WeeklyValidation


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


def _extract_cot_weekly_change(signal: WeeklySignal) -> str | None:
    details = signal.details or {}
    value = details.get("weekly_change_contracts")
    if value is None:
        return None
    return f"{float(value):+,.0f} 张"


def _extract_cot_direction(signal: WeeklySignal) -> str:
    summary = signal.summary
    if "继续加多" in summary:
        return "加多"
    if "继续减仓" in summary:
        return "减仓"
    return "变化有限"


def _format_cot_signal(signal: WeeklySignal) -> str:
    weekly_change = _extract_cot_weekly_change(signal)
    weekly_change_text = f"，周变动 {weekly_change}" if weekly_change else ""
    return (
        f"- {signal.name}：{signal.value}，仓位状态 {signal.direction}"
        f"{weekly_change_text}，近周方向 {_extract_cot_direction(signal)}。"
    )


def _format_single_weekly_signal(signal: WeeklySignal) -> str:
    return f"- {signal.summary}"


def _weekly_markdown(weekly_validation: WeeklyValidation | None) -> list[str]:
    if weekly_validation is None:
        return ["## 第2层：周频增强信号", "- 暂无周频增强数据。"]

    lines = ["## 第2层：周频增强信号"]
    if weekly_validation.highlights:
        lines.extend(
            [
                "### 真实流量补充验证",
                *[f"- {item}" for item in weekly_validation.highlights],
            ]
        )

    if weekly_validation.cot_signals:
        lines.append("")
        cot_as_of = weekly_validation.cot_signals[0].as_of
        lines.append(f"### CFTC COT（截至 {cot_as_of}）")
        lines.extend(
            _format_cot_signal(signal) for signal in weekly_validation.cot_signals
        )

    if weekly_validation.northbound_signal:
        lines.append("")
        lines.append("### A股北向资金")
        lines.append(_format_single_weekly_signal(weekly_validation.northbound_signal))

    if weekly_validation.btc_etf_signal:
        lines.append("")
        lines.append("### BTC ETF 净流入")
        lines.append(_format_single_weekly_signal(weekly_validation.btc_etf_signal))

    if weekly_validation.credit_signal:
        lines.append("")
        lines.append("### 信用债 ETF 风险偏好")
        lines.append(_format_single_weekly_signal(weekly_validation.credit_signal))

    if weekly_validation.errors:
        lines.append("")
        lines.append("### 数据备注")
        lines.extend(f"- {item}" for item in weekly_validation.errors)

    return lines


def build_report(
    brand: str,
    timezone: str,
    analysis: AnalysisResult,
    weekly_validation: WeeklyValidation | None = None,
) -> ReportBundle:
    now = datetime.now(ZoneInfo(timezone))
    date_label = now.strftime("%Y-%m-%d")
    effective_brand = brand.strip() or "全球资金流向早报"
    best_regions = _join_names(analysis.top_regions, "全球强势市场")
    best_themes = _join_names(analysis.top_themes, "成长主线")

    title = f"{date_label} {effective_brand}"
    headline = f"{date_label} | {analysis.regime}"
    summary = f"今日全球资金偏向{best_regions}与{best_themes}，整体处于“{analysis.regime}”框架。"

    weakest_lines = [
        f"- {item.name}（{item.symbol}）日涨跌 {item.daily_return:+.2f}%，解释：{_weak_reason(item, analysis.macro_flags)}"
        for item in analysis.weakest_markets
    ]
    macro_lines = (
        "\n".join(f"- {flag}" for flag in analysis.macro_flags)
        or "- 宏观变量波动有限，市场更关注相对收益。"
    )

    markdown_lines = [
        f"# {title}",
        "",
        f"> 市场状态：{headline}",
        "",
        "## 今日一句话",
        summary,
        "",
        "## 第1层：日频免费主报告",
        "",
        "### 四分法结论",
        f"- 叙事判断：{analysis.narrative}",
        "- 业绩判断：强势市场集中在盈利确定性更高的龙头与半导体链。",
        f"- 交易判断：最强方向是{best_regions}与{best_themes}，弱势市场则面临相对收益流失。",
        f"- {analysis.positioning}",
        "",
        "### 股票地域轮动",
        _format_leaders("强势区域", analysis.top_regions),
        "",
        "### 股票行业轮动",
        _format_leaders("强势主题", analysis.top_themes),
        "",
        "### 为什么其他市场跌",
        *weakest_lines,
        "",
        "### 宏观因子",
        macro_lines,
        "",
        "### 全球基准表现",
        _table_markdown(analysis.benchmark_table),
        "",
        "### 主题表现",
        _table_markdown(analysis.theme_table),
        "",
        "### 跨资产表现",
        _table_markdown(analysis.cross_asset_table, include_asset_class=True),
        "",
        *_weekly_markdown(weekly_validation),
    ]
    markdown = "\n".join(markdown_lines)

    weekly_summary = (
        weekly_validation.highlights[0]
        if weekly_validation and weekly_validation.highlights
        else None
    )
    short_text_lines = [
        f"市场状态：{analysis.regime}",
        f"一句话：{summary}",
        f"叙事判断：{analysis.narrative}",
        f"交易判断：领涨方向为{best_regions}、{best_themes}。",
        f"仓位判断：{analysis.positioning.replace('仓位判断：', '')}",
    ]
    if weekly_summary:
        short_text_lines.append(f"周频验证：{weekly_summary}")
    short_text = "\n".join(short_text_lines)

    payload = {
        "date": date_label,
        "title": title,
        "headline": headline,
        "report_brand": effective_brand,
        "summary": summary,
        "analysis": asdict(analysis),
        "weekly_validation": weekly_validation.to_payload()
        if weekly_validation
        else None,
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
