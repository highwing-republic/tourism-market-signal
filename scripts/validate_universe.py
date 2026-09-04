from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.market_data import load_universe  # noqa: E402
from app.settings import Settings  # noqa: E402


if __name__ == "__main__":
    universe = load_universe(Settings().universe_file)
    print(f"OK: {len(universe)}銘柄、重複なし、inbound_weightは1〜5です")
