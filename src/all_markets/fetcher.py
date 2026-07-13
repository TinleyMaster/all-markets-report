from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import yfinance as yf


@dataclass
class SymbolSnapshot:
    symbol: str
    name: str
    group: str
    meta: str
    latest_close: float
    prev_close: float
    daily_return: float
    weekly_return: float
    volume_ratio: float | None


def _download_history(
    symbol: str, lookback_days: int, retries: int = 3
) -> pd.DataFrame:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            data = yf.download(
                tickers=symbol,
                period=f"{lookback_days + 10}d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if not data.empty:
                return data
        except Exception as error:  # pragma: no cover - network path
            last_error = error
        time.sleep(attempt)
    if last_error:
        raise last_error
    raise RuntimeError(f"无法获取 {symbol} 的行情数据")


def _series_from_frame(frame: pd.DataFrame, field: str) -> pd.Series:
    if isinstance(frame.columns, pd.MultiIndex):
        if field in frame.columns.get_level_values(0):
            return frame[field].iloc[:, 0].dropna()
        return pd.Series(dtype=float)
    if field not in frame.columns:
        return pd.Series(dtype=float)
    return frame[field].dropna()


def _build_snapshot(item: dict, lookback_days: int) -> SymbolSnapshot | None:
    frame = _download_history(item["symbol"], lookback_days)
    close_series = _series_from_frame(frame, "Close")
    volume_series = _series_from_frame(frame, "Volume")
    if len(close_series) < 2:
        return None

    latest_close = float(close_series.iloc[-1])
    prev_close = float(close_series.iloc[-2])
    daily_return = (latest_close / prev_close - 1.0) * 100

    weekly_base = (
        close_series.iloc[-6] if len(close_series) >= 6 else close_series.iloc[0]
    )
    weekly_return = (latest_close / float(weekly_base) - 1.0) * 100

    volume_ratio: float | None = None
    if not volume_series.empty:
        latest_volume = float(volume_series.iloc[-1])
        rolling_volume = (
            float(volume_series.tail(10).mean())
            if len(volume_series) >= 3
            else latest_volume
        )
        if rolling_volume > 0:
            volume_ratio = latest_volume / rolling_volume

    return SymbolSnapshot(
        symbol=item["symbol"],
        name=item["name"],
        group=item.get("bucket") or item.get("theme") or item.get("macro") or "unknown",
        meta="bucket" if "bucket" in item else "theme" if "theme" in item else "macro",
        latest_close=latest_close,
        prev_close=prev_close,
        daily_return=daily_return,
        weekly_return=weekly_return,
        volume_ratio=volume_ratio,
    )


def fetch_snapshots(items: Iterable[dict], lookback_days: int) -> list[SymbolSnapshot]:
    snapshots: list[SymbolSnapshot] = []
    for item in items:
        snapshot = _build_snapshot(item, lookback_days)
        if snapshot:
            snapshots.append(snapshot)
    return snapshots
