import numpy as np
import pandas as pd

from app.indicators import calculate_metrics, calculate_rsi, classify_rsi


def test_rsi_and_state_boundaries() -> None:
    rising = pd.Series(np.arange(1, 40, dtype=float))
    assert calculate_rsi(rising).iloc[-1] == 100
    assert classify_rsi(29.9) == "売られ過ぎ"
    assert classify_rsi(30) == "弱い"
    assert classify_rsi(60) == "強い"
    assert classify_rsi(70.1) == "過熱"


def test_metrics_include_prior_volume_average_and_signals() -> None:
    dates = pd.date_range("2026-01-01", periods=80, freq="B")
    close = pd.DataFrame({"TEST.T": np.arange(100, 180, dtype=float)}, index=dates)
    volume = pd.DataFrame({"TEST.T": [100.0] * 79 + [300.0]}, index=dates)
    universe = pd.DataFrame([{"ticker": "TEST.T", "code": "0000", "name": "テスト", "category": "ホテル・宿泊", "inbound_weight": 5}])
    result = calculate_metrics(close, volume, universe).iloc[0]
    assert result["volume_20d_avg"] == 100
    assert result["volume_ratio"] == 3
    assert bool(result["is_20d_high"])
    assert result["up_streak_days"] == 79
    assert result["rsi_state"] == "過熱"

