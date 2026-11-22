"""데이터 수집: 구글 뉴스 검색, 언론사 RSS, 네이버 뉴스 검색 API(선택), 시세(Yahoo Finance)."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import config

KST = timezone(timedelta(hours=9))
USER_AGENT = "Mozilla/5.0 (compatible; market-news-collector/1.0)"


@dataclass
class Article:
    title: str
    summary: str      # 첫 문장(또는 리드)
    url: str
    outlet: str
    published: datetime  # KST
    via: str          # "구글", "RSS", "네이버"


@dataclass
class SourceStatus:
    name: str
    ok: bool
    count: int = 0
    error: str = ""


@dataclass
class Quote:
    group: str
    name: str
    unit: str
    price: float | None = None
    change: float | None = None
    pct: float | None = None
    as_of: datetime | None = None
    note: str = ""
    flags: list[str] = field(default_factory=list)  # "big", "stale"


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------
def http_get(url: str, headers: dict | None = None, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean_text(raw: str) -> str:
    """CDATA·태그·HTML 엔티티(이중 인코딩 포함) 제거."""
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", raw, flags=re.S)
    for _ in range(2):  # 일부 매체는 &amp;quot; 처럼 두 번 인코딩됨
        text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def first_sentence(text: str, limit: int = 160) -> str:
    # "(서울=연합뉴스) 홍길동 기자 = " 같은 머리말 제거
    text = re.sub(r"^\s*[\(\[][^)\]]{0,30}[\)\]]\s*([^=]{0,20}기자\s*=\s*)?", "", text)
    text = re.sub(r"^[^=]{0,20}기자\s*=\s*", "", text)
    m = re.search(r"(.+?(?:다|음|함|됨|요)\.)(\s|$)", text)
    sentence = m.group(1) if m else text
    return sentence if len(sentence) <= limit else sentence[: limit - 1] + "…"


def parse_date(raw: str) -> datetime | None:
    raw = clean_text(raw)
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)  # RFC 822 (대부분 RSS·네이버)
    except (TypeError, ValueError):
        dt = None
    if dt is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(raw[:25], fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return None
    if dt.tzinfo is None:  # 시간대 없는 국내 매체 날짜는 KST로 간주
        dt = dt.replace(tzinfo=KST)
    return dt.astimezone(KST)


def decode(body: bytes) -> str:
    m = re.search(rb'encoding=["\']([\w-]+)["\']', body[:200])
    enc = m.group(1).decode() if m else "utf-8"
    try:
        return body.decode(enc, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# RSS
# ---------------------------------------------------------------------------
def _tag(block: str, *names: str) -> str:
    for name in names:
        m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", block, flags=re.S)
        if m:
            return m.group(1)
    return ""


def fetch_rss(outlet: str, section: str, url: str, since: datetime) -> tuple[list[Article], SourceStatus]:
    name = f"{outlet} {section} (RSS)"
    try:
        text = decode(http_get(url))
        if "<item" not in text:
            raise ValueError("RSS 형식이 아님 (차단 페이지일 수 있음)")
        articles = []
        for block in re.findall(r"<item[\s>].*?</item>", text, flags=re.S):
            published = parse_date(_tag(block, "pubDate", "dc:date"))
            title = clean_text(_tag(block, "title"))
            link = clean_text(_tag(block, "link"))
            if not (title and link and published) or published < since:
                continue
            articles.append(Article(
                title=title,
                summary=first_sentence(clean_text(_tag(block, "description"))),
                url=link, outlet=outlet, published=published, via="RSS",
            ))
        return articles, SourceStatus(name, True, len(articles))
    except Exception as e:  # 소스 하나가 실패해도 전체는 계속
        return [], SourceStatus(name, False, error=str(e)[:120])


# ---------------------------------------------------------------------------
# 검색 공통
# ---------------------------------------------------------------------------
def outlet_from_url(url: str) -> str | None:
    host = urllib.parse.urlparse(url).hostname or ""
    host = host.removeprefix("www.").removeprefix("m.")
    if config.OUTLETS is None:
        return host
    # 가장 긴 도메인부터 매칭 (biz.chosun.com이 chosun.com보다 우선)
    for domain in sorted(config.OUTLETS, key=len, reverse=True):
        if host == domain or host.endswith("." + domain):
            return config.OUTLETS[domain]
    return None


def run_queries(label: str, fetch_one, workers: int) -> tuple[list[Article], SourceStatus]:
    """검색어 전체를 돌리고, 실패한 검색어는 모아서 상태에 기록."""
    queries = [q for qs in config.SEARCH_QUERIES.values() for q in qs]
    articles: list[Article] = []
    failed: list[str] = []

    def run(q):
        try:
            return fetch_one(q), None
        except urllib.error.HTTPError as e:
            hint = {401: "인증 실패 — 키 또는 앱의 '검색' API 권한 확인", 429: "호출 한도 초과",
                    503: "일시 차단 — 잠시 후 재시도"}.get(e.code, "")
            return [], f"{q}: HTTP {e.code} {hint}".strip()
        except Exception as e:
            return [], f"{q}: {str(e)[:60]}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for found, err in pool.map(run, queries):
            articles.extend(found)
            if err:
                failed.append(err)

    error = f"검색어 {len(failed)}개 실패: " + "; ".join(failed[:3]) if failed else ""
    return articles, SourceStatus(f"{label} (검색어 {len(queries)}개)", len(failed) < len(queries), len(articles), error)


# ---------------------------------------------------------------------------
# 구글 뉴스 RSS 검색 (주력, 키 불필요)
# ---------------------------------------------------------------------------
def fetch_google_query(query: str, since: datetime) -> list[Article]:
    days = max(1, -(-config.WINDOW_HOURS // 24))  # 올림
    params = urllib.parse.urlencode({"q": f"{query} when:{days}d", "hl": "ko", "gl": "KR", "ceid": "KR:ko"})
    text = decode(http_get(f"{config.GOOGLE_NEWS_URL}?{params}"))

    articles = []
    for block in re.findall(r"<item>.*?</item>", text, flags=re.S):
        published = parse_date(_tag(block, "pubDate"))
        source = re.search(r'<source url="([^"]*)"[^>]*>(.*?)</source>', block, flags=re.S)
        if not (published and source) or published < since:
            continue
        outlet = outlet_from_url(source.group(1))
        if outlet is None:
            continue
        source_name = clean_text(source.group(2))
        title = clean_text(_tag(block, "title"))
        while source_name and title.endswith(f" - {source_name}"):  # "제목 - 언론사" 꼬리 제거
            title = title[: -len(f" - {source_name}")]
        articles.append(Article(
            title=title, summary="",  # 구글 RSS에는 본문 첫 문장이 없음 (같은 사건의 언론사 RSS 기사에서 채워짐)
            url=clean_text(_tag(block, "link")), outlet=outlet, published=published, via="구글",
        ))
    return articles


def fetch_google(since: datetime) -> tuple[list[Article], list[SourceStatus]]:
    # 동시 요청을 많이 보내면 구글이 일시 차단(503)할 수 있어 3개로 제한
    articles, status = run_queries("구글 뉴스 검색", lambda q: fetch_google_query(q, since), workers=3)
    return articles, [status]


# ---------------------------------------------------------------------------
# 네이버 뉴스 검색 API (선택)
# ---------------------------------------------------------------------------
def fetch_naver_query(query: str, since: datetime, client_id: str, secret: str) -> list[Article]:
    endpoint, id_header, secret_header = config.NAVER_ENDPOINTS[config.NAVER_API]
    articles = []
    for page in range(config.NAVER_MAX_PAGES):
        params = urllib.parse.urlencode({"query": query, "display": 100, "start": 1 + page * 100,
                                         "sort": "date", "format": "json"})
        body = http_get(f"{endpoint}?{params}", headers={id_header: client_id, secret_header: secret})
        items = json.loads(body).get("items", [])
        oldest = None
        for it in items:
            published = parse_date(it.get("pubDate", ""))
            if published is None:
                continue
            oldest = published if oldest is None else min(oldest, published)
            url = it.get("originallink") or it.get("link", "")
            outlet = outlet_from_url(url)
            if published < since or outlet is None:
                continue
            articles.append(Article(
                title=clean_text(it.get("title", "")),
                summary=first_sentence(clean_text(it.get("description", ""))),
                url=url, outlet=outlet, published=published, via="네이버",
            ))
        if len(items) < 100 or (oldest and oldest < since):
            break  # 기간 밖으로 넘어가면 다음 페이지 불필요
    return articles


def fetch_naver(since: datetime) -> tuple[list[Article], list[SourceStatus]]:
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    secret = os.environ.get("NAVER_CLIENT_SECRET", "")
    if not (client_id and secret):
        return [], [SourceStatus("네이버 뉴스 검색 (선택)", True, error="키 없음 — 건너뜀")]
    articles, status = run_queries("네이버 뉴스 검색", lambda q: fetch_naver_query(q, since, client_id, secret), workers=4)
    return articles, [status]


# ---------------------------------------------------------------------------
# 시세
# ---------------------------------------------------------------------------
def fetch_quote(group: str, name: str, symbol: str | None, scale: float, unit: str) -> Quote:
    q = Quote(group=group, name=name, unit=unit)
    if symbol is None:
        q.note = "확인 못 함 (무료 소스 없음)"
        return q
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=5d&interval=1d"
        result = json.loads(http_get(url))["chart"]["result"][0]
        meta = result["meta"]
        price = meta["regularMarketPrice"]
        as_of = datetime.fromtimestamp(meta["regularMarketTime"], KST)
        offset = timedelta(seconds=meta.get("gmtoffset", 0))

        # 직전 거래일 종가: 마지막 일봉이 현재가와 같은 날이면 그 앞 봉을 사용
        bars = [(datetime.fromtimestamp(t, timezone.utc) + offset).date()
                for t in result.get("timestamp", [])]
        closes = result["indicators"]["quote"][0]["close"]
        pairs = [(d, c) for d, c in zip(bars, closes) if c is not None]
        today = (datetime.fromtimestamp(meta["regularMarketTime"], timezone.utc) + offset).date()
        prev_closes = [c for d, c in pairs if d < today]
        prev = prev_closes[-1] if prev_closes else None

        q.price = price * scale
        q.as_of = as_of
        if prev:
            q.change = (price - prev) * scale
            q.pct = (price - prev) / prev * 100
        if datetime.now(KST) - as_of > timedelta(days=4):
            q.flags.append("stale")
    except Exception as e:
        q.note = f"확인 못 함 ({str(e)[:40]})"
    return q


def fetch_quotes() -> list[Quote]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        quotes = list(pool.map(lambda args: fetch_quote(*args), config.QUOTES))
    for q in quotes:
        if q.pct is None:
            continue
        big = (
            (q.group in ("국내", "미국", "아시아") and q.name != "VIX" and abs(q.pct) >= config.BIG_MOVE["index_pct"])
            or (q.group == "유가" and abs(q.pct) >= config.BIG_MOVE["oil_pct"])
            or (q.name == "원/달러" and abs(q.change or 0) >= config.BIG_MOVE["usdkrw_won"])
        )
        if big:
            q.flags.append("big")
    return quotes


# ---------------------------------------------------------------------------
# 전체 수집
# ---------------------------------------------------------------------------
def collect(now: datetime) -> tuple[list[Article], list[SourceStatus], list[Quote]]:
    since = now - timedelta(hours=config.WINDOW_HOURS)
    articles: list[Article] = []
    statuses: list[SourceStatus] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        rss_jobs = [pool.submit(fetch_rss, o, s, u, since) for o, s, u in config.RSS_FEEDS]
        search_jobs = [pool.submit(fetch_google, since), pool.submit(fetch_naver, since)]
        quotes_job = pool.submit(fetch_quotes)

        for job in search_jobs:
            found, status = job.result()
            articles += found
            statuses += status
        for job in rss_jobs:
            found, status = job.result()
            articles += found
            statuses.append(status)
        quotes = quotes_job.result()

    return articles, statuses, quotes
