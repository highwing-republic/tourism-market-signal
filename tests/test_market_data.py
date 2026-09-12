from unittest.mock import patch

import pandas as pd

from app.market_data import MarketFrames, download_market_data, retain_completed_closes_before


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
    assert download.call_args_list[0].kwargs["auto_adjust"] is False
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


def test_retry_preserves_actual_acquisition_time_per_ticker():
    from datetime import datetime, timezone
    batch_time = datetime(2026, 9, 6, 22, 30, tzinfo=timezone.utc)
    retry_time = datetime(2026, 9, 6, 22, 32, tzinfo=timezone.utc)
    with patch('app.market_data.yf.download') as download, patch('app.market_data.datetime') as clock:
        download.side_effect = [_download_result(['AAA']), pd.DataFrame(), _download_result(['BBB'])]
        clock.now.side_effect = [batch_time, retry_time]
        frames = download_market_data(['AAA', 'BBB'], retry_count=1)
    assert frames.retrieved_at == {'AAA': batch_time.isoformat(), 'BBB': retry_time.isoformat()}


def test_missing_data_does_not_get_an_acquisition_time():
    with patch('app.market_data.yf.download') as download:
        download.side_effect = [_download_result(['AAA']), pd.DataFrame(), pd.DataFrame()]
        frames = download_market_data(['AAA', 'MISSING'], retry_count=1)
    assert set(frames.retrieved_at) == {'AAA'}


def test_report_uses_only_closes_before_its_calendar_date():
    dates = pd.to_datetime(["2026-09-10", "2026-09-11", "2026-09-12"])
    frames = MarketFrames(
        close=pd.DataFrame({"AAA": [100.0, 105.0, 999.0]}, index=dates),
        volume=pd.DataFrame({"AAA": [1000.0, 1100.0, 9999.0]}, index=dates),
        retrieved_at={"AAA": "2026-09-12T21:00:10+00:00"},
    )

    completed = retain_completed_closes_before(frames, "2026-09-12")

    assert completed.close.index.max() == pd.Timestamp("2026-09-11")
    assert completed.close.iloc[-1, 0] == 105.0
    assert completed.volume.iloc[-1, 0] == 1100.0
    assert completed.retrieved_at == frames.retrieved_at
