from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from io import StringIO
from typing import Any

import pandas as pd
import requests

from .fetcher import SymbolSnapshot


CFTC_DISAGG_SODA_URL = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
EASTMONEY_NORTHBOUND_URL = "https://push2his.eastmoney.com/api/qt/kamt.kline/get"
FARSIDE_BTC_FLOW_URL = "https://farside.co.uk/btc/"

COT_TARGETS = {
    "标普500期货": "E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE",
    "美债10年期货": "10-YEAR U.S. TREASURY NOTES - CHICAGO BOARD OF TRADE",
    "欧元期货": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "黄金期货": "GOLD - COMMODITY EXCHANGE INC.",
    "WTI原油期货": "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE",
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
            "northbound_signal": asdict(self.northbound_signal) if self.northbound_signal else None,
            "btc_etf_signal": asdict(self.btc_etf_signal) if self.btc_etf_signal else None,
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
    return float(text)


def _classify_direction(value: float, positive_threshold: float = 0.0, negative_threshold: float = 0.0) -> str:
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


def _flatten_columns(columns: pd.Index) -> list[str]:
    flattened: list[str] = []
    for column in columns:
        if isinstance(column, tuple):
            parts = [str(item).strip() for item in column if str(item).strip() and str(item).strip().lower() != "nan"]
            flattened.append(" ".join(parts))
        else:
            flattened.append(str(column))
    return flattened


def fetch_cftc_cot_signals() -> list[WeeklySignal]:
    session = requests.Session()
    signals: list[WeeklySignal] = []
    for display_name, market_name in COT_TARGETS.items():
        where_value = market_name.replace("'", "''")
        response = session.get(
            CFTC_DISAGG_SODA_URL,
            params={
                "$select": ",".join(
                    [
                        "market_and_exchange_names",
                        "report_date_as_yyyy_mm_dd",
                        "open_interest_all",
                        "m_money_positions_long_all",
                        "m_money_positions_short_all",
                        "change_in_m_money_long_all",
                        "change_in_m_money_short_all",
                    ]
                ),
                "$where": f"market_and_exchange_names='{where_value}' AND futonly_or_combined='FutOnly'",
                "$order": "report_date_as_yyyy_mm_dd DESC",
                "$limit": 1,
            },
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            continue

        row = rows[0]
        long_contracts = _to_float(row.get("m_money_positions_long_all"))
        short_contracts = _to_float(row.get("m_money_positions_short_all"))
        open_interest = max(_to_float(row.get("open_interest_all")), 1.0)
        net_contracts = long_contracts - short_contracts
        weekly_change = _to_float(row.get("change_in_m_money_long_all")) - _to_float(
            row.get("change_in_m_money_short_all")
        )
        net_pct_oi = net_contracts / open_interest * 100
        posture = _classify_cot_posture(net_pct_oi)
        change_direction = "继续加多" if weekly_change > 0 else "继续减仓" if weekly_change < 0 else "变化有限"

        signals.append(
            WeeklySignal(
                name=display_name,
                as_of=str(row.get("report_date_as_yyyy_mm_dd", ""))[:10],
                direction=posture,
                value=f"净仓 {net_contracts:,.0f} 张，占 OI {net_pct_oi:.1f}%",
                summary=f"{display_name} 的管理资金仓位为“{posture}”，周度净变动 {weekly_change:,.0f} 张，说明机构在 {change_direction}。",
                source="CFTC COT",
                details={
                    "net_contracts": round(net_contracts, 2),
                    "net_pct_open_interest": round(net_pct_oi, 2),
                    "weekly_change_contracts": round(weekly_change, 2),
                },
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


def fetch_btc_etf_signal(days: int = 5) -> WeeklySignal | None:
    response = requests.get(FARSIDE_BTC_FLOW_URL, timeout=30)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        return None

    table = tables[0].copy()
    table.columns = _flatten_columns(table.columns)
    date_column = table.columns[0]
    total_column = next((column for column in table.columns if "Total" in column and column != date_column), table.columns[-1])

    table[date_column] = table[date_column].astype(str).str.strip()
    date_rows = table[table[date_column].str.match(r"^\d{2} \w{3} \d{4}$", na=False)].copy()
    if date_rows.empty:
        return None

    date_rows["parsed_date"] = pd.to_datetime(date_rows[date_column], format="%d %b %Y", errors="coerce")
    date_rows = date_rows.dropna(subset=["parsed_date"]).sort_values("parsed_date")
    date_rows["total_flow_usd_m"] = date_rows[total_column].apply(_to_float)
    recent_rows = date_rows.tail(days).copy()
    latest_row = recent_rows.iloc[-1]
    weekly_total = float(recent_rows["total_flow_usd_m"].sum())
    direction = _classify_direction(weekly_total)

    etf_columns = [
        column
        for column in date_rows.columns
        if column not in {date_column, total_column, "parsed_date", "total_flow_usd_m"} and "Fee" not in column
    ]
    latest_breakdown = {
        column.split()[-1]: _to_float(latest_row[column])
        for column in etf_columns
        if str(latest_row[column]).strip() not in {"", "nan"}
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
        source="Farside Investors",
        details={
            "days": days,
            "weekly_total_flow_usd_m": round(weekly_total, 2),
            "latest_day_flow_usd_m": round(float(latest_row['total_flow_usd_m']), 2),
            "latest_breakdown_usd_m": latest_breakdown,
        },
    )


def build_credit_signal(cross_asset_snapshots: list[SymbolSnapshot]) -> WeeklySignal | None:
    snapshot_map = {item.symbol: item for item in cross_asset_snapshots}
    lqd = snapshot_map.get("LQD")
    hyg = snapshot_map.get("HYG")
    jnk = snapshot_map.get("JNK")
    if not lqd or not hyg:
        return None

    risk_spread = hyg.weekly_return - lqd.weekly_return
    junk_spread = (jnk.weekly_return - lqd.weekly_return) if jnk else 0.0
    direction = "偏好提升" if risk_spread > 0 else "偏好回落" if risk_spread < 0 else "中性"
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


def build_weekly_validation(cross_asset_snapshots: list[SymbolSnapshot]) -> WeeklyValidation:
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
