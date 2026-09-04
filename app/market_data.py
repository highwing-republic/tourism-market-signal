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


def _download_once(
    tickers: list[str],
    *,
    period: str,
    repair: bool,
    threads: bool,
) -> MarketFrames:
    data = yf.download(
        tickers=tickers,
        period=period,
        interval="1d",
        auto_adjust=True,
        actions=False,
        repair=repair,
        progress=False,
        threads=threads,
        group_by="column",
        timeout=30,
    )
    if data is None or data.empty:
        return MarketFrames(close=pd.DataFrame(), volume=pd.DataFrame())
    close = _extract_field(data, "Close", tickers)
    volume = _extract_field(data, "Volume", tickers)
    return MarketFrames(
        close=close.sort_index().dropna(axis=1, how="all"),
        volume=volume.sort_index().dropna(axis=1, how="all"),
    )


def _has_prices(close: pd.DataFrame, ticker: str) -> bool:
    return ticker in close.columns and not close[ticker].dropna().empty


def _merge_frame_columns(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if not frame.empty]
    if not usable:
        return pd.DataFrame()
    merged = pd.concat(usable, axis=1).sort_index()
    if merged.columns.duplicated().any():
        merged = merged.T.groupby(level=0, sort=False).first().T
    return merged


def download_market_data(
    tickers: list[str],
    *,
    period: str = "1y",
    retry_count: int = 3,
    cache_dir: Path | None = None,
    repair: bool = True,
    retry_missing_individually: bool = True,
) -> MarketFrames:
    unique_tickers = list(dict.fromkeys(tickers))
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir))
    batch_frames = MarketFrames(close=pd.DataFrame(), volume=pd.DataFrame())
    last_error: Exception | None = None
    for attempt in range(1, retry_count + 1):
        try:
            logger.info("市場データ取得: %s系列（%s/%s）", len(unique_tickers), attempt, retry_count)
            batch_frames = _download_once(
                unique_tickers,
                period=period,
                repair=repair,
                threads=True,
            )
            if batch_frames.close.empty:
                raise RuntimeError("yfinance の結果が空です")
            break
        except Exception as exc:  # network/library errors vary by yfinance version
            last_error = exc
            logger.warning("市場データ取得失敗（%s/%s）: %s", attempt, retry_count, exc)
            if attempt < retry_count:
                time.sleep(attempt * 3)

    missing = [ticker for ticker in unique_tickers if not _has_prices(batch_frames.close, ticker)]
    recovered: list[MarketFrames] = []
    if missing and retry_missing_individually:
        logger.warning(
            "一括取得で欠落した%s系列を個別再取得します: %s",
            len(missing),
            ", ".join(missing),
        )
        for ticker in missing:
            ticker_frame: MarketFrames | None = None
            repair_modes = list(dict.fromkeys([repair, not repair]))
            for repair_mode in repair_modes:
                try:
                    candidate = _download_once(
                        [ticker],
                        period=period,
                        repair=repair_mode,
                        threads=False,
                    )
                    if _has_prices(candidate.close, ticker):
                        ticker_frame = candidate
                        logger.info(
                            "個別再取得成功: %s (repair=%s)", ticker, repair_mode
                        )
                        break
                except Exception as exc:  # keep trying the alternate repair mode
                    logger.warning(
                        "個別再取得失敗: %s (repair=%s): %s",
                        ticker,
                        repair_mode,
                        exc,
                    )
            if ticker_frame is not None:
                recovered.append(ticker_frame)

    close = _merge_frame_columns([batch_frames.close, *(frame.close for frame in recovered)])
    volume = _merge_frame_columns([batch_frames.volume, *(frame.volume for frame in recovered)])
    still_missing = [ticker for ticker in unique_tickers if not _has_prices(close, ticker)]
    if still_missing:
        logger.warning(
            "市場データを取得できなかった系列: %s", ", ".join(still_missing)
        )
    if close.empty:
        raise RuntimeError(f"市場データ取得に失敗しました: {last_error}")
    return MarketFrames(close=close, volume=volume)


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
