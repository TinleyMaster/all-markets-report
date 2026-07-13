from __future__ import annotations

from dataclasses import dataclass

from .fetcher import SymbolSnapshot


@dataclass
class MarketLeader:
    name: str
    symbol: str
    score: float
    daily_return: float
    weekly_return: float
    reason: str


@dataclass
class AnalysisResult:
    regime: str
    narrative: str
    positioning: str
    top_regions: list[MarketLeader]
    top_themes: list[MarketLeader]
    weakest_markets: list[MarketLeader]
    macro_flags: list[str]
    benchmark_table: list[dict]
    theme_table: list[dict]
    cross_asset_table: list[dict]


def _score(snapshot: SymbolSnapshot) -> float:
    volume_boost = 0.0
    if snapshot.volume_ratio is not None:
        volume_boost = min(max(snapshot.volume_ratio - 1.0, -1.0), 1.5) * 0.8
    return snapshot.daily_return * 0.55 + snapshot.weekly_return * 0.35 + volume_boost


def _leader_reason(
    snapshot: SymbolSnapshot, macro_context: dict[str, SymbolSnapshot]
) -> str:
    reasons: list[str] = []
    if snapshot.weekly_return > 2:
        reasons.append("近一周相对强势")
    if snapshot.volume_ratio and snapshot.volume_ratio > 1.15:
        reasons.append("成交活跃度抬升")
    if snapshot.daily_return > 1.5:
        reasons.append("日内有明显增量资金追逐")

    if snapshot.group in {
        "us_ai",
        "us_tech",
        "us_semiconductor",
        "korea_semiconductor",
        "taiwan_semiconductor",
    }:
        if macro_context.get("duration") and macro_context["duration"].daily_return > 0:
            reasons.append("利率压力边际缓和，有利成长板块")
        else:
            reasons.append("AI 与半导体仍是资金主线")
    elif snapshot.group in {"energy"}:
        reasons.append("油价偏强支撑能源链表现")
    elif snapshot.group in {"defensives"}:
        reasons.append("资金偏向防御配置")

    return "，".join(reasons[:3]) or "相对收益领先同类市场"


def _macro_map(macro_snapshots: list[SymbolSnapshot]) -> dict[str, SymbolSnapshot]:
    return {item.group: item for item in macro_snapshots}


def _macro_flags(macro_context: dict[str, SymbolSnapshot]) -> list[str]:
    flags: list[str] = []
    dollar = macro_context.get("dollar")
    duration = macro_context.get("duration")
    oil = macro_context.get("oil")
    gold = macro_context.get("gold")
    volatility = macro_context.get("volatility")

    if dollar and dollar.daily_return > 0.4:
        flags.append("美元走强，非美资产承压")
    elif dollar and dollar.daily_return < -0.4:
        flags.append("美元回落，风险资产获得喘息")

    if duration and duration.daily_return > 0.5:
        flags.append("长债反弹，利率压力边际缓和")
    elif duration and duration.daily_return < -0.5:
        flags.append("长债走弱，市场重新交易高利率")

    if volatility and volatility.daily_return > 5:
        flags.append("VIX 抬升，风险偏好回落")
    elif volatility and volatility.daily_return < -5:
        flags.append("VIX 回落，风险偏好修复")

    if oil and oil.daily_return > 1:
        flags.append("油价走强，输入型经济体与制造链成本承压")

    if gold and gold.daily_return > 0.8:
        flags.append("黄金偏强，避险情绪仍有残留")
    return flags


def _build_regime(
    macro_context: dict[str, SymbolSnapshot], top_themes: list[MarketLeader]
) -> tuple[str, str, str]:
    dollar = macro_context.get("dollar")
    duration = macro_context.get("duration")
    volatility = macro_context.get("volatility")

    growth_bias = any(
        item.symbol
        in {"QQQ", "XLK", "SOXX", "SMH", "NVDA", "MSFT", "005930.KS", "000660.KS"}
        for item in top_themes
    )
    risk_on = (
        volatility is not None
        and volatility.daily_return < 0
        and dollar is not None
        and dollar.daily_return <= 0.3
        and growth_bias
    )

    if risk_on:
        regime = "风险偏好回升"
        narrative = "全球资金正在从防御与低弹性资产回流成长，主线集中在 AI 与半导体。"
        positioning = "仓位判断：偏进攻，但继续围绕盈利确定性更强的科技龙头。"
    elif duration and duration.daily_return < -0.5:
        regime = "高利率压制"
        narrative = (
            "市场重新交易利率上行，成长与新兴市场承压，资金更偏向防御与现金流资产。"
        )
        positioning = "仓位判断：以均衡偏防守为主，回避高估值弱基本面资产。"
    else:
        regime = "震荡轮动"
        narrative = "全球市场缺乏单一主线，资金更偏向区域与行业之间的相对收益切换。"
        positioning = "仓位判断：维持均衡配置，聚焦最强地区与最强主题。"
    return regime, narrative, positioning


def _to_table_rows(items: list[SymbolSnapshot]) -> list[dict]:
    return [
        {
            "name": item.name,
            "symbol": item.symbol,
            "daily_return": round(item.daily_return, 2),
            "weekly_return": round(item.weekly_return, 2),
        }
        for item in items
    ]


def _cross_asset_rows(items: list[SymbolSnapshot]) -> list[dict]:
    asset_class_names = {
        "crypto": "加密资产",
        "fx": "外汇",
        "commodities": "大宗商品",
        "us_rates": "美债",
    }
    return [
        {
            "asset_class": asset_class_names.get(item.group, item.group),
            "name": item.name,
            "symbol": item.symbol,
            "daily_return": round(item.daily_return, 2),
            "weekly_return": round(item.weekly_return, 2),
        }
        for item in items
    ]


def analyze_market_data(
    benchmark_snapshots: list[SymbolSnapshot],
    theme_snapshots: list[SymbolSnapshot],
    macro_snapshots: list[SymbolSnapshot],
    cross_asset_snapshots: list[SymbolSnapshot],
    top_regions: int,
    top_themes: int,
    top_losers: int,
) -> AnalysisResult:
    macro_context = _macro_map(macro_snapshots)

    ranked_regions = sorted(
        [
            MarketLeader(
                name=item.name,
                symbol=item.symbol,
                score=_score(item),
                daily_return=item.daily_return,
                weekly_return=item.weekly_return,
                reason=_leader_reason(item, macro_context),
            )
            for item in benchmark_snapshots
        ],
        key=lambda x: x.score,
        reverse=True,
    )
    ranked_themes = sorted(
        [
            MarketLeader(
                name=item.name,
                symbol=item.symbol,
                score=_score(item),
                daily_return=item.daily_return,
                weekly_return=item.weekly_return,
                reason=_leader_reason(item, macro_context),
            )
            for item in theme_snapshots
        ],
        key=lambda x: x.score,
        reverse=True,
    )

    weakest_markets = sorted(ranked_regions, key=lambda x: x.score)[:top_losers]
    region_leaders = ranked_regions[:top_regions]
    theme_leaders = ranked_themes[:top_themes]
    regime, narrative, positioning = _build_regime(macro_context, theme_leaders)

    return AnalysisResult(
        regime=regime,
        narrative=narrative,
        positioning=positioning,
        top_regions=region_leaders,
        top_themes=theme_leaders,
        weakest_markets=weakest_markets,
        macro_flags=_macro_flags(macro_context),
        benchmark_table=_to_table_rows(benchmark_snapshots),
        theme_table=_to_table_rows(theme_snapshots),
        cross_asset_table=_cross_asset_rows(cross_asset_snapshots),
    )
