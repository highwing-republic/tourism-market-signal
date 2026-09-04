from __future__ import annotations

from typing import Any

import pandas as pd


def percentile_score(series: pd.Series, *, missing_score: float = 50.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    ranked = numeric.rank(pct=True, method="average") * 100
    return ranked.fillna(missing_score)


def score_attention(metrics: pd.DataFrame) -> pd.DataFrame:
    """Calculate an explainable cross-sectional attention score.

    RSI is intentionally excluded: it is reported as a market state so an
    overbought stock is not automatically rewarded or punished.
    """
    if metrics.empty:
        return metrics.copy()
    frame = metrics.copy()
    frame["score_return_20d"] = percentile_score(frame["return_20d_pct"])
    frame["score_return_5d"] = percentile_score(frame["return_5d_pct"])
    frame["score_ma20"] = percentile_score(frame["distance_ma20_pct"])
    frame["score_ma60"] = percentile_score(frame["distance_ma60_pct"])
    frame["score_volume"] = percentile_score(frame["volume_ratio"], missing_score=0)
    frame["inbound_score"] = (
        pd.to_numeric(frame["inbound_weight"], errors="coerce").fillna(3).clip(1, 5) * 20
    )
    frame["attention_score"] = (
        frame["score_return_20d"] * 0.30
        + frame["score_return_5d"] * 0.20
        + frame["score_ma20"] * 0.15
        + frame["score_ma60"] * 0.10
        + frame["score_volume"] * 0.10
        + frame["inbound_score"] * 0.15
    ).round(2)
    frame = frame.sort_values(
        ["attention_score", "return_20d_pct"], ascending=[False, False]
    ).reset_index(drop=True)
    frame["rank"] = range(1, len(frame) + 1)
    return frame


def _previous_stock_map(previous: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not previous:
        return {}
    return {
        item["ticker"]: item
        for item in previous.get("stocks", [])
        if isinstance(item, dict) and item.get("ticker")
    }


def detect_changes(
    scored: pd.DataFrame,
    previous: dict[str, Any] | None,
) -> pd.DataFrame:
    previous_map = _previous_stock_map(previous)
    has_previous = bool(previous_map)
    records: list[dict[str, Any]] = []

    for row in scored.to_dict("records"):
        prior = previous_map.get(row["ticker"])
        prior_rank = int(prior["rank"]) if prior and prior.get("rank") is not None else None
        prior_attention = (
            float(prior["attention_score"])
            if prior and prior.get("attention_score") is not None
            else None
        )
        rank_change = prior_rank - int(row["rank"]) if prior_rank is not None else None
        attention_change = (
            round(float(row["attention_score"]) - prior_attention, 2)
            if prior_attention is not None
            else None
        )

        signals: list[str] = []
        new_top_10 = bool(prior_rank and prior_rank > 10 and int(row["rank"]) <= 10)
        if new_top_10:
            signals.append("今日初めてTOP10入り")
        if rank_change is not None and rank_change >= 3:
            signals.append(f"順位が{rank_change}位上昇")
        elif rank_change is not None and rank_change <= -3:
            signals.append(f"順位が{abs(rank_change)}位下落")
        if row.get("ma20_cross_up"):
            signals.append("20日移動平均を上抜け")
        if row.get("ma20_cross_down"):
            signals.append("20日移動平均を下抜け")
        if row.get("volume_ratio") is not None and float(row["volume_ratio"]) >= 2:
            signals.append("出来高が20日平均の2倍以上")
        if row.get("up_streak_days", 0) >= 3:
            signals.append(f"{int(row['up_streak_days'])}日連続上昇")
        if row.get("is_20d_high"):
            signals.append("20日高値を更新")

        if has_previous:
            change_score = 0.0
            if rank_change is not None:
                change_score += min(abs(rank_change) * 2.5, 25)
            if attention_change is not None:
                change_score += min(abs(attention_change) * 1.5, 20)
            change_score += 15 if new_top_10 else 0
            change_score += 15 if row.get("ma20_cross_up") or row.get("ma20_cross_down") else 0
            change_score += 10 if row.get("volume_ratio") is not None and float(row["volume_ratio"]) >= 2 else 0
            change_score += 10 if row.get("is_20d_high") else 0
            change_score += 5 if row.get("up_streak_days", 0) >= 3 else 0
            change_score = min(change_score, 100)
        else:
            change_score = 0.0

        row.update(
            {
                "previous_rank": prior_rank,
                "rank_change": rank_change,
                "attention_change": attention_change,
                "change_score": round(change_score, 2),
                "signals": signals,
            }
        )
        row["priority_score"] = round(
            float(row["attention_score"])
            if not has_previous
            else float(row["attention_score"]) * 0.70 + change_score * 0.30,
            2,
        )
        records.append(row)

    return pd.DataFrame.from_records(records).sort_values("rank").reset_index(drop=True)


def select_research_targets(scored: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    if scored.empty:
        return scored.copy()
    changed = scored[scored["signals"].map(bool)]
    candidate_pool = changed if len(changed) >= limit else scored
    return candidate_pool.sort_values(
        ["priority_score", "attention_score"], ascending=[False, False]
    ).head(limit)

