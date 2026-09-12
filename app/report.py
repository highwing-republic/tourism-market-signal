from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


DRIVER_UNITS = {
    "^N225": "円",
    "^GSPC": "ポイント",
    "^IXIC": "ポイント",
    "^VIX": "ポイント",
    "JPY=X": "円/米ドル",
    "CL=F": "米ドル/バレル",
    "DAL": "米ドル",
    "UAL": "米ドル",
    "AAL": "米ドル",
    "LUV": "米ドル",
    "BA": "米ドル",
}


def _datetime_jst(value: Any) -> str:
    if not value:
        return "未記録"
    try:
        timestamp = datetime.fromisoformat(str(value))
        if timestamp.tzinfo is None:
            return "未記録"
        return timestamp.astimezone(ZoneInfo("Asia/Tokyo")).strftime("%Y年%m月%d日%H時%M分%S秒")
    except (ValueError, TypeError):
        return "未記録"


def _freshness_notice(payload: dict[str, Any], stock: dict[str, Any] | None = None) -> str:
    generated_at = _datetime_jst(payload.get("generated_at"))
    statement = (
        f"{generated_at}（日本時間）現在の情報です。"
        if generated_at != "未記録" else "レポート作成日時は未記録です。"
    )
    records = [stock] if stock is not None else [
        *payload.get("market_drivers", {}).values(), *payload.get("stocks", [])
    ]
    rows = "".join(
        f'<tr><th scope="row">{_text(item.get("name"))}<small>{_text(item.get("ticker"))}</small></th>'
        f'<td>{_text(item.get("as_of_date"), "未記録")}</td>'
        f'<td>{"取得不能" if item.get("status") == "unavailable" else _datetime_jst(item.get("retrieved_at"))}</td></tr>'
        for item in records
    )
    ai_time = (
        _datetime_jst(payload.get("analysis_completed_at"))
        if payload.get("analysis_status") == "complete" else "未実行・取得不能"
    )
    return f"""
<aside class="data-notice" aria-label="情報の日時とご利用にあたって">
  <p class="data-notice__statement"><strong>{statement}投資は自己判断でお願いします。</strong></p>
  <p>上記はレポート作成時点です。市場データはリアルタイムではありません。データ基準日は各市場の日付、取得日時とAI分析完了日時は日本時間で表示しています。</p>
  <p>AI分析完了日時：{ai_time}</p>
  <details>
    <summary>各データの基準日・取得日時を確認する</summary>
    <div class="table-wrap"><table><caption>データの取得日時（日本時間）</caption><thead><tr><th scope="col">データ</th><th scope="col">データ基準日</th><th scope="col">取得日時</th></tr></thead><tbody>{rows}</tbody></table></div>
    <p>「未記録」は取得時刻の記録がないデータです。レポート作成日時を取得日時の代わりには使用していません。</p>
  </details>
</aside>
"""


def _text(value: Any, fallback: str = "—") -> str:
    return fallback if value is None else escape(str(value))


def _pct(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value):+.2f}%"


def _number(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}{suffix}"


def _driver_level(driver: dict[str, Any]) -> str:
    value = driver.get("close")
    if value is None:
        return "—"
    digits = int(driver.get("digits", 2))
    unit = _text(driver.get("unit") or DRIVER_UNITS.get(str(driver.get("ticker"))), "")
    return f"{float(value):,.{digits}f}<small>{unit}</small>"


def _slug(ticker: str) -> str:
    return ticker.lower().replace("^", "").replace("=", "-").replace(".", "-")


def _page(title: str, body: str, *, asset_prefix: str, home_href: str) -> str:
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="観光・インバウンド関連株の変化を毎朝抽出する調査支援レポート">
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="{asset_prefix}/style.css">
</head>
<body>
  <header class="site-header">
    <a class="brand" href="{home_href}"><span>観光株シグナル</span><small>Tourism Market Signal</small></a>
    <span class="purpose">予測ではなく、調べるべき変化を。</span>
  </header>
  <main>{body}</main>
  <footer>
    <p>本サイトは調査支援を目的としたもので、特定銘柄の売買を推奨するものではありません。投資は自己判断でお願いします。</p>
    <p>株価データ: Yahoo Finance（yfinance経由）。公開・商用利用時は利用条件を別途確認してください。</p>
  </footer>
