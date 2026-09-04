from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


logger = logging.getLogger(__name__)
JST = ZoneInfo("Asia/Tokyo")


def to_jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return None if not math.isfinite(number) else number
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return value


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("過去データを読めませんでした: %s (%s)", path, exc)
        return None


def load_previous_snapshot(
    data_dir: Path,
    history_dir: Path,
    current_date: str,
) -> dict[str, Any] | None:
    latest_path = data_dir / "latest.json"
    if latest_path.exists():
        latest = _read_json(latest_path)
        if latest and str(latest.get("report_date", "")) < current_date:
            return latest

    for path in sorted(history_dir.glob("*.json"), reverse=True):
        if path.stem < current_date:
            previous = _read_json(path)
            if previous:
                return previous
    return None


def build_snapshot(
    scored: pd.DataFrame,
    driver_summary: dict[str, dict],
    analyses: dict[str, Any],
    *,
    model: str,
    universe_size: int,
    research_targets: list[str],
) -> dict[str, Any]:
    report_date = str(scored["as_of_date"].max())
    stocks = to_jsonable(scored.to_dict("records"))
    for stock in stocks:
        analysis = analyses.get(stock["ticker"])
        stock["analysis"] = (
            to_jsonable(analysis.model_dump())
            if analysis is not None and hasattr(analysis, "model_dump")
            else to_jsonable(analysis)
        )

    missing = universe_size - len(stocks)
    return {
        "schema_version": 1,
        "title": "観光株シグナル / Tourism Market Signal",
        "report_date": report_date,
        "generated_at": datetime.now(JST).isoformat(timespec="seconds"),
        "timezone": "Asia/Tokyo",
        "model": model,
        "analysis_status": "complete" if analyses else "skipped_or_unavailable",
        "research_targets": research_targets,
        "data_quality": {
            "configured_stocks": universe_size,
            "analyzed_stocks": len(stocks),
            "missing_stocks": missing,
        },
        "market_drivers": to_jsonable(driver_summary),
        "stocks": stocks,
        "disclaimer": "調査支援を目的とした情報であり、特定銘柄の売買を推奨しません。",
    }


def save_snapshot(payload: dict[str, Any], data_dir: Path, history_dir: Path) -> tuple[Path, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    latest_path = data_dir / "latest.json"
    history_path = history_dir / f"{payload['report_date']}.json"
    latest_path.write_text(text, encoding="utf-8")
    history_path.write_text(text, encoding="utf-8")
    return latest_path, history_path

