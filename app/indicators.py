from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from app.market_data import safe_return


logger = logging.getLogger(__name__)


def safe_number(value: object, digits: int = 4) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not np.isfinite(number):
        return None
    return round(number, digits)


def calculate_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    delta = values.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    average_loss = losses.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + relative_strength))
    rsi = rsi.mask((average_loss == 0) & (average_gain > 0), 100)
    rsi = rsi.mask((average_gain == 0) & (average_loss > 0), 0)
    rsi = rsi.mask((average_gain == 0) & (average_loss == 0), 50)
    return rsi


def classify_rsi(value: float | None) -> str:
    if value is None:
        return "データ不足"
    if value < 30:
        return "売られ過ぎ"
    if value < 45:
        return "弱い"
    if value < 60:
        return "中立"
    if value <= 70:
        return "強い"
    return "過熱"


def consecutive_up_days(series: pd.Series) -> int:
    changes = series.dropna().diff().dropna()
    count = 0
    for value in reversed(changes.tolist()):
        if value <= 0:
            break
        count += 1
    return count


def calculate_metrics(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    universe: pd.DataFrame,
    *,
    minimum_observations: int = 60,
) -> pd.DataFrame:
    metadata = universe.set_index("ticker").to_dict("index")
    records: list[dict] = []

    for ticker in universe["ticker"]:
        if ticker not in close.columns:
            logger.warning("終値を取得できなかったため除外: %s", ticker)
            continue
        prices = pd.to_numeric(close[ticker], errors="coerce").dropna()
        if len(prices) < minimum_observations:
            logger.warning("データ不足のため除外: %s (%s件)", ticker, len(prices))
            continue

        ma20 = prices.rolling(20).mean()
        ma60 = prices.rolling(60).mean()
        rsi = calculate_rsi(prices)
        daily_returns = prices.pct_change().dropna()
        latest = prices.iloc[-1]
        latest_ma20 = ma20.iloc[-1]
        latest_ma60 = ma60.iloc[-1]

        ticker_volume = (
            pd.to_numeric(volume[ticker], errors="coerce").reindex(prices.index)
            if ticker in volume.columns
            else pd.Series(index=prices.index, dtype=float)
        )
        latest_volume = ticker_volume.iloc[-1] if len(ticker_volume) else np.nan
        prior_volume_average = ticker_volume.shift(1).rolling(20).mean().iloc[-1]
        volume_ratio = (
            latest_volume / prior_volume_average
            if pd.notna(latest_volume) and pd.notna(prior_volume_average) and prior_volume_average > 0
            else np.nan
        )

        previous_distance = (
            prices.iloc[-2] / ma20.iloc[-2] - 1
            if pd.notna(ma20.iloc[-2]) and ma20.iloc[-2] != 0
            else np.nan
        )
        latest_distance = latest / latest_ma20 - 1
        attributes = metadata[ticker]
        latest_rsi = safe_number(rsi.iloc[-1], 2)

        records.append(
            {
                "ticker": ticker,
                "code": attributes["code"],
                "name": attributes["name"],
                "category": attributes["category"],
                "inbound_weight": int(attributes["inbound_weight"]),
                "as_of_date": prices.index[-1].date().isoformat(),
                "close": safe_number(latest),
                "return_1d_pct": safe_return(prices, 1),
                "return_5d_pct": safe_return(prices, 5),
                "return_20d_pct": safe_return(prices, 20),
                "return_60d_pct": safe_return(prices, 60),
                "ma20": safe_number(latest_ma20),
                "ma60": safe_number(latest_ma60),
                "distance_ma20_pct": safe_number(latest_distance * 100),
                "distance_ma60_pct": safe_number((latest / latest_ma60 - 1) * 100),
                "ma20_cross_up": bool(previous_distance <= 0 < latest_distance),
                "ma20_cross_down": bool(previous_distance >= 0 > latest_distance),
                "rsi14": latest_rsi,
                "rsi_state": classify_rsi(latest_rsi),
                "volatility20_pct": safe_number(daily_returns.tail(20).std() * np.sqrt(252) * 100),
                "volume": safe_number(latest_volume, 0),
                "volume_20d_avg": safe_number(prior_volume_average, 0),
                "volume_ratio": safe_number(volume_ratio, 3),
                "is_20d_high": bool(latest >= prices.tail(20).max()),
                "up_streak_days": consecutive_up_days(prices),
            }
        )

    return pd.DataFrame.from_records(records)