</body>
</html>
"""


def _signal_badges(stock: dict[str, Any]) -> str:
    signals = stock.get("signals") or []
    if not signals:
        return '<span class="badge muted">継続監視</span>'
    return "".join(f'<span class="badge">{escape(str(item))}</span>' for item in signals)


def _rank_label(stock: dict[str, Any]) -> str:
    previous = stock.get("previous_rank")
    current = stock.get("rank")
    if previous is None:
        return f"初回 → {current}位"
    return f"{previous}位 → {current}位"


def _target_card(stock: dict[str, Any], report_date: str, *, detail_prefix: str) -> str:
    analysis = stock.get("analysis") or {}
    summary = analysis.get("summary") or "AI分析は未実行です。定量指標と変化シグナルを確認してください。"
    href = f"{detail_prefix}/{_slug(stock['ticker'])}.html"
    return f"""
<article class="signal-card">
  <div class="card-rank">#{int(stock['rank'])}</div>
  <div class="card-heading">
    <div><span class="category">{_text(stock.get('category'))}</span><h3>{_text(stock.get('name'))}</h3><code>{_text(stock.get('code'))}</code></div>
    <div class="score"><strong>{_number(stock.get('attention_score'), 0)}</strong><span>注目度</span></div>
  </div>
  <div class="badges">{_signal_badges(stock)}</div>
  <dl class="metrics">
    <div><dt>20日</dt><dd>{_pct(stock.get('return_20d_pct'))}</dd></div>
    <div><dt>出来高</dt><dd>{_number(stock.get('volume_ratio'), 2, '倍')}</dd></div>
    <div><dt>順位</dt><dd>{_rank_label(stock)}</dd></div>
    <div><dt>RSI</dt><dd>{_number(stock.get('rsi14'), 1)} <small>{_text(stock.get('rsi_state'))}</small></dd></div>
  </dl>
  <p class="ai-summary"><span>AI / 定量コメント</span>{escape(str(summary))}</p>
  <a class="detail-link" href="{href}">詳細を見る <span aria-hidden="true">→</span></a>
</article>
"""


def _driver_cards(drivers: dict[str, dict]) -> str:
    items: list[str] = []
    for driver in drivers.values():
        if driver.get("status") != "ok":
            level, change_text, direction, css, as_of = "取得不能", "—", "—", "flat", "未記録"
        else:
            change = driver.get("return_5d_pct")
            level = _driver_level(driver)
            change_text = _pct(change)
            direction = "↑" if change is not None and change > 0.3 else "↓" if change is not None and change < -0.3 else "→"
            css = "up" if direction == "↑" else "down" if direction == "↓" else "flat"
            as_of = _text(driver.get("as_of_date"), "未記録")
        items.append(
            f'<div class="driver"><span class="driver-name">{_text(driver.get("name"))}</span>'
            f'<strong class="driver-level">{level}</strong>'
            f'<span class="driver-change"><b class="{css}">{direction} {change_text}</b><small>5日変化</small></span>'
            f'<small class="driver-as-of">基準日 {as_of}</small></div>'
        )
    return "".join(items)


def _ranking_table(stocks: list[dict[str, Any]]) -> str:
    rows = []
    for stock in sorted(stocks, key=lambda item: item["rank"])[:15]:
        rows.append(
            "<tr>"
            f"<td>{int(stock['rank'])}</td><td>{_text(stock.get('code'))}</td>"
            f"<td>{_text(stock.get('name'))}<small>{_text(stock.get('category'))}</small></td>"
            f"<td>{_number(stock.get('attention_score'), 1)}</td>"
            f"<td>{_number(stock.get('change_score'), 1)}</td>"
            f"<td>{_pct(stock.get('return_20d_pct'))}</td>"
            f"<td>{_number(stock.get('volume_ratio'), 2, '倍')}</td>"
            "</tr>"
        )
    return "".join(rows)


def _dashboard_body(payload: dict[str, Any], *, detail_prefix: str) -> str:
    report_date = str(payload["report_date"])
    stock_map = {stock["ticker"]: stock for stock in payload["stocks"]}
    targets = [stock_map[ticker] for ticker in payload.get("research_targets", []) if ticker in stock_map]
    quality = payload.get("data_quality", {})
    cards = "".join(_target_card(stock, report_date, detail_prefix=detail_prefix) for stock in targets)
    return f"""
