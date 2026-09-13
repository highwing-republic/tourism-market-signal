import json
from pathlib import Path

from app.market_wind import calculate_market_wind
from app.public_statistics import refresh_public_statistics, validate_public_statistics


CONFIG = Path(__file__).resolve().parents[1] / "config" / "market_wind.yml"


def _stocks(change: float) -> list[dict]:
    return [
        {
            "category": "航空" if index < 3 else "ホテル・宿泊",
            "return_5d_pct": change,
            "return_20d_pct": change * 2,
            "return_60d_pct": change * 4,
            "distance_ma20_pct": change,
            "distance_ma60_pct": change,
        }
        for index in range(20)
    ]


def _public(visitor_yoy: float) -> dict:
    return {
        "schema_version": 1,
        "sources": {
            "jnto_visitors": {"source_name": "JNTO", "reference_period": "2026-07", "published_date": "2026-08-19"},
            "lodging_statistics": {"source_name": "観光庁", "reference_period": "2026-06", "published_date": "2026-08-31"},
        },
        "indicators": {
            "visitor_arrivals": {"value": 100, "yoy_pct": visitor_yoy, "source_key": "jnto_visitors"},
            "total_guest_nights_12m": {"value": 100, "yoy_pct": visitor_yoy, "source_key": "lodging_statistics"},
            "occupancy_rate": {"value": 70, "yoy_pct": None, "source_key": "lodging_statistics"},
        },
        "comparability": {"lodging_2026_boundary": True, "lodging_growth_weight_multiplier": 0.5},
        "is_stale": False,
    }


def test_market_wind_classifies_positive_and_negative_conditions() -> None:
    positive_drivers = {
        "^N225": {"return_5d_pct": 4}, "^VIX": {"return_5d_pct": -15},
        "CL=F": {"return_5d_pct": -8},
    }
    tailwind = calculate_market_wind(
        _stocks(4), positive_drivers, _public(12), report_date="2026-09-11", config_path=CONFIG,
    )
    assert tailwind["horizons"]["short"]["state"] in {"tailwind", "strong_tailwind"}
    assert tailwind["horizons"]["long"]["score"] > 0

    negative_drivers = {
        "^N225": {"return_5d_pct": -4}, "^VIX": {"return_5d_pct": 20},
        "CL=F": {"return_5d_pct": 10},
    }
    headwind = calculate_market_wind(
        _stocks(-4), negative_drivers, _public(-12), report_date="2026-09-11", config_path=CONFIG,
    )
    assert headwind["horizons"]["short"]["state"] in {"headwind", "strong_headwind"}
    assert headwind["horizons"]["long"]["score"] < 0


def test_future_publication_is_not_used_for_historical_report() -> None:
    public = _public(100)
    public["sources"]["jnto_visitors"]["published_date"] = "2026-10-01"
    result = calculate_market_wind(
        _stocks(0), {}, public, report_date="2026-09-11", config_path=CONFIG,
    )
    used = result["market_wind"] if "market_wind" in result else result
    assert "jnto_visitors" not in used["public_statistics"]["sources"]
    for horizon in used["horizons"].values():
        assert all(item["indicator"] != "visitor_yoy" for item in horizon["positive_factors"])


def test_public_statistics_uses_cached_source_when_one_refresh_fails(tmp_path, monkeypatch) -> None:
    cached = _public(4)
    cached["generated_at"] = "2026-09-01T06:00:00+09:00"
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(cached, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr("app.public_statistics._jnto_statistics", lambda _session: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr("app.public_statistics._lodging_statistics", lambda _session: (cached["sources"]["lodging_statistics"], {
        "total_guest_nights_12m": cached["indicators"]["total_guest_nights_12m"],
        "occupancy_rate": cached["indicators"]["occupancy_rate"],
    }))
    monkeypatch.setattr("app.public_statistics._consumption_statistics", lambda _session: (_ for _ in ()).throw(RuntimeError("offline")))

    refreshed = refresh_public_statistics(path)
    validate_public_statistics(refreshed)
    assert refreshed["is_stale"] is True
    assert refreshed["indicators"]["visitor_arrivals"]["value"] == 100
    assert "jnto_visitors" in refreshed["update_errors"]
