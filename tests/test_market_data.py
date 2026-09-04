from unittest.mock import patch

import pandas as pd

from app.market_data import download_market_data


def _download_result(tickers: list[str]) -> pd.DataFrame:
    dates = pd.date_range("2026-08-01", periods=30, freq="B")
    columns = pd.MultiIndex.from_product(
        [["Close", "Volume"], tickers], names=["Price", "Ticker"]
    )
    values = []
    for index in range(len(dates)):
        values.append(
            [100.0 + index for _ in tickers]
            + [1000.0 + index for _ in tickers]
        )
    return pd.DataFrame(values, index=dates, columns=columns)


def test_missing_ticker_is_retried_with_alternate_repair_mode() -> None:
    batch = _download_result(["AAA"])
    recovered = _download_result(["BBB"])

    with patch("app.market_data.yf.download") as download:
        download.side_effect = [batch, pd.DataFrame(), recovered]
        frames = download_market_data(
            ["AAA", "BBB"], retry_count=1, repair=True
        )

    assert list(frames.close.columns) == ["AAA", "BBB"]
    assert download.call_count == 3
    assert download.call_args_list[1].kwargs["repair"] is True
    assert download.call_args_list[2].kwargs["repair"] is False
    assert download.call_args_list[1].kwargs["threads"] is False


def test_partial_result_is_returned_when_one_ticker_stays_unavailable() -> None:
    batch = _download_result(["AAA"])

    with patch("app.market_data.yf.download") as download:
        download.side_effect = [batch, pd.DataFrame(), pd.DataFrame()]
        frames = download_market_data(
            ["AAA", "MISSING"], retry_count=1, repair=False
        )

    assert list(frames.close.columns) == ["AAA"]
