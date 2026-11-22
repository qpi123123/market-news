"""실행: python collector/main.py

결과
- docs/index.html      : 오늘 페이지 (GitHub Pages가 이 폴더를 서비스)
- data/history.json    : 사건별 첫 보도 시각 기록 (다음 실행에서 'N일 전 재료' 판단에 사용)
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
from process import process  # noqa: E402
from render import render_page  # noqa: E402
from sources import KST, collect  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """로컬 실행용 .env 읽기 (GitHub Actions에서는 Secrets가 환경변수로 들어옴)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    load_dotenv(ROOT / ".env")
    started = time.time()
    now = datetime.now(KST)

    articles, statuses, quotes = collect(now)
    stories, n_ai = process(articles, ROOT / "data" / "history.json", now)
    page = render_page(stories, quotes, statuses, len(articles), n_ai, now, config.WINDOW_HOURS)

    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

    print(f"기사 {len(articles):,}건 (AI 작성 {n_ai}건 제외) → 사건 {len(stories):,}개 ({time.time() - started:.0f}초)")
    for st in statuses:
        print(f"  {'OK ' if st.ok else 'ERR'} {st.name}: {st.count}건 {st.error}")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
