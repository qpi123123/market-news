"""패널 요약 보강: 요약이 빈 주식 관련 기사는 언론사 기사 페이지의 대표 설명문(og:description)을 가져옴.

구글 경유 링크는 원래 주소를 알 수 없어 대상에서 제외 (같은 사건에 언론사 직접 링크가 있으면 그걸 사용).
"""

from __future__ import annotations

import html
import re
from concurrent.futures import ThreadPoolExecutor

from process import Story
from sources import SourceStatus, clean_text, http_get, lead_text

MAX_FETCH = 150   # 한 번 실행에 최대 몇 건까지 가져올지
WORKERS = 6


def _meta_description(page: bytes) -> str:
    head = page[:200_000]
    m = re.search(rb'charset=["\']?([\w-]+)', head[:5000])
    text = head.decode(m.group(1).decode() if m else "utf-8", errors="replace") if m else head.decode("utf-8", errors="replace")
    for prop in ("og:description", "description", "twitter:description"):
        tag = re.search(rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]*>', text, flags=re.I)
        if tag:
            content = re.search(r'content=["\']([^"\']*)["\']', tag.group(0), flags=re.I)
            if content and len(content.group(1).strip()) > 20:
                return clean_text(html.unescape(content.group(1)))
    return ""


def fill_leads(stories: list[Story]) -> SourceStatus:
    targets = []
    for s in stories:  # stories는 중요도순
        if not s.stock_related or s.lead_text:
            continue
        direct = next((a for a in s.articles if a.via != "구글"), None)
        if direct:
            targets.append(direct)
        if len(targets) >= MAX_FETCH:
            break

    def run(article):
        try:
            desc = _meta_description(http_get(article.url, timeout=8, retries=1))
            if desc:
                article.lead = lead_text(desc)
                return True
        except Exception:
            pass
        return False

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        ok = sum(pool.map(run, targets))
    return SourceStatus("패널 요약 보강 (기사 페이지 설명문)", True, ok,
                        error=f"대상 {len(targets)}건 중 {ok}건 채움" if targets else "대상 없음")
