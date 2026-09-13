import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.market_wind import calculate_market_wind
from app.report import render_reports
from app.settings import Settings


if __name__ == "__main__":
    settings = Settings()
    latest_path = settings.data_dir / "latest.json"
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    public_statistics = json.loads(settings.public_statistics_file.read_text(encoding="utf-8"))
    payload["schema_version"] = 4
    payload["market_wind"] = calculate_market_wind(
        payload.get("stocks") or [], payload.get("market_drivers") or {}, public_statistics,
        report_date=str(payload["report_date"]), config_path=settings.market_wind_file,
    )
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(text, encoding="utf-8")
    history_path = settings.history_dir / f'{payload["report_date"]}.json'
    if history_path.exists():
        history_path.write_text(text, encoding="utf-8")
    paths = render_reports(payload, settings.docs_dir)
    print(f"風向き判定を反映しました: {len(paths)}ページ")
