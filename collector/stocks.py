"""상장 종목 사전과 기사 제목 속 종목 찾기.

출처: 한국거래소 KIND 상장법인목록 (코스피·코스닥·코넥스). 7일마다 새로 받아 data/stocks.json에 저장.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from sources import KST, http_get

KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
REFRESH_DAYS = 7

# 두 글자 종목명은 일반 단어와 헷갈려서 아래만 인정 (예: '대상', '동방'은 일반 단어로도 쓰임)
SHORT_NAME_ALLOW = {"기아", "한화", "효성", "농심", "풍산", "한샘", "동서", "SK", "LG", "KT", "GS", "LS", "CJ", "DL", "HL"}
# 세 글자 이상이지만 일반 단어로 자주 쓰여 오탐이 나는 이름
NAME_STOPLIST = {"디지털", "인터넷", "에이스", "유니온", "미래산업", "대한제당"}
SPORTS = re.compile(r"감독|연승|연패|세트|프로야구|프로농구|프로배구|K리그|홈경기|원정|득점|선발|우승|\d+-\d+")


CACHE_VERSION = 2  # 업종 추가


def short_industry(text: str) -> str:
    """'반도체 제조업' → '반도체', '소프트웨어 개발 및 공급업' → '소프트웨어 개발 및 공급'."""
    text = re.sub(r"\s*(제조업|서비스업|도매업|소매업|업)$", "", text.strip())
    return text[:14]


def _parse_kind(html: str) -> list[dict]:
    stocks = []
    for row in re.findall(r"<tr>(.*?)</tr>", html, flags=re.S):
        cells = [re.sub(r"<[^>]+>|\s+", " ", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
        if len(cells) < 3:
            continue
        name, market, code = cells[0], cells[1], cells[2].zfill(6)
        industry = cells[3] if len(cells) > 3 else ""
        if not re.fullmatch(r"[0-9A-Z]{6}", code) or "스팩" in name:
            continue
        stocks.append({"name": name, "market": market, "code": code, "industry": short_industry(industry)})
    return stocks


def load_stocks(cache: Path) -> tuple[list[dict], str]:
    """(종목 목록, 상태 메시지). 받기 실패하면 이전 캐시 사용."""
    cached = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
    if (cached and cached.get("v") == CACHE_VERSION
            and datetime.fromisoformat(cached["fetched"]) > datetime.now(KST) - timedelta(days=REFRESH_DAYS)):
        return cached["stocks"], f"캐시 사용 ({cached['fetched'][:10]})"
    try:
        stocks = _parse_kind(http_get(KIND_URL, timeout=30).decode("euc-kr", errors="replace"))
        if len(stocks) < 1000:
            raise ValueError(f"종목 수가 너무 적음 ({len(stocks)})")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"v": CACHE_VERSION, "fetched": datetime.now(KST).isoformat(), "stocks": stocks},
                                    ensure_ascii=False), encoding="utf-8")
        return stocks, "새로 받음"
    except Exception as e:
        if cached:
            return cached["stocks"], f"받기 실패, 이전 캐시 사용 ({str(e)[:40]})"
        return [], f"받기 실패 ({str(e)[:60]})"


class StockMatcher:
    """제목에서 종목명을 찾음. 긴 이름 우선 (삼성전자우 < 삼성전자 < 삼성)."""

    def __init__(self, stocks: list[dict]):
        names = {}
        for s in stocks:
            n = s["name"]
            if n in NAME_STOPLIST or (len(n) <= 2 and n not in SHORT_NAME_ALLOW):
                continue
            names[n] = s["code"]
        self.codes = names
        self.industry = {s["code"]: s.get("industry", "") for s in stocks}
        if not names:
            self.pattern = None
            return
        alts = []
        for n in sorted(names, key=len, reverse=True):
            if re.fullmatch(r"[A-Za-z0-9&]+", n):  # 영문 이름은 앞뒤가 영문·숫자가 아니어야 함
                alts.append(rf"(?<![A-Za-z0-9]){re.escape(n)}(?![A-Za-z0-9])")
            else:  # 한글 이름은 앞에 한글이 붙어 있으면 다른 단어의 일부로 봄
                alts.append(rf"(?<![가-힣]){re.escape(n)}")
        self.pattern = re.compile("|".join(alts))

    def find(self, text: str) -> list[tuple[str, str, str]]:
        """[(종목명, 종목코드, 업종)]"""
        if not self.pattern or SPORTS.search(text):  # 스포츠 기사의 구단 이름(현대건설 배구단 등) 제외
            return []
        found = dict.fromkeys(m.group(0) for m in self.pattern.finditer(text))
        return [(n, self.codes[n], self.industry.get(self.codes[n], "")) for n in found]
