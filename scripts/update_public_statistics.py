import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.public_statistics import refresh_public_statistics
from app.settings import Settings


if __name__ == "__main__":
    payload = refresh_public_statistics(Settings().public_statistics_file)
    print(f'公的統計を更新しました: {len(payload.get("indicators", {}))}指標')
