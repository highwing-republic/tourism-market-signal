from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
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


def _date_ja(value: Any) -> str:
    if not value:
        return "日付未記録"
    try:
        parsed = datetime.strptime(str(value), "%Y-%m-%d")
        return f"{parsed.year}年{parsed.month}月{parsed.day}日"
    except (ValueError, TypeError):
        return "日付未記録"


def _replace_relative_date_text(value: Any, report_date: str) -> str:
    report_date_ja = _date_ja(report_date)
    return (
        str(value)
        .replace("本日の", f"{report_date_ja}の")
        .replace("今日の", f"{report_date_ja}の")
        .replace("本日", f"{report_date_ja}に")
        .replace("今日", f"{report_date_ja}に")
    )


def _dated_text(value: Any, report_date: str, fallback: str = "") -> str:
    return escape(_replace_relative_date_text(fallback if value is None else value, report_date))


def _replace_relative_dates(html: str, report_date: str) -> str:
    return _replace_relative_date_text(html, report_date)


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
    methodology = payload.get("methodology") or {}
    basis_note = (
        "選定基準：平日朝6:00（日本時間）に取得処理を開始し、レポート日の前日までに確定した直近取引日の終値を使用しています。"
        if methodology.get("price_basis") == "previous_market_close"
        else "選定基準：各カードに記載した株価基準日の終値を使用しています。"
    )
    return f"""
<aside class="data-notice" aria-label="情報の日時とご利用にあたって">
  <p class="data-notice__statement"><strong>{statement}投資は自己判断でお願いします。</strong></p>
  <p><strong>{basis_note}</strong></p>
  <p>銘柄選定には、各カードに記載したデータ基準日の終値を使用しています。市場データはリアルタイムではありません。取得日時とAI分析完了日時は日本時間で表示しています。</p>
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


def _yen_price(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value):,.2f}<small>円</small>"


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


def _signal_badges(stock: dict[str, Any], report_date: str) -> str:
    signals = stock.get("signals") or []
    if not signals:
        return '<span class="badge muted">継続監視</span>'
    return "".join(f'<span class="badge">{_dated_text(item, report_date)}</span>' for item in signals)


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
    stock_date = _date_ja(stock.get("as_of_date"))
    retrieved_at = _datetime_jst(stock.get("retrieved_at"))
    return f"""
<article class="signal-card">
  <div class="card-rank">#{int(stock['rank'])}</div>
  <div class="card-heading">
    <div><span class="category">{_text(stock.get('category'))}</span><h3>{_text(stock.get('name'))}</h3><code>{_text(stock.get('code'))}</code></div>
    <div class="score"><strong>{_number(stock.get('attention_score'), 0)}</strong><span>注目度</span></div>
  </div>
  <p class="stock-price"><span>株価基準日 {stock_date}</span><strong>{_yen_price(stock.get('close'))}</strong></p>
  <p class="stock-retrieved">取得日時 {retrieved_at}（日本時間）</p>
  <div class="badges">{_signal_badges(stock, report_date)}</div>
  <dl class="metrics">
    <div><dt>20日</dt><dd>{_pct(stock.get('return_20d_pct'))}</dd></div>
    <div><dt>出来高</dt><dd>{_number(stock.get('volume_ratio'), 2, '倍')}</dd></div>
    <div><dt>順位</dt><dd>{_rank_label(stock)}</dd></div>
    <div><dt>RSI</dt><dd>{_number(stock.get('rsi14'), 1)} <small>{_text(stock.get('rsi_state'))}</small></dd></div>
  </dl>
  <p class="ai-summary"><span>AI / 定量コメント</span>{_dated_text(summary, report_date)}</p>
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


