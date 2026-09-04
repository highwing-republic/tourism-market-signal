from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    base_dir: Path = BASE_DIR
    universe_file: Path = BASE_DIR / "config" / "universe.csv"
    drivers_file: Path = BASE_DIR / "config" / "drivers.yml"
    data_dir: Path = BASE_DIR / "data"
    history_dir: Path = BASE_DIR / "data" / "history"
    logs_dir: Path = BASE_DIR / "data" / "logs"
    market_cache_dir: Path = BASE_DIR / "data" / ".yfinance-cache"
    docs_dir: Path = BASE_DIR / "docs"
    reports_dir: Path = BASE_DIR / "docs" / "reports"
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    top_n: int = int(os.getenv("TOP_N", "5"))
    llm_max_targets: int = int(os.getenv("LLM_MAX_TARGETS", "5"))
    lookback_period: str = os.getenv("LOOKBACK_PERIOD", "1y")
    retry_count: int = int(os.getenv("REQUEST_RETRY_COUNT", "3"))

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.history_dir,
            self.logs_dir,
            self.market_cache_dir,
            self.docs_dir,
            self.reports_dir,
            self.docs_dir / "assets",
        ):
            path.mkdir(parents=True, exist_ok=True)