<section class="hero">
  <p class="eyebrow">DAILY SIGNAL · {escape(report_date)}</p>
  <h1>今日、調べる価値が<br><em>生まれた企業</em></h1>
  <p>観光・インバウンド関連50銘柄から、価格・トレンド・出来高・前日差分をもとに調査候補を抽出します。</p>
  <div class="quality"><span>分析 {quality.get('analyzed_stocks', 0)} / {quality.get('configured_stocks', 0)}銘柄</span><span>レポート作成日時 {_datetime_jst(payload.get('generated_at'))}（日本時間）</span></div>
</section>
{_freshness_notice(payload)}
<section>
  <div class="section-heading"><div><p class="eyebrow">MARKET CONTEXT</p><h2>市場環境</h2></div><p>スコアへ混ぜず、判断材料として分離表示</p></div>
  <div class="driver-grid">{_driver_cards(payload.get('market_drivers', {}))}</div>
</section>
<section>
  <div class="section-heading"><div><p class="eyebrow">TODAY'S RESEARCH</p><h2>今日の注目</h2></div><p>注目度 × 昨日からの変化</p></div>
  <div class="signal-grid">{cards or '<p class="empty">表示できる調査候補がありません。</p>'}</div>
</section>
<section>
  <div class="section-heading"><div><p class="eyebrow">QUANT RANKING</p><h2>定量ランキング</h2></div><p>RSIは状態表示のみ。総合点には含めません。</p></div>
  <div class="table-wrap"><table><thead><tr><th>順位</th><th>コード</th><th>銘柄</th><th>注目度</th><th>変化</th><th>20日</th><th>出来高</th></tr></thead><tbody>{_ranking_table(payload['stocks'])}</tbody></table></div>
</section>
"""


def _factor_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<li>入力データだけでは特定できません。</li>"
    return "".join(
        f"<li><strong>{_text(item.get('title'))}</strong><p>{_text(item.get('description'))}</p>"
        f"<small>{_text(item.get('factor_type'))} · 根拠: {_text(', '.join(item.get('evidence_fields') or []))}</small></li>"
        for item in items
    )


def _simple_list(items: list[Any]) -> str:
    return "".join(f"<li>{_text(item)}</li>" for item in items) or "<li>記載なし</li>"


def _detail_body(stock: dict[str, Any], payload: dict[str, Any]) -> str:
    analysis = stock.get("analysis") or {}
    scenarios = {item.get("name"): item for item in analysis.get("scenarios", [])}
    scenario_labels = (("bull", "強気"), ("base", "基本"), ("bear", "弱気"))
    scenario_html = "".join(
        f'<article><span>{label}</span><p>{_text(scenarios.get(key, {}).get("description"), "AI分析未実行")}</p>'
        f'<ul>{_simple_list(scenarios.get(key, {}).get("conditions", []))}</ul></article>'
        for key, label in scenario_labels
    )
    return f"""