def _wind_icon(state: str) -> str:
    """Decorative, currentColor SVGs keep the signal readable without external assets."""
    if state in {"tailwind", "strong_tailwind"}:
        paths = '<path d="M8 29h27c8 0 8-10 2-11-4-.7-6 2-6 4"/><path d="M8 39h39c9 0 9 11 2 12-5 .8-7-3-6-6"/><path d="M8 49h20"/><path d="m22 22 8 7-8 7"/>'
    elif state in {"headwind", "strong_headwind"}:
        paths = '<path d="M56 29H29c-8 0-8-10-2-11 4-.7 6 2 6 4"/><path d="M56 39H17c-9 0-9 11-2 12 5 .8 7-3 6-6"/><path d="M56 49H36"/><path d="m42 22-8 7 8 7"/>'
    elif state == "mixed":
        paths = '<path d="M8 24h32c8 0 8-9 2-10-4-.6-6 2-6 4"/><path d="M56 42H24c-8 0-8 9-2 10 4 .6 6-2 6-4"/><path d="m18 18-7 6 7 6"/><path d="m46 36 7 6-7 6"/>'
    elif state == "insufficient":
        paths = '<path d="M32 10a22 22 0 1 0 22 22A22 22 0 0 0 32 10Z"/><path d="M32 22v13"/><path d="M32 44h.01"/>'
    else:
        paths = '<path d="M8 32h48"/><path d="M14 24h36"/><path d="M18 40h28"/><path d="M24 17h16"/>'
    return f'<svg class="wind-icon" viewBox="0 0 64 64" aria-hidden="true" focusable="false"><g>{paths}</g></svg>'


def _wind_value(item: dict[str, Any]) -> str:
    value = item.get("raw_value")
    if value is None:
        return "—"
    unit = item.get("unit", "%")
    if unit == "比率":
        return f"{float(value) * 100:.0f}%"
    return f"{float(value):+.1f}{escape(str(unit))}"


def _wind_factor_list(items: list[dict[str, Any]], empty: str) -> str:
    if not items:
        return f'<li class="wind-factor-empty">{escape(empty)}</li>'
    return "".join(
        f'<li><span>{_text(item.get("label"))}</span><strong>{_wind_value(item)}</strong></li>'
        for item in items
    )


def _market_wind_section(payload: dict[str, Any]) -> str:
    wind = payload.get("market_wind") or {}
    horizons = wind.get("horizons") or {}
    if not horizons:
        return ""
    cards: list[str] = []
    for key in ("short", "medium", "long"):
        item = horizons.get(key)
        if not item:
            continue
        state = str(item.get("state", "insufficient"))
        score = float(item.get("score") or 0)
        score_text = f"{score:+.0f}"
        cards.append(f"""
<article class="wind-card wind-card--{escape(state)}">
  <div class="wind-card__top">
    <div><p class="wind-period">{_text(item.get('period'))}</p><h3>{_text(item.get('label'))}</h3></div>
    {_wind_icon(state)}
  </div>
  <div class="wind-verdict"><strong>{_text(item.get('state_label'))}</strong><span>風向き指数 <b>{score_text}</b></span></div>
  <p class="wind-summary">{_text(item.get('summary'))}</p>
  <div class="wind-factors">
    <div><h4>追い風材料</h4><ul>{_wind_factor_list(item.get('positive_factors') or [], '明確な材料なし')}</ul></div>
    <div><h4>逆風材料</h4><ul>{_wind_factor_list(item.get('negative_factors') or [], '明確な材料なし')}</ul></div>
  </div>
  <p class="wind-confidence">判定確度 {_text(item.get('confidence_label'))} {_number(item.get('confidence'), 0, '%')} <span>・有効データ {_number(item.get('coverage'), 0, '%')}・市場基準日 {_text(item.get('market_basis_date'), '未記録')}</span></p>
</article>""")
    source_rows = ""
    for source in wind.get("source_periods") or []:
        url = str(source.get("url") or "")
        parsed = urlparse(url)
        source_name = _text(source.get("name"))
        if parsed.scheme == "https" and parsed.hostname in {"www.jnto.go.jp", "www.mlit.go.jp"}:
            source_name = f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{source_name}</a>'
        source_rows += (
            f'<li><span>{source_name}</span><strong>{_text(source.get("period"))}</strong>'
            f'<small>{_text(source.get("release_type"), "区分未記録")}・公表日 {_text(source.get("published_date"), "未記録")}</small></li>'
        )
    methodology_note = _text(wind.get("methodology_note"), "")
    return f"""
<section class="wind-section" aria-labelledby="market-wind-title">
  <div class="section-heading"><div><p class="eyebrow">TOURISM MARKET WIND</p><h2 id="market-wind-title">観光マーケットの風向き</h2></div><p>市場データと公的統計を期間別に総合判定</p></div>
  <p class="wind-lead">{_text(wind.get('overall_summary'))} 指数は−100（強い逆風）から＋100（強い追い風）で表します。</p>
  <div class="wind-grid">{''.join(cards)}</div>
  <details class="wind-sources"><summary>判定に使用した公的統計と算出上の注意</summary>
    <ul>{source_rows or '<li>利用できる公的統計はありません。</li>'}</ul>
    <p>{methodology_note}</p>
    <p>株価・指数の動き、公的な需要統計、客室稼働率を同じ尺度に正規化した独自判定です。将来の価格や需要を保証するものではありません。</p>
  </details>
</section>"""


