from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import requests

from .fetcher import SymbolSnapshot


CFTC_DISAGG_SODA_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
CFTC_TFF_SODA_URL = "https://publicreporting.cftc.gov/resource/yw9f-hn96.json"
EASTMONEY_NORTHBOUND_URL = "https://push2his.eastmoney.com/api/qt/kamt.kline/get"
JINA_FARSIDE_PROXY_URL = "https://r.jina.ai/http://farside.co.uk/btc/"

FINANCIAL_COT_TARGETS = {
    "标普500期货": {
        "code": "13874A",
        "net_long": "asset_mgr_positions_long",
        "net_short": "asset_mgr_positions_short",
        "change_long": "change_in_asset_mgr_long",
        "change_short": "change_in_asset_mgr_short",
        "sentiment_label": "资管机构",
    },
    "美债10年期货": {
        "code": "043602",
        "net_long": "asset_mgr_positions_long",
        "net_short": "asset_mgr_positions_short",
        "change_long": "change_in_asset_mgr_long",
        "change_short": "change_in_asset_mgr_short",
        "sentiment_label": "资管机构",
    },
    "欧元期货": {
        "code": "099741",
        "net_long": "asset_mgr_positions_long",
        "net_short": "asset_mgr_positions_short",
        "change_long": "change_in_asset_mgr_long",
        "change_short": "change_in_asset_mgr_short",
        "sentiment_label": "资管机构",
    },
}

COMMODITY_COT_TARGETS = {
    "黄金期货": {
        "code": "088691",
        "net_long": "m_money_positions_long_all",
        "net_short": "m_money_positions_short_all",
        "change_long": "change_in_m_money_long_all",
        "change_short": "change_in_m_money_short_all",
        "sentiment_label": "管理资金",
    },
    "WTI原油期货": {
        "code": "067651",
        "net_long": "m_money_positions_long_all",
        "net_short": "m_money_positions_short_all",
        "change_long": "change_in_m_money_long_all",
        "change_short": "change_in_m_money_short_all",
        "sentiment_label": "管理资金",
    },
}


@dataclass
class WeeklySignal:
    name: str
    as_of: str
    direction: str
    value: str
    summary: str
    source: str
    details: dict[str, Any] | None = None


@dataclass
class WeeklyValidation:
    highlights: list[str]
    cot_signals: list[WeeklySignal]
    northbound_signal: WeeklySignal | None
    btc_etf_signal: WeeklySignal | None
    credit_signal: WeeklySignal | None
    errors: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "highlights": self.highlights,
            "cot_signals": [asdict(item) for item in self.cot_signals],
            "northbound_signal": asdict(self.northbound_signal)
            if self.northbound_signal
            else None,
            "btc_etf_signal": asdict(self.btc_etf_signal)
            if self.btc_etf_signal
            else None,
            "credit_signal": asdict(self.credit_signal) if self.credit_signal else None,
            "errors": self.errors,
        }


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "")
    if not text or text in {".", "-", "nan", "None"}:
        return 0.0
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    if text.startswith("$"):
        text = text[1:]
    return float(text)


def _classify_direction(
    value: float, positive_threshold: float = 0.0, negative_threshold: float = 0.0
) -> str:
    if value > positive_threshold:
        return "流入"
    if value < negative_threshold:
        return "流出"
    return "中性"


def _classify_cot_posture(net_pct_oi: float) -> str:
    if net_pct_oi >= 20:
        return "重仓多头"
    if net_pct_oi >= 5:
        return "偏多"
    if net_pct_oi <= -20:
        return "重仓空头"
    if net_pct_oi <= -5:
        return "偏空"
    return "中性"


