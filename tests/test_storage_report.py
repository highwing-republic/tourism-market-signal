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
        "market_drivers": {"^N225": {"ticker": "^N225", "name": "日経平均", "group": "common", "status": "ok", "as_of_date": "2026-09-01", "close": 42123.45, "unit": "円", "digits": 2, "return_5d_pct": 1.2}},
        "stocks": [{
            "ticker": "TEST.T", "code": "0000", "name": "A&B <テスト>", "category": "ホテル",
            "rank": 1, "previous_rank": None, "attention_score": 80.0, "change_score": 0.0,
            "as_of_date": "2026-09-01", "retrieved_at": "2026-09-01T07:25:00+09:00",
            "return_20d_pct": 4.2, "return_5d_pct": 1.1, "close": 1000,
            "distance_ma20_pct": 2.0, "rsi14": 65, "rsi_state": "強い", "volume_ratio": 1.5,
            "signals": ["今日初めてTOP10入り"],
            "analysis": {"summary": "本日の要約", "why_research_today": "今日見る理由"},
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
    assert "42,123.45<small>円</small>" in index
    assert "基準日 2026-09-01" in index
    assert "1,000.00<small>円</small>" in index
    assert "2026年9月1日 レポート" in index
    assert "2026年9月1日の注目銘柄" in index
    assert "株価基準日 2026年9月1日" in index
    assert "取得日時 2026年09月01日07時25分00秒（日本時間）" in index
    assert "前回レポートからの変化" in index
    assert "今日" not in index
    assert "本日" not in index
    assert (docs_dir / "reports" / "2026-09-01" / "test-t.html").exists()


def test_report_times_use_jst_and_do_not_invent_legacy_acquisition_times(tmp_path):
    payload = _payload()
    payload['generated_at'] = '2026-09-06T22:35:00+00:00'
    payload['stocks'][0]['as_of_date'] = '2026-09-04'
    payload['stocks'][0]['retrieved_at'] = '2026-09-06T22:30:12+00:00'
    payload['market_drivers']['^N225']['as_of_date'] = '2026-09-04'
    for path in render_reports(payload, tmp_path):
        html = path.read_text(encoding='utf-8')
        assert '2026年09月07日07時35分00秒（日本時間）現在の情報です。投資は自己判断でお願いします。' in html
        assert '2026年09月07日07時30分12秒' in html
        assert '2026-09-04' in html
        assert '未記録' in html
    assert '2026年09月07日07時35分00秒</td>' not in (tmp_path / 'index.html').read_text(encoding='utf-8')


def test_datetime_rejects_unknown_or_naive_dates():
    from app.report import _datetime_jst
    for value in (None, '', 'invalid', '2026-09-07', '2026-09-07T07:30:00'):
        assert _datetime_jst(value) == '未記録'


def test_snapshot_preserves_per_source_timestamps():
    import pandas as pd
    from app.storage import build_snapshot
    payload = _payload()
    stock = {**payload['stocks'][0], 'as_of_date': '2026-09-04'}
    drivers = {**payload['market_drivers'], 'MISSING': {'status': 'unavailable'}}
    snapshot = build_snapshot(
        pd.DataFrame([stock]), drivers, {}, model='test', universe_size=1,
        research_targets=['TEST.T'],
        stock_retrieved_at={'TEST.T': '2026-09-06T22:30:00+00:00'},
        driver_retrieved_at={'^N225': '2026-09-06T22:31:00+00:00', 'MISSING': 'invalid'},
        analysis_completed_at='2026-09-06T22:32:00+00:00',
    )
    assert snapshot['stocks'][0]['retrieved_at'] == '2026-09-06T22:30:00+00:00'
    assert snapshot['market_drivers']['^N225']['retrieved_at'] == '2026-09-06T22:31:00+00:00'
    assert snapshot['market_drivers']['MISSING']['retrieved_at'] is None
    assert snapshot['analysis_completed_at'] is None
