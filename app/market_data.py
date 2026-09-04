from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml
import yfinance as yf


logger = logging.getLogger(__name__)

REQUIRED_UNIVERSE_COLUMNS = {
    "ticker",
    "code",
    "name",
    "category",
    "inbound_weight",
}


@dataclass(frozen=True)
class MarketFrames:
    close: pd.DataFrame
    volume: pd.DataFrame


def load_universe(path: Path) -> pd.DataFrame:
    universe = pd.read_csv(
        path,
        dtype={
            "ticker": str,
            "code": str,
            "name": str,
            "category": str,
            "inbound_weight": int,
        },
    )
    missing = REQUIRED_UNIVERSE_COLUMNS - set(universe.columns)
    if missing:
        raise ValueError(f"universe.csv に必要な列がありません: {sorted(missing)}")
    if universe["ticker"].duplicated().any():
        duplicated = universe.loc[universe["ticker"].duplicated(), "ticker"].tolist()
        raise ValueError(f"ticker が重複しています: {duplicated}")
    if not universe["inbound_weight"].between(1, 5).all():
        raise ValueError("inbound_weight は1〜5で指定してください")
    if len(universe) != 50:
        logger.warning("監視銘柄数が50ではありません: %s", len(universe))
    return universe


def load_drivers(path: Path) -> list[dict[str, str]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    drivers = raw.get("drivers", [])
    if not drivers:
        raise ValueError("drivers.yml に drivers がありません")
    for item in drivers:
        if not {"ticker", "name", "group"} <= set(item):
            raise ValueError("driver には ticker, name, group が必要です")
    return drivers


def _extract_field(
    data: pd.DataFrame,
    field: str,
    requested_tickers: list[str],
) -> pd.DataFrame:
    if not isinstance(data.columns, pd.MultiIndex):
        if field not in data.columns:
            return pd.DataFrame(index=data.index)
        result = data[[field]].copy()
        if len(requested_tickers) == 1:
            result.columns = [requested_tickers[0]]
        return result

    level_zero = set(data.columns.get_level_values(0))
    level_one = set(data.columns.get_level_values(1))
    if field in level_zero:
        result = data[field].copy()
    elif field in level_one:
        result = data.xs(field, axis=1, level=1).copy()
    else:
        return pd.DataFrame(index=data.index)
    if isinstance(result, pd.Series):
        result = result.to_frame(name=requested_tickers[0])
    return result


def download_market_data(
    tickers: list[str],
    *,
    period: str = "1y",
    retry_count: int = 3,
    cache_dir: Path | None = None,
) -> MarketFrames:
    unique_tickers = list(dict.fromkeys(tickers))
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir))
    last_error: Exception | None = None
    for attempt in range(1, retry_count + 1):
        try:
            logger.info("市場データ取得: %s系列（%s/%s）", len(unique_tickers), attempt, retry_count)
            data = yf.download(
                tickers=unique_tickers,
                period=period,
                interval="1d",
                auto_adjust=True,
                actions=False,
                repair=True,
                progress=False,
                threads=True,
                group_by="column",
                timeout=30,
            )
            if data is None or data.empty:
                raise RuntimeError("yfinance の結果が空です")
            close = _extract_field(data, "Close", unique_tickers)
            volume = _extract_field(data, "Volume", unique_tickers)
            close = close.sort_index().dropna(axis=1, how="all")
            volume = volume.sort_index().dropna(axis=1, how="all")
            if close.empty:
                raise RuntimeError("終値を抽出できませんでした")
            return MarketFrames(close=close, volume=volume)
        except Exception as exc:  # network/library errors vary by yfinance version
            last_error = exc
            logger.warning("市場データ取得失敗（%s/%s）: %s", attempt, retry_count, exc)
            if attempt < retry_count:
                time.sleep(attempt * 3)
    raise RuntimeError(f"市場データ取得に失敗しました: {last_error}")


def safe_return(series: pd.Series, periods: int) -> float | None:
    cleaned = series.dropna()
    if len(cleaned) <= periods:
        return None
    start = cleaned.iloc[-periods - 1]
    if start == 0:
        return None
    return round(float((cleaned.iloc[-1] / start - 1) * 100), 4)


def summarize_drivers(
    close: pd.DataFrame,
    drivers: list[dict[str, str]],
) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for driver in drivers:
        ticker = driver["ticker"]
        if ticker not in close.columns or close[ticker].dropna().empty:
            result[ticker] = {**driver, "status": "unavailable"}
            continue
        series = close[ticker].dropna()
        result[ticker] = {
            **driver,
            "status": "ok",
            "as_of_date": series.index[-1].date().isoformat(),
            "close": round(float(series.iloc[-1]), 4),
            "return_1d_pct": safe_return(series, 1),
            "return_5d_pct": safe_return(series, 5),
            "return_20d_pct": safe_return(series, 20),
        }
    return result


def driver_subset_for_category(
    category: str,
    driver_summary: dict[str, dict],
) -> dict[str, dict]:
    allowed_groups = {"common"}
    if category in {"航空", "空港"}:
        allowed_groups.add("aviation")
    else:
        allowed_groups.add("growth")
    return {
        ticker: item
        for ticker, item in driver_summary.items()
        if item.get("group") in allowed_groups
    }
