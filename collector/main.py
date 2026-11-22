"""실행: python collector/main.py

순서: 수집 → 정리(AI 작성 기사 제외·같은 사건 묶기·종목/테마 태그·점수)
      → AI 판별(GitHub Actions에서만) → 패널 요약 보강 → 페이지 생성

결과
- docs/index.html    : 페이지 (GitHub Pages가 이 폴더를 서비스)
- data/history.json  : 사건별 첫 보도 시각 기록 ('N일 전 재료' 판단)
- data/stocks.json   : 상장 종목 목록 캐시 (7일마다 갱신)
- data/themes.json   : 날짜별 테마 건수 (테마 흐름)
- data/archive/      : 날짜별 상위 뉴스 기록 → docs/archive/*.html
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: E402
from ai import classify  # noqa: E402
from archive import build_archive_pages, save_snapshot, update_theme_log  # noqa: E402
from enrich import fill_leads  # noqa: E402
from process import process  # noqa: E402
from render import render_page, story_id  # noqa: E402
from sources import KST, SourceStatus, collect  # noqa: E402
from stocks import StockMatcher, load_stocks  # noqa: E402

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

    stock_list, stock_msg = load_stocks(ROOT / "data" / "stocks.json")
    articles, statuses, quotes = collect(now)
    statuses.append(SourceStatus("상장 종목 목록 (KRX)", bool(stock_list), len(stock_list), stock_msg))

    stories, n_ai = process(articles, ROOT / "data" / "history.json", now, StockMatcher(stock_list))
    ids = {id(s): story_id(s) for s in stories}
    statuses.append(classify(stories, ids))
    statuses.append(fill_leads(stories))

    # 날짜별 보관 (작은 JSON만 저장소에 남김) → 지난 날짜 페이지 생성
    theme_log = update_theme_log(ROOT / "data" / "themes.json", now, stories)
    save_snapshot(ROOT / "data" / "archive", now, stories)
    archive_dates = build_archive_pages(ROOT / "data" / "archive", ROOT / "docs" / "archive")

    page = render_page(stories, quotes, statuses, len(articles), n_ai, now, config.WINDOW_HOURS, stock_list,
                       theme_log, archive_dates)
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")

    n_world = sum(s.is_world for s in stories)
    print(f"기사 {len(articles):,}건 (AI 작성 {n_ai}건 제외) → 사건 {len(stories):,}개 "
          f"(주식 관련 {sum(s.stock_related for s in stories)}, 해외 {n_world}) ({time.time() - started:.0f}초)")
    for st in statuses:
        print(f"  {'OK ' if st.ok else 'ERR'} {st.name}: {st.count}건 {st.error}")
    print(f"저장: {out}")


if __name__ == "__main__":
    main()