<nav class="breadcrumb"><a href="../../index.html">トップ</a><span>/</span><span>{_text(stock.get('name'))}</span></nav>
<section class="detail-hero">
  <div><p class="eyebrow">RESEARCH NOTE · {escape(str(payload['report_date']))}</p><span class="category">{_text(stock.get('category'))}</span><h1>{_text(stock.get('name'))}</h1><p>{_text(stock.get('ticker'))}</p></div>
  <div class="score large"><strong>{_number(stock.get('attention_score'), 0)}</strong><span>注目度</span><small>変化 {_number(stock.get('change_score'), 0)}</small></div>
</section>
<div class="badges detail-badges">{_signal_badges(stock)}</div>
{_freshness_notice(payload, stock)}
<section class="detail-grid">
  <article class="panel"><p class="eyebrow">WHY TODAY</p><h2>なぜ今日見るのか</h2><p class="lead">{_text(analysis.get('why_research_today'), 'AI分析は未実行です。定量データを確認してください。')}</p><p>{_text(analysis.get('summary'), '')}</p></article>
  <article class="panel"><p class="eyebrow">TECHNICAL</p><h2>定量データ</h2><dl class="detail-metrics">
    <div><dt>終値</dt><dd>{_number(stock.get('close'), 2)}</dd></div><div><dt>5日</dt><dd>{_pct(stock.get('return_5d_pct'))}</dd></div>
    <div><dt>20日</dt><dd>{_pct(stock.get('return_20d_pct'))}</dd></div><div><dt>MA20乖離</dt><dd>{_pct(stock.get('distance_ma20_pct'))}</dd></div>
    <div><dt>RSI</dt><dd>{_number(stock.get('rsi14'), 1)} {_text(stock.get('rsi_state'))}</dd></div><div><dt>出来高比</dt><dd>{_number(stock.get('volume_ratio'), 2, '倍')}</dd></div>
  </dl></article>
</section>
<section class="factor-grid"><article class="panel positive"><h2>プラス材料</h2><ul>{_factor_list(analysis.get('positive_factors', []))}</ul></article><article class="panel negative"><h2>マイナス材料</h2><ul>{_factor_list(analysis.get('negative_factors', []))}</ul></article></section>
<section><div class="section-heading"><div><p class="eyebrow">CONDITIONAL VIEW</p><h2>条件付きシナリオ</h2></div></div><div class="scenario-grid">{scenario_html}</div></section>
<section class="detail-grid"><article class="panel"><h2>反対材料</h2><ul>{_simple_list(analysis.get('counter_arguments', []))}</ul></article><article class="panel"><h2>追加で確認したい情報</h2><ul>{_simple_list(analysis.get('additional_data_needed', []))}</ul></article></section>
"""


def render_reports(payload: dict[str, Any], docs_dir: Path) -> list[Path]:
    report_date = str(payload["report_date"])
    daily_dir = docs_dir / "reports" / report_date
    daily_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    index_path = docs_dir / "index.html"
    index_path.write_text(
        _page(
            "観光株シグナル / Tourism Market Signal",
            _dashboard_body(payload, detail_prefix=f"reports/{report_date}"),
            asset_prefix="assets",
            home_href="index.html",
        ),
        encoding="utf-8",
    )
    written.append(index_path)

    daily_index = daily_dir / "index.html"
    daily_index.write_text(
        _page(
            f"観光株シグナル {report_date}",
            _dashboard_body(payload, detail_prefix="."),
            asset_prefix="../../assets",
            home_href="../../index.html",
        ),
        encoding="utf-8",
    )
    written.append(daily_index)

    stock_map = {stock["ticker"]: stock for stock in payload["stocks"]}
    for ticker in payload.get("research_targets", []):
        stock = stock_map.get(ticker)
        if stock is None:
            continue
        detail_path = daily_dir / f"{_slug(ticker)}.html"
        detail_path.write_text(
            _page(
                f"{stock['name']} | 観光株シグナル",
                _detail_body(stock, payload),
                asset_prefix="../../assets",
                home_href="../../index.html",
            ),
            encoding="utf-8",
        )
        written.append(detail_path)
    return written