def _fetch_latest_cot_row(url: str, contract_code: str) -> dict[str, Any] | None:
    response = requests.get(
        url,
        params={
            "cftc_contract_market_code": contract_code,
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$limit": 1,
        },
        timeout=30,
    )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def _build_cot_signal(
    name: str,
    row: dict[str, Any],
    net_long_field: str,
    net_short_field: str,
    change_long_field: str,
    change_short_field: str,
    sentiment_label: str,
    source: str,
) -> WeeklySignal:
    long_contracts = _to_float(row.get(net_long_field))
    short_contracts = _to_float(row.get(net_short_field))
    open_interest = max(_to_float(row.get("open_interest_all")), 1.0)
    net_contracts = long_contracts - short_contracts
    weekly_change = _to_float(row.get(change_long_field)) - _to_float(
        row.get(change_short_field)
    )
    net_pct_oi = net_contracts / open_interest * 100
    posture = _classify_cot_posture(net_pct_oi)
    if weekly_change > 0:
        change_direction = "继续加多"
    elif weekly_change < 0:
        change_direction = "继续减仓"
    else:
        change_direction = "变化有限"

    return WeeklySignal(
        name=name,
        as_of=str(row.get("report_date_as_yyyy_mm_dd", ""))[:10],
        direction=posture,
        value=f"净仓 {net_contracts:,.0f} 张，占 OI {net_pct_oi:.1f}%",
        summary=f"{sentiment_label}在{name}上的仓位为“{posture}”，周度净变动 {weekly_change:,.0f} 张，说明机构在{change_direction}。",
        source=source,
        details={
            "market_name": row.get("market_and_exchange_names"),
            "net_contracts": round(net_contracts, 2),
            "net_pct_open_interest": round(net_pct_oi, 2),
            "weekly_change_contracts": round(weekly_change, 2),
        },
    )


def fetch_cftc_cot_signals() -> list[WeeklySignal]:
    signals: list[WeeklySignal] = []

    for display_name, spec in FINANCIAL_COT_TARGETS.items():
        row = _fetch_latest_cot_row(CFTC_TFF_SODA_URL, spec["code"])
        if not row:
            continue
        signals.append(
            _build_cot_signal(
                name=display_name,
                row=row,
                net_long_field=spec["net_long"],
                net_short_field=spec["net_short"],
                change_long_field=spec["change_long"],
                change_short_field=spec["change_short"],
                sentiment_label=spec["sentiment_label"],
                source="CFTC TFF",
            )
        )

    for display_name, spec in COMMODITY_COT_TARGETS.items():
        row = _fetch_latest_cot_row(CFTC_DISAGG_SODA_URL, spec["code"])
        if not row:
            continue
        signals.append(
            _build_cot_signal(
                name=display_name,
                row=row,
                net_long_field=spec["net_long"],
                net_short_field=spec["net_short"],
                change_long_field=spec["change_long"],
                change_short_field=spec["change_short"],
                sentiment_label=spec["sentiment_label"],
                source="CFTC Disaggregated",
            )
        )

    return signals


def fetch_northbound_signal(days: int = 5) -> WeeklySignal | None:
    response = requests.get(
        EASTMONEY_NORTHBOUND_URL,
        params={
            "fields1": "f1,f3,f5",
            "fields2": "f51,f52",
            "klt": "101",
            "lmt": "5000",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "cb": "jQuery18305732402561585701_1584961751919",
            "_": "1584962164273",
        },
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://data.eastmoney.com/"},
        timeout=30,
    )
    response.raise_for_status()
    text = response.text
    payload = json.loads(text[text.find("{") : -2])
    data = payload.get("data", {})

    def _parse_series(key: str) -> list[tuple[str, float]]:
        parsed: list[tuple[str, float]] = []
        for entry in data.get(key, []):
            raw = entry[0] if isinstance(entry, list) else entry
            date_text, value_text = str(raw).split(",", 1)
            parsed.append((date_text, _to_float(value_text) / 10000))
        return parsed

    total_series = _parse_series("s2n")
    sh_series = _parse_series("hk2sh")
    sz_series = _parse_series("hk2sz")
    if not total_series:
        return None

    recent_total = total_series[-days:]
    recent_sh = sh_series[-days:]
    recent_sz = sz_series[-days:]
    total_5d = sum(value for _, value in recent_total)
    sh_5d = sum(value for _, value in recent_sh)
    sz_5d = sum(value for _, value in recent_sz)
    as_of = recent_total[-1][0]

    if recent_total and all(abs(value) < 1e-9 for _, value in recent_total):
        return WeeklySignal(
            name="A股北向资金",
            as_of=as_of,
            direction="待更新",
            value=f"近{days}日源站连续返回 0.0 亿",
            summary=f"东方财富北向资金接口近{days}个交易日连续返回 0.0，疑似源站未更新或返回占位值，本期暂不据此下资金结论。",
            source="Eastmoney kamt.kline",
            details={
                "days": days,
                "status": "all_zero_placeholder",
                "northbound_series": recent_total,
            },
        )

    direction = _classify_direction(total_5d)
    return WeeklySignal(
        name="A股北向资金",
        as_of=as_of,
        direction=direction,
        value=f"近{days}日净流入 {total_5d:+.1f} 亿人民币",
        summary=f"北向资金近{days}个交易日累计{direction} {abs(total_5d):.1f} 亿，其中沪股通 {sh_5d:+.1f} 亿、深股通 {sz_5d:+.1f} 亿。",
        source="Eastmoney kamt.kline",
        details={
            "days": days,
            "northbound_5d_cny_100m": round(total_5d, 2),
            "shanghai_connect_5d_cny_100m": round(sh_5d, 2),
            "shenzhen_connect_5d_cny_100m": round(sz_5d, 2),
        },
    )


