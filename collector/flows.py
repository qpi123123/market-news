"""투자자별 순매수(외국인·기관·개인) — 마감시황 기사 본문에서 숫자를 읽음.

- 수집한 언론사 RSS 기사 중 '코스피/코스닥 … 마감' 기사를 찾아 본문을 받아 문장을 해석.
- 같은 날 여러 기사가 있으면 가장 늦게 나온 기사 사용 (매체·시점마다 숫자가 조금씩 다름 → 출처 표시).
- 못 읽으면 직전 성공 결과(data/flows.json)를 기준일과 함께 표시. 주말·휴일도 마지막 거래일 값이 보임.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

from datetime import timedelta

from sources import Article, SourceStatus, fetch_rss, http_get

# 마감시황 기사를 찾을 언론사 RSS (최근 며칠치가 들어 있어 주말에도 직전 거래일 기사를 찾을 수 있음)
FEEDS = [
    ("연합뉴스", "마켓+", "https://www.yna.co.kr/rss/market.xml"),
    ("한국경제", "증권", "https://www.hankyung.com/feed/finance"),
    ("아시아경제", "증권", "https://www.asiae.co.kr/rss/stock.htm"),
    ("연합인포맥스", "전체", "https://news.einfomax.co.kr/rss/allArticle.xml"),
    ("뉴시스", "경제", "https://www.newsis.com/RSS/economy.xml"),
]
LOOKBACK_DAYS = 4

INVESTORS = ("외국인", "기관", "개인")
TITLE = re.compile(r"(코스피|코스닥).{0,25}마감|마감\s*시황|\[마감\]")
MAX_FETCH = 8

# 금액: '1조2682억원', '3,499억원', '2조3159억9900만원', '1조원'
AMT = r"(?:\d[\d,]*\s*조\s*)?(?:\d[\d,]*\s*억\s*)?(?:\d[\d,]*\s*만\s*)?원"
SUBJ = r"(외국인(?:과|와|·|,\s*)\s*기관|기관(?:과|와|·|,\s*)\s*외국인|외국인(?:과|와)\s*개인|외국인|기관(?:계)?|개인)"
CLAUSE = re.compile(
    SUBJ + r"\s*(?:투자자)?[은는이가]?\s*(?:유가증권시장에서|코스닥(?:시장)?에서)?\s*(?:각각\s*)?"
    r"((?:" + AMT + r")(?:\s*(?:,|와|과)\s*" + AMT + r")?)"
    r"\s*(?:어치)?\s*[를을]?\s*(?:각각\s*)?(순매수|순매도|사들|팔|매수|매도)")


def parse_amount(text: str) -> float | None:
    """'1조2682억원' → 12682.0 (억원 단위)."""
    t = text.replace(",", "").replace(" ", "")
    m = re.fullmatch(r"(?:(\d+)조)?(?:(\d+)억)?(?:(\d+)만)?원", t)
    if not m or not any(m.groups()):
        return None
    jo, eok, man = (int(g) if g else 0 for g in m.groups())
    return jo * 10000 + eok + man / 10000


def _subjects(s: str) -> list[str]:
    s = s.replace("기관계", "기관")
    if "외국인" in s and "기관" in s:
        return ["외국인", "기관"] if s.index("외국인") < s.index("기관") else ["기관", "외국인"]
    if "외국인" in s and "개인" in s:
        return ["외국인", "개인"]
    return [s]


def parse_flows(text: str, default_market: str) -> dict[str, dict[str, float]]:
    """본문 → {"kospi": {"외국인": -12682, ...}, "kosdaq": {...}}"""
    out: dict[str, dict[str, float]] = {}
    market = default_market
    for sent in re.split(r"(?<=[다요])\.\s*|\n", text):
        if "코스닥" in sent:
            market = "kosdaq"
        elif re.search(r"유가증권|코스피", sent):
            market = "kospi"
        for m in CLAUSE.finditer(sent):
            subj, amounts, verb = m.groups()
            sign = 1 if verb in ("순매수", "사들", "매수") else -1
            values = [parse_amount(a) for a in re.findall(AMT, amounts)]
            values = [v for v in values if v is not None]
            names = _subjects(subj)
            if len(names) == 2 and len(values) == 1:   # '외국인과 기관이 1조원을 순매도' → 합계라 무시
                continue
            for name, v in zip(names, values):
                if name in INVESTORS:
                    out.setdefault(market, {}).setdefault(name, round(sign * v, 1))
    return {k: v for k, v in out.items() if len(v) >= 2}


def _article_text(url: str) -> str:
    raw = http_get(url, timeout=12, retries=1)
    m = re.search(rb'charset=["\']?([\w-]+)', raw[:5000])
    text = raw.decode(m.group(1).decode() if m else "utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
    return re.sub(r"[ \t]+", " ", text)


def collect_flows(now: datetime, cache: Path) -> tuple[dict, SourceStatus]:
    """반환: ({"kospi": {...,"date","outlet","url","title"}, "kosdaq": {...}}, 상태)"""
    saved = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    since = now - timedelta(days=LOOKBACK_DAYS)
    articles: list[Article] = []
    for outlet, section, url in FEEDS:
        articles += fetch_rss(outlet, section, url, since)[0]
    candidates = sorted((a for a in articles if TITLE.search(a.title)),
                        key=lambda a: a.published, reverse=True)[:MAX_FETCH]
    found: dict[str, dict] = {}
    for a in candidates:
        if {"kospi", "kosdaq"} <= found.keys():
            break
        default = "kosdaq" if "코스닥" in a.title and "코스피" not in a.title else "kospi"
        try:
            flows = parse_flows(a.title + ". " + _article_text(a.url), default)
        except Exception:
            continue
        for market, vals in flows.items():
            prev = found.get(market) or saved.get(market)
            date = a.published.date().isoformat()
            # 더 최근 날짜이거나, 같은 날 더 늦은 기사일 때만 교체 (후보가 최신순이라 처음 찾은 것이 우선)
            if market not in found and (not prev or date >= prev.get("date", "")):
                found[market] = {**vals, "date": date, "time": a.published.strftime("%H:%M"),
                                 "outlet": a.outlet, "url": a.url, "title": a.title}
    result = {**saved, **found}
    if found:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    note = (f"마감시황 기사 {len(candidates)}건 확인 · " +
            (f"새로 읽음: {', '.join(found)}" if found else "새 숫자 없음 — 직전 값 표시" if result else "아직 기록 없음"))
    return result, SourceStatus("투자자별 순매수 (마감시황 기사)", bool(result) or not candidates, len(found), note)
