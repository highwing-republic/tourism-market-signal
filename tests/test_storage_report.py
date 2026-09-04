import json

from app.report import render_reports
from app.storage import save_snapshot


def _payload() -> dict:
    return {
        "schema_version": 1,
        "report_date": "2026-09-01",
        "generated_at": "2026-09-01T07:30:00+09:00",
        "model": "gemini-2.5-flash",
        "analysis_status": "skipped_or_unavailable",
        "research_targets": ["TEST.T"],
        "data_quality": {"configured_stocks": 50, "analyzed_stocks": 1, "missing_stocks": 49},
        "market_drivers": {"^N225": {"ticker": "^N225", "name": "日経平均", "group": "common", "status": "ok", "return_5d_pct": 1.2}},
        "stocks": [{
            "ticker": "TEST.T", "code": "0000", "name": "A&B <テスト>", "category": "ホテル",
            "rank": 1, "previous_rank": None, "attention_score": 80.0, "change_score": 0.0,
            "return_20d_pct": 4.2, "return_5d_pct": 1.1, "close": 1000,
            "distance_ma20_pct": 2.0, "rsi14": 65, "rsi_state": "強い", "volume_ratio": 1.5,
            "signals": [], "analysis": None,
        }],
        "disclaimer": "test",
    }


def test_snapshot_is_valid_json_and_report_escapes_html(tmp_path) -> None:
    data_dir = tmp_path / "data"
    history_dir = data_dir / "history"
    latest, history = save_snapshot(_payload(), data_dir, history_dir)
    assert json.loads(latest.read_text(encoding="utf-8"))["report_date"] == "2026-09-01"
    assert history.exists()

    docs_dir = tmp_path / "docs"
    paths = render_reports(_payload(), docs_dir)
    assert len(paths) == 3
    index = (docs_dir / "index.html").read_text(encoding="utf-8")
    assert "A&amp;B &lt;テスト&gt;" in index
    assert (docs_dir / "reports" / "2026-09-01" / "test-t.html").exists()