def _extract_farside_table_markdown(text: str) -> str:
    lines = text.splitlines()
    table_lines = [line.strip() for line in lines if line.strip().startswith("|")]
    return "\n".join(table_lines)


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _parse_farside_rows(markdown: str) -> list[dict[str, str]]:
    raw_lines = [line for line in markdown.splitlines() if line.strip()]
    rows = [_split_markdown_table_row(line) for line in raw_lines]
    ticker_row = next(
        (
            row
            for row in rows
            if row
            and row[0] == ""
            and any(cell in {"IBIT", "FBTC", "GBTC", "BTC"} for cell in row)
        ),
        None,
    )
    if ticker_row is None:
        return []

    columns = ["Date", *ticker_row[1:]]
    if columns[-1] == "":
        columns[-1] = "Total"

    parsed_rows: list[dict[str, str]] = []
    for row in rows:
        if not row or len(row) < len(columns):
            continue
        if not row[0] or not row[0][:2].isdigit():
            continue
        normalized = row[: len(columns)]
        parsed_rows.append(dict(zip(columns, normalized)))
    return parsed_rows


def _parse_flow_cell(value: Any) -> float:
    text = str(value).strip()
    if text in {"-", "", "nan"}:
        return 0.0
    return _to_float(text)


def fetch_btc_etf_signal(days: int = 5) -> WeeklySignal | None:
    response = requests.get(
        JINA_FARSIDE_PROXY_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    table_markdown = _extract_farside_table_markdown(response.text)
    if not table_markdown:
        return None

    parsed_rows = _parse_farside_rows(table_markdown)
    if not parsed_rows:
        return None

    dated_rows: list[dict[str, Any]] = []
    for row in parsed_rows:
        try:
            parsed_date = datetime.strptime(row["Date"], "%d %b %Y")
        except ValueError:
            continue
        normalized = dict(row)
        normalized["parsed_date"] = parsed_date
        normalized["total_flow_usd_m"] = _parse_flow_cell(row.get("Total"))
        dated_rows.append(normalized)

    if not dated_rows:
        return None

    dated_rows.sort(key=lambda item: item["parsed_date"])
    recent_rows = dated_rows[-days:]
    latest_row = recent_rows[-1]
    weekly_total = float(sum(row["total_flow_usd_m"] for row in recent_rows))
    direction = _classify_direction(weekly_total)

    etf_columns = [
        column
        for column in latest_row.keys()
        if column not in {"Date", "Total", "parsed_date", "total_flow_usd_m"}
    ]
    latest_breakdown = {
        str(column): _parse_flow_cell(latest_row[column])
        for column in etf_columns
        if str(latest_row[column]).strip() not in {"", "nan", "-"}
    }
    top_inflow = max(latest_breakdown.items(), key=lambda item: item[1], default=None)
    top_outflow = min(latest_breakdown.items(), key=lambda item: item[1], default=None)
    leaders: list[str] = []
    if top_inflow and top_inflow[1] > 0:
        leaders.append(f"最大流入 {top_inflow[0]} {top_inflow[1]:+.1f} 百万美元")
    if top_outflow and top_outflow[1] < 0:
        leaders.append(f"最大流出 {top_outflow[0]} {top_outflow[1]:+.1f} 百万美元")
    leader_text = "；".join(leaders) if leaders else "分项流量分布较均衡"

    return WeeklySignal(
        name="BTC 现货 ETF",
        as_of=latest_row["parsed_date"].strftime("%Y-%m-%d"),
        direction=direction,
        value=f"近{days}日净流入 {weekly_total:+.1f} 百万美元",
        summary=f"美国 BTC 现货 ETF 近{days}个交易日累计{direction} {abs(weekly_total):.1f} 百万美元；{leader_text}。",
        source="Farside Investors via Jina proxy",
        details={
            "days": days,
            "weekly_total_flow_usd_m": round(weekly_total, 2),
            "latest_day_flow_usd_m": round(float(latest_row["total_flow_usd_m"]), 2),
            "latest_breakdown_usd_m": latest_breakdown,
        },
    )


def build_credit_signal(
    cross_asset_snapshots: list[SymbolSnapshot],
) -> WeeklySignal | None:
    snapshot_map = {item.symbol: item for item in cross_asset_snapshots}
    lqd = snapshot_map.get("LQD")
    hyg = snapshot_map.get("HYG")
    jnk = snapshot_map.get("JNK")
    if not lqd or not hyg:
        return None

    risk_spread = hyg.weekly_return - lqd.weekly_return
    junk_spread = (jnk.weekly_return - lqd.weekly_return) if jnk else 0.0
    direction = (
        "偏好提升" if risk_spread > 0 else "偏好回落" if risk_spread < 0 else "中性"
    )
    summary = (
        f"高收益债相对投资级信用债 5 日超额收益 {risk_spread:+.2f}pct，"
        f"垃圾债相对投资级信用债 {junk_spread:+.2f}pct，信用风险偏好为“{direction}”。"
    )

    return WeeklySignal(
        name="信用债ETF风险偏好",
        as_of="latest",
        direction=direction,
        value=f"HYG-LQD 5日超额 {risk_spread:+.2f}pct",
        summary=summary,
        source="Yahoo Finance proxy",
        details={
            "hyg_weekly_return": round(hyg.weekly_return, 2),
            "lqd_weekly_return": round(lqd.weekly_return, 2),
            "jnk_weekly_return": round(jnk.weekly_return, 2) if jnk else None,
            "risk_spread_pct": round(risk_spread, 2),
            "junk_spread_pct": round(junk_spread, 2),
        },
    )


def build_weekly_validation(
    cross_asset_snapshots: list[SymbolSnapshot],
) -> WeeklyValidation:
    cot_signals: list[WeeklySignal] = []
    northbound_signal: WeeklySignal | None = None
    btc_etf_signal: WeeklySignal | None = None
    credit_signal: WeeklySignal | None = None
    errors: list[str] = []

    try:
        cot_signals = fetch_cftc_cot_signals()
    except Exception as error:  # pragma: no cover - network path
        errors.append(f"CFTC COT 获取失败：{error}")

    try:
        northbound_signal = fetch_northbound_signal()
    except Exception as error:  # pragma: no cover - network path
        errors.append(f"北向资金获取失败：{error}")

    try:
        btc_etf_signal = fetch_btc_etf_signal()
    except Exception as error:  # pragma: no cover - network path
        errors.append(f"BTC ETF 净流入获取失败：{error}")

    try:
        credit_signal = build_credit_signal(cross_asset_snapshots)
    except Exception as error:  # pragma: no cover - defensive path
        errors.append(f"信用债风险偏好构建失败：{error}")

    highlights: list[str] = []
    if northbound_signal:
        highlights.append(northbound_signal.summary)
    if btc_etf_signal:
        highlights.append(btc_etf_signal.summary)
    if credit_signal:
        highlights.append(credit_signal.summary)
    if cot_signals:
        highlights.append("；".join(item.summary for item in cot_signals[:2]))

    return WeeklyValidation(
        highlights=highlights,
        cot_signals=cot_signals,
        northbound_signal=northbound_signal,
        btc_etf_signal=btc_etf_signal,
        credit_signal=credit_signal,
        errors=errors,
    )
