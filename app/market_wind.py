from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

import yaml


STATE_LABELS = {
    "strong_tailwind": "強い追い風", "tailwind": "追い風", "calm": "凪",
    "mixed": "方向感混在", "headwind": "逆風", "strong_headwind": "強い逆風",
    "insufficient": "判定材料不足",
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _median(items: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite(item.get(key)) for item in items]
    usable = [item for item in values if item is not None]
    return median(usable) if usable else None


def _share(items: list[dict[str, Any]], key: str) -> float | None:
    values = [_finite(item.get(key)) for item in items]
    usable = [item for item in values if item is not None]
    return sum(item > 0 for item in usable) / len(usable) if usable else None


def _driver(drivers: dict[str, Any], ticker: str, field: str) -> float | None:
    return _finite((drivers.get(ticker) or {}).get(field))


def _public_available_as_of(public: dict[str, Any], report_date: str) -> dict[str, Any]:
    """Exclude statistics that were not yet published on the report date."""
    cutoff = datetime.strptime(report_date, "%Y-%m-%d").date()
    available = deepcopy(public)
    sources = {}
    for key, source in (public.get("sources") or {}).items():
        try:
            published = datetime.strptime(str(source.get("published_date")), "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if published <= cutoff:
            sources[key] = source
    available["sources"] = sources
    available["indicators"] = {
        key: item for key, item in (public.get("indicators") or {}).items()
        if item.get("source_key") in sources
    }
    return available


def derive_metrics(stocks: list[dict[str, Any]], drivers: dict[str, Any], public: dict[str, Any]) -> dict[str, float | None]:
    airline = [item for item in stocks if item.get("category") in {"航空", "空港"}]
    indicators = public.get("indicators") or {}
    return {
        "positive_5d_share": _share(stocks, "return_5d_pct"),
        "median_5d": _median(stocks, "return_5d_pct"),
        "positive_20d_share": _share(stocks, "return_20d_pct"),
        "median_20d": _median(stocks, "return_20d_pct"),
        "positive_60d_share": _share(stocks, "return_60d_pct"),
        "median_60d": _median(stocks, "return_60d_pct"),
        "above_ma20_share": _share(stocks, "distance_ma20_pct"),
        "above_ma60_share": _share(stocks, "distance_ma60_pct"),
        "airline_median_5d": _median(airline, "return_5d_pct"),
        "nikkei_5d": _driver(drivers, "^N225", "return_5d_pct"),
        "sp500_5d": _driver(drivers, "^GSPC", "return_5d_pct"),
        "vix_5d": _driver(drivers, "^VIX", "return_5d_pct"),
        "oil_5d": _driver(drivers, "CL=F", "return_5d_pct"),
        "fx_5d": _driver(drivers, "JPY=X", "return_5d_pct"),
        "visitor_yoy": _finite((indicators.get("visitor_arrivals") or {}).get("yoy_pct")),
        "lodging_12m_yoy": _finite((indicators.get("total_guest_nights_12m") or {}).get("yoy_pct")),
        "occupancy_rate": _finite((indicators.get("occupancy_rate") or {}).get("value")),
        "spend_yoy": _finite((indicators.get("spend_per_visitor") or {}).get("yoy_pct")),
    }


def _normalized(value: float, neutral: float, scale: float, direction: float) -> float:
    return max(-100.0, min(100.0, ((value - neutral) / scale) * 100.0 * direction))


def _state(score: float, normalized: list[float]) -> str:
    if score >= 55:
        return "strong_tailwind"
    if score >= 25:
        return "tailwind"
    if score <= -55:
        return "strong_headwind"
    if score <= -25:
        return "headwind"
    if normalized and max(normalized) - min(normalized) >= 110:
        return "mixed"
    return "calm"


def _public_periods(public: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"name": item.get("source_name", key), "period": item.get("reference_period") or "未記録",
         "published_date": item.get("published_date") or "未記録", "url": item.get("source_url") or "",
         "release_type": item.get("release_type") or ""}
        for key, item in (public.get("sources") or {}).items()
    ]


def calculate_market_wind(
    stocks: list[dict[str, Any]], drivers: dict[str, Any], public: dict[str, Any],
    *, report_date: str, config_path: Path,
) -> dict[str, Any]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    public_as_of = _public_available_as_of(public, report_date)
    metrics = derive_metrics(stocks, drivers, public_as_of)
    market_dates = sorted({
        str(item.get("as_of_date")) for item in [*stocks, *drivers.values()] if item.get("as_of_date")
    })
    market_basis_date = market_dates[-1] if market_dates else None
    horizons: dict[str, Any] = {}
    for key, horizon in config["horizons"].items():
        contributions = []
        total_weight = sum(float(item["weight"]) for item in horizon["signals"])
        usable_weight = 0.0
        for item in horizon["signals"]:
            value = metrics.get(item["key"])
            if value is None:
                continue
            weight = float(item["weight"])
            if item["key"] == "lodging_12m_yoy" and public_as_of.get("comparability", {}).get("lodging_2026_boundary"):
                weight *= float(public_as_of["comparability"].get("lodging_growth_weight_multiplier", 0.5))
            norm = _normalized(value, float(item.get("neutral", 0)), float(item["scale"]), float(item.get("direction", 1)))
            usable_weight += weight
            contributions.append({
                "indicator": item["key"], "label": item["label"], "raw_value": round(value, 3),
                "unit": item.get("unit", "%"), "normalized": round(norm, 1), "weight": weight,
            })
        coverage = usable_weight / total_weight if total_weight else 0
        if usable_weight:
            for item in contributions:
                item["contribution"] = round(item["normalized"] * item["weight"] / usable_weight, 1)
            score = round(sum(item["contribution"] for item in contributions), 1)
        else:
            score = 0.0
        state = "insufficient" if coverage < 0.5 else _state(score, [item["normalized"] for item in contributions])
        comparability = 10 if public_as_of.get("comparability", {}).get("lodging_2026_boundary") else 20
        freshness = 15 if public_as_of.get("is_stale") else 30
        confidence = min(100, round(coverage * 50 + freshness + comparability))
        confidence_label = "高" if confidence >= 80 else "中" if confidence >= 60 else "低"
        positive = sorted((item for item in contributions if item["contribution"] > 0), key=lambda x: x["contribution"], reverse=True)[:2]
        negative = sorted((item for item in contributions if item["contribution"] < 0), key=lambda x: x["contribution"])[:2]
        if state == "insufficient":
            summary = "判定に必要なデータが不足しています。取得済みの指標だけを表示しています。"
        elif positive and negative:
            summary = f'{negative[0]["label"]}が重荷になる一方、{positive[0]["label"]}が下支えしています。'
        elif positive:
            summary = f'{positive[0]["label"]}を中心に、観光マーケットへ追い風が確認できます。'
        elif negative:
            summary = f'{negative[0]["label"]}を中心に、観光マーケットへの逆風が確認できます。'
        else:
            summary = "主要指標に大きな方向感は見られません。"
        horizons[key] = {
            "label": horizon["label"], "period": horizon["period"], "score": score,
            "state": state, "state_label": STATE_LABELS[state], "confidence": confidence,
            "confidence_label": confidence_label, "market_basis_date": market_basis_date,
            "coverage": round(coverage * 100), "summary": summary,
            "positive_factors": positive, "negative_factors": negative,
            "missing_indicators": [item["label"] for item in horizon["signals"] if metrics.get(item["key"]) is None],
        }
    labels = [f'{item["label"]}は{item["state_label"]}' for item in horizons.values()]
    return {
        "methodology_version": "1.0.0", "calculated_for": report_date,
        "overall_summary": "、".join(labels) + "です。",
        "horizons": horizons, "public_statistics": public_as_of,
        "source_periods": _public_periods(public_as_of),
        "methodology_note": (public_as_of.get("comparability") or {}).get("note"),
    }
