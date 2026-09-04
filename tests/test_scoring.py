import pandas as pd

from app.scoring import detect_changes, score_attention, select_research_targets


def test_attention_score_ranks_stronger_stock_first() -> None:
    metrics = pd.DataFrame([
        {"ticker": "HIGH.T", "return_20d_pct": 12, "return_5d_pct": 5, "distance_ma20_pct": 4, "distance_ma60_pct": 8, "volume_ratio": 2.2, "inbound_weight": 5},
        {"ticker": "MID.T", "return_20d_pct": 1, "return_5d_pct": 0, "distance_ma20_pct": 0, "distance_ma60_pct": 1, "volume_ratio": 1, "inbound_weight": 3},
        {"ticker": "LOW.T", "return_20d_pct": -10, "return_5d_pct": -4, "distance_ma20_pct": -5, "distance_ma60_pct": -8, "volume_ratio": 0.5, "inbound_weight": 1},
    ])
    scored = score_attention(metrics)
    assert scored.iloc[0]["ticker"] == "HIGH.T"
    assert scored.iloc[-1]["ticker"] == "LOW.T"


def test_change_detection_flags_new_top_10_and_volume_surge() -> None:
    today = pd.DataFrame([{"ticker": "TEST.T", "rank": 2, "attention_score": 82.0, "ma20_cross_up": True, "ma20_cross_down": False, "volume_ratio": 2.3, "is_20d_high": True, "up_streak_days": 3}])
    previous = {"stocks": [{"ticker": "TEST.T", "rank": 12, "attention_score": 65.0}]}
    changed = detect_changes(today, previous).iloc[0]
    assert changed["rank_change"] == 10
    assert "今日初めてTOP10入り" in changed["signals"]
    assert "出来高が20日平均の2倍以上" in changed["signals"]
    assert changed["change_score"] > 50


def test_first_run_uses_attention_without_artificial_change() -> None:
    today = pd.DataFrame([{"ticker": "A.T", "rank": 1, "attention_score": 80.0, "ma20_cross_up": False, "ma20_cross_down": False, "volume_ratio": 1, "is_20d_high": False, "up_streak_days": 0}])
    result = detect_changes(today, None)
    assert result.iloc[0]["change_score"] == 0
    assert result.iloc[0]["priority_score"] == 80
    assert select_research_targets(result, 1).iloc[0]["ticker"] == "A.T"
