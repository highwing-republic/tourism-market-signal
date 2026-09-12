from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.gemini_analysis import analyze_targets, create_client
from app.indicators import calculate_metrics
from app.market_data import (
    download_market_data,
    load_drivers,
    load_universe,
    retain_completed_closes_before,
    summarize_drivers,
)
from app.report import render_reports
from app.scoring import detect_changes, score_attention, select_research_targets
from app.settings import Settings
from app.storage import build_snapshot, load_previous_snapshot, save_snapshot


def configure_logging(settings: Settings) -> None:
    settings.ensure_directories()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    file_handler = logging.FileHandler(settings.logs_dir / "daily-report.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(stream)
    root.addHandler(file_handler)


def run(settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    configure_logging(settings)
    logger = logging.getLogger(__name__)
    report_date = datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat()

    universe = load_universe(settings.universe_file)
    drivers = load_drivers(settings.drivers_file)
    stock_frames = download_market_data(
        universe["ticker"].tolist(),
        period=settings.lookback_period,
        retry_count=settings.retry_count,
        cache_dir=settings.market_cache_dir,
        repair=True,
    )
    driver_frames = download_market_data(
        [item["ticker"] for item in drivers],
        period=settings.lookback_period,
        retry_count=settings.retry_count,
        cache_dir=settings.market_cache_dir,
        repair=False,
    )
    stock_frames = retain_completed_closes_before(stock_frames, report_date)
    driver_frames = retain_completed_closes_before(driver_frames, report_date)

    metrics = calculate_metrics(stock_frames.close, stock_frames.volume, universe)
    if metrics.empty:
        raise RuntimeError("分析可能な銘柄がありません")
    previous = load_previous_snapshot(settings.data_dir, settings.history_dir, report_date)
    scored = detect_changes(score_attention(metrics), previous)
    driver_summary = summarize_drivers(driver_frames.close, drivers)

    candidate_limit = max(settings.top_n, settings.llm_max_targets)
    candidates = select_research_targets(scored, candidate_limit)
    llm_targets = candidates.head(settings.llm_max_targets)
    client = create_client(settings.gemini_api_key)
    analyses = analyze_targets(
        client,
        llm_targets,
        driver_summary,
        model=settings.gemini_model,
        retry_count=settings.retry_count,
    )
    analysis_completed_at = datetime.now(timezone.utc).isoformat(timespec="seconds") if analyses else None
    research_targets = candidates.head(settings.top_n)["ticker"].tolist()
    payload = build_snapshot(
        scored,
        driver_summary,
        analyses,
        report_date=report_date,
        model=settings.gemini_model,
        universe_size=len(universe),
        research_targets=research_targets,
        stock_retrieved_at=stock_frames.retrieved_at,
        driver_retrieved_at=driver_frames.retrieved_at,
        analysis_completed_at=analysis_completed_at,
    )
    latest_path, history_path = save_snapshot(payload, settings.data_dir, settings.history_dir)
    html_paths = render_reports(payload, settings.docs_dir)
    logger.info(
        "生成完了: date=%s stocks=%s ai=%s json=%s html=%s",
        payload["report_date"],
        len(payload["stocks"]),
        len(analyses),
        history_path,
        len(html_paths),
    )
    return {
        "payload": payload,
        "latest_path": latest_path,
        "history_path": history_path,
        "html_paths": html_paths,
    }


if __name__ == "__main__":
    run()