def _ranking_table(stocks: list[dict[str, Any]]) -> str:
    rows = []
    for stock in sorted(stocks, key=lambda item: item["rank"])[:15]:
        stock_date = _date_ja(stock.get("as_of_date"))
        rows.append(
            "<tr>"
            f"<td>{int(stock['rank'])}</td><td>{_text(stock.get('code'))}</td>"
            f"<td>{_text(stock.get('name'))}<small>{_text(stock.get('category'))}</small></td>"
            f'<td class="ranking-price"><span>{_yen_price(stock.get("close"))}</span>'
            f"<small>{stock_date}終値</small></td>"
            f"<td>{_number(stock.get('attention_score'), 1)}</td>"
            f"<td>{_number(stock.get('change_score'), 1)}</td>"
            f"<td>{_pct(stock.get('return_20d_pct'))}</td>"
            f"<td>{_number(stock.get('volume_ratio'), 2, '倍')}</td>"
            "</tr>"
        )
    return "".join(rows)


def _dashboard_body(payload: dict[str, Any], *, detail_prefix: str) -> str:
    report_date = str(payload["report_date"])
    report_date_ja = _date_ja(report_date)
    stock_map = {stock["ticker"]: stock for stock in payload["stocks"]}
    targets = [stock_map[ticker] for ticker in payload.get("research_targets", []) if ticker in stock_map]
    quality = payload.get("data_quality", {})
    cards = "".join(_target_card(stock, report_date, detail_prefix=detail_prefix) for stock in targets)
    return f"""
<section class="hero">
  <p class="eyebrow">DAILY SIGNAL</p>
  <p class="report-date">{report_date_ja} レポート</p>
  <h1>この日に、調べる価値が<br><em>生まれた企業</em></h1>
  <p>平日毎朝6:00（日本時間）に取得処理を開始し、前日までに確定した直近取引日の終値から、価格・トレンド・出来高・前回レポートとの差分を分析します。</p>
  <div class="quality"><span>分析 {quality.get('analyzed_stocks', 0)} / {quality.get('configured_stocks', 0)}銘柄</span><span>レポート作成日時 {_datetime_jst(payload.get('generated_at'))}（日本時間）</span></div>
</section>
{_freshness_notice(payload)}
{_market_wind_section(payload)}
<section>
  <div class="section-heading"><div><p class="eyebrow">MARKET CONTEXT</p><h2>市場環境</h2></div><p>スコアへ混ぜず、判断材料として分離表示</p></div>
  <div class="driver-grid">{_driver_cards(payload.get('market_drivers', {}))}</div>
</section>
<section>
  <div class="section-heading"><div><p class="eyebrow">RESEARCH TARGETS</p><h2>{report_date_ja}の注目銘柄</h2></div><p>注目度 × 前回レポートからの変化</p></div>
  <div class="signal-grid">{cards or '<p class="empty">表示できる調査候補がありません。</p>'}</div>
</section>
<section>
  <div class="section-heading"><div><p class="eyebrow">QUANT RANKING</p><h2>定量ランキング</h2></div><p>RSIは状態表示のみ。総合点には含めません。</p></div>
  <div class="table-wrap"><table class="ranking-table"><thead><tr><th>順位</th><th>コード</th><th>銘柄</th><th>前日終値</th><th>注目度</th><th>変化</th><th>20日</th><th>出来高</th></tr></thead><tbody>{_ranking_table(payload['stocks'])}</tbody></table></div>
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
    report_date = str(payload["report_date"])
    report_date_ja = _date_ja(report_date)
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
  <div><p class="eyebrow">RESEARCH NOTE · {report_date_ja}</p><span class="category">{_text(stock.get('category'))}</span><h1>{_text(stock.get('name'))}</h1><p>{_text(stock.get('ticker'))}</p></div>
  <div class="score large"><strong>{_number(stock.get('attention_score'), 0)}</strong><span>注目度</span><small>変化 {_number(stock.get('change_score'), 0)}</small></div>
</section>
<div class="badges detail-badges">{_signal_badges(stock, report_date)}</div>
{_freshness_notice(payload, stock)}
<section class="detail-grid">
  <article class="panel"><p class="eyebrow">RESEARCH REASON</p><h2>{report_date_ja}に注目する理由</h2><p class="lead">{_dated_text(analysis.get('why_research_today'), report_date, 'AI分析は未実行です。定量データを確認してください。')}</p><p>{_dated_text(analysis.get('summary'), report_date)}</p></article>
  <article class="panel"><p class="eyebrow">TECHNICAL</p><h2>定量データ</h2><dl class="detail-metrics">
    <div><dt>終値</dt><dd>{_yen_price(stock.get('close'))}</dd></div><div><dt>5日</dt><dd>{_pct(stock.get('return_5d_pct'))}</dd></div>
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
        _replace_relative_dates(
            _page(
                "観光株シグナル / Tourism Market Signal",
                _dashboard_body(payload, detail_prefix=f"reports/{report_date}"),
                asset_prefix="assets",
                home_href="index.html",
            ),
            report_date,
        ),
        encoding="utf-8",
    )
    written.append(index_path)

    daily_index = daily_dir / "index.html"
    daily_index.write_text(
        _replace_relative_dates(
            _page(
                f"観光株シグナル {report_date}",
                _dashboard_body(payload, detail_prefix="."),
                asset_prefix="../../assets",
                home_href="../../index.html",
            ),
            report_date,
        ),
        encoding="utf-8",
    )
    written.append(daily_index)

    stock_map = {stock["ticker"]: stock for stock in payload["stocks"]}
    existing_detail_tickers = [
        ticker
        for ticker in stock_map
        if (daily_dir / f"{_slug(ticker)}.html").exists()
    ]
    detail_tickers = dict.fromkeys([
        *payload.get("research_targets", []),
        *existing_detail_tickers,
    ])
    for ticker in detail_tickers:
        stock = stock_map.get(ticker)
        if stock is None:
            continue
        detail_path = daily_dir / f"{_slug(ticker)}.html"
        detail_path.write_text(
            _replace_relative_dates(
                _page(
                    f"{stock['name']} | 観光株シグナル",
                    _detail_body(stock, payload),
                    asset_prefix="../../assets",
                    home_href="../../index.html",
                ),
                report_date,
            ),
            encoding="utf-8",
        )
        written.append(detail_path)
    return written

