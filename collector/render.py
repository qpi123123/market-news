"""결과 페이지(HTML 1장) 생성 — ver.3

화면 구성
- 상단 바(고정): 시장 지표 · 보기(주식 관련 / 국내 전체 / 해외 / 관심) · 검색 · 테마 · 정렬 · NEW · 관심종목
- 시장 지표: 버튼을 누를 때만 펼침
- 국내: 한 줄에 한 건. 기본 중요도순, 최신순이면 장 전·장중·장 마감 후 구분선
- 해외: 중요도 상위 20건만 카드로 (제목 + 기사 앞부분)
- 오른쪽 패널: 요약 → 종목·AI 추정 → 같은 사건 보도 → 원문
- 읽음·NEW·관심종목: 서버 없이 브라우저 localStorage에만 저장
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from html import escape

import config
import keywords as kw
from process import OLD_NEWS_DAYS, Story
from sources import Quote, SourceStatus

STAR_N = 15
WEEKDAYS = "월화수목금토일"
DIR_TEXT = {"+": "상승 압력 가능성", "-": "하락 압력 가능성", "0": "방향 불분명"}


# ---------------------------------------------------------------------------
# 포맷 도우미
# ---------------------------------------------------------------------------
def md(dt: datetime) -> str:
    return f"{dt.month}/{dt.day}"


def fmt_number(value: float) -> str:
    if abs(value) >= 10000:
        return f"{value:,.0f}"
    return f"{value:,.2f}" if abs(value) >= 10 else f"{value:,.3f}"


def safe_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else ""


def story_id(s: Story) -> str:
    return hashlib.md5(s.lead.url.encode()).hexdigest()[:10]


def short_time(dt: datetime, now: datetime) -> str:
    return f"{dt:%H:%M}" if (now - dt).total_seconds() < 86400 else md(dt)


def session_of(dt: datetime) -> tuple[str, str]:
    """(정렬 키, 구분선 이름). 국내 장 시간 기준."""
    day = f"{md(dt)}({WEEKDAYS[dt.weekday()]})"
    if dt.weekday() >= 5:
        return f"{dt:%Y%m%d}0", f"{day} 주말"
    minutes = dt.hour * 60 + dt.minute
    if minutes < 9 * 60:
        return f"{dt:%Y%m%d}1", f"{day} 장 전 · 미국장 시간대 포함"
    if minutes < 15 * 60 + 30:
        return f"{dt:%Y%m%d}2", f"{day} 장중"
    return f"{dt:%Y%m%d}3", f"{day} 장 마감 후"


def change_html(q: Quote) -> str:
    if q.pct is None:
        return ""
    d = "up" if q.change > 0 else "down" if q.change < 0 else ""
    arrow = {"up": "▲", "down": "▼"}.get(d, "")
    value = f"{abs(q.change):.2f}%p" if q.unit == "%" else f"{abs(q.pct):.2f}%"
    return f'<i class="{d}">{arrow} {value}</i>'


# ---------------------------------------------------------------------------
# 시장 지표 (접힘)
# ---------------------------------------------------------------------------
def fmt_eok(v: float) -> str:
    """억원 → '−1조 2,682억' / '+3,499억'."""
    sign = "+" if v > 0 else "−" if v < 0 else ""
    v = abs(round(v))
    jo, eok = divmod(v, 10000)
    return f"{sign}{jo}조 {eok:,}억" if jo else f"{sign}{eok:,}억"


def render_flows(flows: dict) -> str:
    """투자자별 순매수 카드 (마감시황 기사 기준)."""
    if not flows:
        return ('<div class="mcard"><h3>투자자별 순매수</h3>'
                '<p class="note">아직 기록 없음 — 장 마감 기사가 나온 뒤 표시</p></div>')
    rows, sources = [], []
    for key, label in (("kospi", "코스피"), ("kosdaq", "코스닥")):
        f = flows.get(key)
        if not f:
            continue
        cells = "".join(
            f'<span class="fv {"up" if f.get(n, 0) > 0 else "down" if f.get(n, 0) < 0 else ""}">'
            f'<small>{n}</small>{fmt_eok(f[n]) if n in f else "–"}</span>'
            for n in ("외국인", "기관", "개인"))
        rows.append(f'<div class="fl-row"><span class="fl-m">{label}</span>{cells}</div>')
        src = f'{f["date"][5:7]}/{f["date"][8:10]} {f.get("time", "")} {f["outlet"]}'
        sources.append(f'<a href="{escape(safe_url(f["url"]))}" target="_blank" rel="noopener" '
                       f'title="{escape(f.get("title", ""))}">{label}: {escape(src)}</a>')
    return (f'<div class="mcard mflow"><h3>투자자별 순매수 <small>마감 기준</small></h3>{"".join(rows)}'
            f'<p class="note fl-src">출처 · {" · ".join(sources)}<br>마감시황 기사 숫자. 매체·시점마다 조금씩 다를 수 있음</p></div>')


def render_market(quotes: list[Quote], now: datetime, flows: dict | None = None) -> str:
    groups: dict[str, list[Quote]] = {}
    for q in quotes:
        groups.setdefault(q.group, []).append(q)
    cards = []
    for group, items in groups.items():
        rows = []
        for q in items:
            if q.price is None:
                rows.append(f'<div class="mq missing"><span>{escape(q.name)}</span><span class="mv">확인 못 함</span></div>')
                continue
            as_of = "" if not q.as_of else (f"{q.as_of:%H:%M}" if q.as_of.date() == now.date() else md(q.as_of))
            cls = "mq" + (" big" if "big" in q.flags else "") + (" stale" if "stale" in q.flags else "")
            rows.append(f'<div class="{cls}"><span>{escape(q.name)}</span><b class="mv">{fmt_number(q.price)}</b>'
                        f'{change_html(q)}<small>{as_of}</small></div>')
        cards.append(f'<div class="mcard"><h3>{escape(group)}</h3>{"".join(rows)}</div>')
    cards.insert(1, render_flows(flows or {}))   # '국내' 지수 바로 다음
    return (f'<section id="market" hidden><div class="mgrid">{"".join(cards)}</div>'
            f'<p class="note">등락은 직전 거래일 종가 대비 · 오른쪽은 기준일(오늘이면 KST 시각) · '
            f'흐린 값은 4일 이상 갱신 안 됨 · 국고채·두바이유는 무료 소스 없음</p></section>')


def market_button(quotes: list[Quote]) -> str:
    kospi = next((q for q in quotes if q.name == "코스피" and q.price), None)
    head = f'<span class="mk-l">코스피</span><b>{fmt_number(kospi.price)}</b>{change_html(kospi)}' if kospi else "시장 지표"
    n_big = sum("big" in q.flags for q in quotes)
    badge = f'<span class="bigc">큰 변동 {n_big}</span>' if n_big else ""
    return f'<span class="caret">▾</span>{head}{badge}'


# ---------------------------------------------------------------------------
# 국내 한 줄 / 해외 카드
# ---------------------------------------------------------------------------
def common_attrs(s: Story, sid: str) -> str:
    search = escape(" ".join([*(a.title for a in s.articles[:5]), s.summary, *s.outlets,
                              *(st[0] for st in s.stocks), *s.sectors]).lower())
    return (f'data-id="{sid}" data-cats="{" ".join(s.categories)}" data-themes="{escape(" ".join(s.themes))}" '
            f'data-stocks="{escape("|".join(st[0] for st in s.stocks))}" '
            f'data-time="{s.first_published.timestamp():.0f}" data-search="{search}"')


def render_row(s: Story, sid: str, now: datetime, starred: bool) -> str:
    bucket_key, bucket_label = session_of(s.first_published)
    stocks = "".join(f'<span class="sk">{escape(st[0])}</span>' for st in s.stocks[:2])
    sector = s.sectors[0] if s.sectors else ""
    tag = f'<span class="sec" title="영향 섹터">{escape(sector)}</span>' if sector else ""
    old = s.days_old >= OLD_NEWS_DAYS
    classes = ("row" + (" top" if starred else "") + (" old" if old else "")
               + (" rel" if s.stock_related else "") + (" world" if s.is_world else ""))
    return (
        f'<div class="{classes}" {common_attrs(s, sid)} data-score="{s.score:.1f}" '
        f'data-bucket="{bucket_key}" data-label="{escape(bucket_label)}">'
        f'<span class="tm">{short_time(s.first_published, now)}</span>'
        f'<span class="st">{"★" if starred else ""}</span>'
        f'<span class="ti">{escape(s.lead.title)}</span>'
        f'<span class="meta">{"<span class=oldb>%d일 전</span>" % s.days_old if old else ""}{tag}{stocks}'
        f'<span class="n">{len(s.outlets)}곳</span></span></div>'
    )


def render_world_card(s: Story, sid: str, now: datetime, rank: int) -> str:
    cat = s.world_cats[0] if s.world_cats else "국제"
    sector = f'<span class="sec">{escape(s.sectors[0])}</span>' if s.sectors else ""
    lead = s.lead_text or s.summary
    lead_html = f'<p class="wl">{escape(lead)}</p>' if lead else ""
    return (
        f'<article class="wcard" {common_attrs(s, sid)} data-score="{s.world_score:.1f}">'
        f'<div class="wtop"><span class="wrank">{rank}</span><span class="wcat c-{escape(cat)}">{escape(cat)}</span>'
        f'{sector}<span class="wmeta">{short_time(s.first_published, now)} · {len(s.outlets)}곳</span></div>'
        f'<h3>{escape(s.lead.title)}</h3>{lead_html}</article>'
    )


def panel_data(s: Story) -> dict:
    # 원문 링크: 구글 경유 주소보다 언론사 직접 주소를 우선
    direct = next((a for a in s.articles if a.via != "구글"), None)
    source = direct or s.lead
    ai = s.ai or {}
    return {
        "title": s.lead.title,
        "first": f"{md(s.first_published)} {s.first_published:%H:%M}",
        "old": s.days_old if s.days_old >= OLD_NEWS_DAYS else 0,
        "outlets": s.outlets,
        "tags": ([c for c in s.world_cats] if s.is_world else [])
                + [kw.CATEGORIES[c][0] for c in s.categories if c != "issue"] + s.themes,
        "related": s.stock_related,
        "stocks": [[n, c] for n, c, _ in s.stocks],
        "sectors": s.sectors,
        "ai": {"sector": ai.get("sector", ""), "dir": DIR_TEXT.get(ai.get("dir", "0"), "")} if ai else None,
        "lead": s.lead_text or s.summary,
        "url": safe_url(source.url),
        "outlet": source.outlet,
        "via_google": direct is None,
        "arts": [[a.outlet, f"{md(a.published)} {a.published:%H:%M}", a.title, safe_url(a.url)]
                 for a in s.articles[:20]],
        "more": max(0, len(s.articles) - 20),
    }


# ---------------------------------------------------------------------------
# 테마 흐름 (날짜별 기록 기반)
# ---------------------------------------------------------------------------
# 순차 파랑 (dataviz 기준 팔레트 blue 100→600). 0건은 빈 칸.
HEAT = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#5598e7", "#3987e5", "#256abf", "#184f95"]


def render_flow(log: dict, dates: list, now: datetime) -> str:
    from datetime import timedelta
    today = now.date()
    days = [today - timedelta(days=i) for i in range(13, -1, -1)]          # 최근 14일
    week = [d.isoformat() for d in days[7:]]                                # 최근 7일
    prev = [d.isoformat() for d in days[:7]]                                # 그 전 7일

    def total(theme, keys):
        return sum(log.get(k, {}).get(theme, 0) for k in keys)

    themes = sorted({t for k in (week + prev) for t in log.get(k, {})},
                    key=lambda t: (-total(t, week), -total(t, prev), t))
    n_days = len(log)
    has_prev = any(k in log for k in prev)

    # 1) 주간 변화
    if has_prev:
        diffs = [(t, total(t, week) - total(t, prev), total(t, week), total(t, prev)) for t in themes]
        ups = sorted([d for d in diffs if d[1] > 0], key=lambda d: -d[1])[:6]
        downs = sorted([d for d in diffs if d[1] < 0], key=lambda d: d[1])[:6]
        scale = max([abs(d[1]) for d in ups + downs] or [1])

        def bars(rows, cls):
            if not rows:
                return '<p class="fl-none">해당 없음</p>'
            return "".join(
                f'<div class="fb" title="{escape(t)}: 이번 주 {w}건 · 지난주 {p}건">'
                f'<span class="fb-n">{escape(t)}</span><span class="fb-track"><span class="fb-bar {cls}" '
                f'style="width:{max(4, abs(d) / scale * 100):.0f}%"></span></span>'
                f'<span class="fb-v">{"+" if d > 0 else "−"}{abs(d)}</span><span class="fb-sub">{p}→{w}</span></div>'
                for t, d, w, p in rows)
        weekly = (f'<div class="fl-cols"><div><h3>뜨는 테마 <small>이번 주 − 지난주 건수</small></h3>{bars(ups, "up")}</div>'
                  f'<div><h3>지는 테마</h3>{bars(downs, "down")}</div></div>')
    else:
        top = [(t, total(t, week)) for t in themes[:10]]
        scale = max([v for _, v in top] or [1])
        weekly = ('<p class="fl-note">지난주 기록이 쌓이면(기록 8일째부터) 이번 주와 지난주를 비교한 뜨는·지는 테마가 나옴. '
                  '지금은 이번 주 누적 순위.</p>' + "".join(
                      f'<div class="fb" title="{escape(t)}: 이번 주 {v}건"><span class="fb-n">{escape(t)}</span>'
                      f'<span class="fb-track"><span class="fb-bar seq" style="width:{max(4, v / scale * 100):.0f}%"></span></span>'
                      f'<span class="fb-v">{v}</span><span class="fb-sub"></span></div>' for t, v in top))

    # 2) 히트맵 (테마 × 최근 14일)
    vmax = max([log.get(d.isoformat(), {}).get(t, 0) for d in days for t in themes] or [1]) or 1
    head = "".join(
        f'<th class="{"today" if d == today else ""}{" we" if d.weekday() >= 5 else ""}">'
        f'{d.month}/{d.day}<small>{WEEKDAYS[d.weekday()]}</small></th>' for d in days)
    body = []
    for t in themes:
        cells = []
        for d in days:
            k = d.isoformat()
            if k not in log:
                cells.append('<td class="nd" title="기록 없음"></td>')
                continue
            v = log[k].get(t, 0)
            if not v:
                cells.append(f'<td class="z" title="{escape(t)} · {d.month}/{d.day} · 0건">·</td>')
                continue
            step = min(len(HEAT) - 1, max(0, round(v / vmax * (len(HEAT) - 1))))
            ink = "#fff" if step >= 4 else "#191f28"
            cells.append(f'<td style="background:{HEAT[step]};color:{ink}" '
                         f'title="{escape(t)} · {d.month}/{d.day} · 주식 관련 뉴스 {v}건">{v}</td>')
        body.append(f'<tr><th class="rt">{escape(t)}</th>{"".join(cells)}</tr>')
    swatches = "".join(f'<i style="background:{c}"></i>' for c in HEAT)
    heat = (f'<div class="hm-wrap"><table class="hm"><thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{"".join(body) or "<tr><td>기록 없음</td></tr>"}</tbody></table></div>'
            f'<div class="hm-legend"><span>적음</span>{swatches}<span>많음</span>'
            f'<span class="hm-k">· 0건</span><span class="hm-k"><i class="nd"></i> 기록 없음</span></div>')

    archive = "".join(f'<a href="archive/{d}.html">{d[5:7]}/{d[8:10]}</a>' for d in dates[:60]) or "아직 없음"
    return (f'<section id="flow" hidden><p class="fl-note">테마별 주식 관련 뉴스 건수 기록 · {n_days}일째 '
            f'(하루 마지막 수집 기준). 테마는 키워드 사전 기준. 칸에 마우스를 올리면 건수 표시.</p>'
            f'<div class="fl-card"><h2>이번 주 테마 변화</h2>{weekly}</div>'
            f'<div class="fl-card"><h2>최근 14일 테마 흐름</h2>{heat}</div>'
            f'<div class="fl-card"><h2>지난 날짜 페이지</h2><div class="arch">{archive}</div></div></section>')


# ---------------------------------------------------------------------------
# 수집 정보 (맨 아래, 접힘)
# ---------------------------------------------------------------------------
def render_info(statuses: list[SourceStatus], n_articles: int, n_ai: int, stories: list[Story],
                now: datetime, window_hours: int) -> str:
    failed = sum(not st.ok for st in statuses)
    rows = "".join(
        f'<tr class="{"ok" if st.ok else "fail"}"><td>{"✓" if st.ok else "✕"}</td>'
        f'<td>{escape(st.name)}</td><td class="num">{st.count:,}</td><td>{escape(st.error)}</td></tr>'
        for st in statuses
    )
    n_rel = sum(s.stock_related for s in stories)
    n_outlets = len({o for s in stories for o in s.outlets})
    health = f"소스 {failed}개 실패" if failed else "소스 모두 정상"
    return (
        f'<details class="info"><summary>수집 정보 · {md(now)} {now:%H:%M} · 지난 {window_hours}시간 · 기사 {n_articles:,}건 '
        f'(AI 작성 {n_ai}건 제외) → 사건 {len(stories):,}개, 그중 주식 관련 {n_rel:,}개 · 언론사 {n_outlets}곳 · {health}</summary>'
        f'<p>주식 관련: AI 판별(Groq)이 된 기사는 그 결과, 안 된 기사는 키워드 규칙(시장 검색어·종목·테마·시장 키워드·언론사 5곳 이상). '
        f'★ = 주식 관련 중 중요도 상위 {STAR_N}건. 해외 = 여러 언론사 보도 + 분쟁·테러·정치·외교·경제 키워드 + AI 중요도 상위 {config.WORLD_TOP_N}건. '
        f'시각 = 첫 보도 시각(KST). AI는 분류만 하고 기사·요약은 쓰지 않음.</p>'
        f'<table><thead><tr><th></th><th>소스</th><th>건수</th><th>비고</th></tr></thead><tbody>{rows}</tbody></table>'
        f'<p>자동 수집 결과. 투자 판단 전 원문 확인.</p></details>'
    )


# ---------------------------------------------------------------------------
# 페이지
# ---------------------------------------------------------------------------
def render_page(stories: list[Story], quotes: list[Quote], statuses: list[SourceStatus],
                n_articles: int, n_ai: int, now: datetime, window_hours: int,
                stock_list: list[dict] | None = None, theme_log: dict | None = None,
                archive_dates: list[str] | None = None, flows: dict | None = None) -> str:
    stories = sorted(stories, key=lambda s: s.score, reverse=True)
    starred = {id(s) for s in [s for s in stories if s.stock_related][:STAR_N]}
    ids = {id(s): story_id(s) for s in stories}

    by_time = sorted(stories, key=lambda s: s.first_published, reverse=True)
    rows = "".join(render_row(s, ids[id(s)], now, id(s) in starred) for s in by_time)

    world = sorted([s for s in stories if s.is_world], key=lambda s: s.world_score, reverse=True)[:config.WORLD_TOP_N]
    world_cards = "".join(render_world_card(s, ids[id(s)], now, i + 1) for i, s in enumerate(world))

    data = json.dumps({ids[id(s)]: panel_data(s) for s in stories}, ensure_ascii=False).replace("</", "<\\/")
    names = json.dumps(sorted({s["name"] for s in (stock_list or [])}), ensure_ascii=False).replace("</", "<\\/")

    used_themes = sorted({t for s in stories for t in s.themes})
    chips = '<button class="chip on" data-cat="">전체</button>' + "".join(
        f'<button class="chip" data-cat="{key}">{escape(label)}</button>' for key, (label, _) in kw.CATEGORIES.items()
    )
    themes = '<option value="">테마</option>' + "".join(f'<option>{escape(t)}</option>' for t in used_themes)
    n_rel = sum(s.stock_related for s in stories)
    n_dom = sum(not s.is_world for s in stories)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>증시 뉴스 · {md(now)} {now:%H:%M}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}</style>
</head>
<body>
<header class="bar">
  <div class="bar-row">
    <span class="logo">증시 뉴스</span>
    <button id="mk" class="mk" type="button" title="시장 지표 펼치기">{market_button(quotes)}</button>
    <nav class="seg" id="scope">
      <button class="on" data-scope="rel" type="button">주식 관련<span>{n_rel:,}</span></button>
      <button data-scope="dom" type="button">국내 전체<span>{n_dom:,}</span></button>
      <button data-scope="world" type="button">해외 핵심<span>{len(world)}</span></button>
      <button data-scope="watch" type="button">관심<span id="watchcount">0</span></button>
      <button data-scope="flow" type="button">테마 흐름</button>
    </nav>
    <div class="ctl">
      <input id="q" type="search" placeholder="종목·키워드·언론사 검색">
      <select id="theme">{themes}</select>
      <select id="sort"><option value="score">중요도순</option><option value="time">최신순 (장 시간 구분)</option></select>
      <button id="newonly" class="pill new" type="button" hidden>NEW <span id="newcount"></span></button>
      <button id="watchbtn" class="pill" type="button">관심종목 설정</button>
      <span class="updated" title="수집 시각">{md(now)} {now:%H:%M} 갱신</span>
    </div>
  </div>
  <div class="bar-row sub" id="chiprow"><div class="chips">{chips}</div><span id="shown" class="shown"></span></div>
</header>

{render_market(quotes, now, flows)}

<div id="watchbox" class="watchbox" hidden>
  <div class="wb-in">
    <input id="watchin" list="stocknames" placeholder="종목명 입력 후 Enter (예: 삼성전자)">
    <datalist id="stocknames"></datalist>
    <div id="watchlist" class="wb-list"></div>
    <p class="note">관심종목이 거론된 뉴스는 파란 막대로 표시되고 '관심' 보기에 모임. 이 브라우저에만 저장.</p>
  </div>
</div>

<div class="wrap open">
  <main>
    <div id="list">{rows}</div>
    <div id="world" hidden>
      <p class="wnote">여러 언론사가 다룬 해외 뉴스 중 분쟁·테러·정치·외교·경제 비중과 AI 중요도로 고른 상위 {len(world)}건. 요약은 언론사 기사 앞부분.</p>
      <div class="wgrid">{world_cards}</div>
    </div>
    {render_flow(theme_log or {}, archive_dates or [], now)}
    <p class="empty" id="empty" hidden>조건에 맞는 뉴스 없음</p>
    {render_info(statuses, n_articles, n_ai, stories, now, window_hours)}
  </main>
  <aside id="panel">
    <button id="close" class="close" type="button" title="선택 해제 (Esc)" hidden>✕</button>
    <div id="pbody"></div>
  </aside>
</div>
<script>const GENERATED = {json.dumps(now.isoformat())}; const DATA = {data}; const STOCK_NAMES = {names};{JS}</script>
</body>
</html>"""


CSS = """
:root{
  --bg:#fff;--soft:#f7f8fa;--soft2:#f2f4f6;--text:#191f28;--sub:#4e5968;--faint:#8b95a1;--line:#eceef1;
  --accent:#3182f6;--accent-soft:#e8f3ff;--up:#f04452;--down:#3182f6;--big:#fff4e0;--star:#ffb000;--new:#f04452;
  --shadow:0 1px 2px rgba(0,27,55,.06),0 4px 16px rgba(0,27,55,.05);
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html,body{margin:0;background:var(--bg);color:var(--text)}
body{font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:14.5px;line-height:1.5;-webkit-font-smoothing:antialiased;letter-spacing:-.01em}
button,input,select{font:inherit;color:inherit;letter-spacing:inherit}
.up{color:var(--up)}.down{color:var(--down)}

/* 상단 바 */
.bar{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.96);backdrop-filter:blur(8px);
  border-bottom:1px solid var(--line)}
.bar-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;padding:10px 20px}
.bar-row.sub{padding:0 20px 8px}
.logo{font-weight:800;font-size:16px;letter-spacing:-.03em;margin-right:4px}
.mk{display:flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--bg);border-radius:10px;
  padding:5px 12px;cursor:pointer;font-size:13px;white-space:nowrap;font-variant-numeric:tabular-nums}
.mk:hover{background:var(--soft)}
.mk .mk-l{color:var(--faint)}
.mk i{font-style:normal;font-size:12.5px}
.caret{color:var(--faint);font-size:11px;transition:transform .15s;transform:rotate(-90deg)}
.mk.open .caret{transform:none}
.bigc{background:var(--big);color:#b25e00;border-radius:6px;padding:0 6px;font-size:11.5px;font-weight:600}
.seg{display:flex;gap:2px;background:var(--soft2);border-radius:10px;padding:3px}
.seg button{border:0;background:none;border-radius:8px;padding:4px 12px;font-size:13.5px;cursor:pointer;color:var(--sub);font-weight:500}
.seg button span{color:var(--faint);font-size:11.5px;margin-left:5px;font-variant-numeric:tabular-nums}
.seg button.on{background:var(--bg);color:var(--text);font-weight:700;box-shadow:0 1px 3px rgba(0,27,55,.1)}
.ctl{display:flex;gap:6px;align-items:center;flex:1 1 360px;justify-content:flex-end}
.ctl input,.ctl select{font-size:13px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg)}
.ctl input{flex:0 1 230px;min-width:0}
.ctl input:focus,.ctl select:focus,.wb-in input:focus{outline:2px solid var(--accent-soft);border-color:var(--accent)}
.pill{border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:5px 12px;font-size:12.5px;cursor:pointer;color:var(--sub);white-space:nowrap}
.pill:hover{background:var(--soft)}
.pill.new{color:var(--new);font-weight:700;border-color:#ffd6da}
.pill.new.on{background:var(--new);color:#fff}
.updated,.shown{color:var(--faint);font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}
.chips{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;flex:1}
.chip{flex:0 0 auto;border:1px solid var(--line);background:var(--bg);color:var(--sub);border-radius:999px;padding:3px 12px;font-size:12.5px;cursor:pointer}
.chip:hover{background:var(--soft)}
.chip.on{background:var(--text);border-color:var(--text);color:#fff}

/* 시장 지표 */
#market{background:var(--soft);border-bottom:1px solid var(--line);padding:14px 20px}
.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px}
.mcard{background:var(--bg);border-radius:12px;padding:10px 14px;box-shadow:var(--shadow)}
.mcard h3{margin:0 0 4px;font-size:12px;color:var(--faint);font-weight:600}
.mq{display:grid;grid-template-columns:1fr auto 72px 34px;gap:6px;align-items:baseline;font-size:13px;padding:2px 0;font-variant-numeric:tabular-nums}
.mq .mv{font-weight:700}
.mq i{font-style:normal;text-align:right;font-size:12.5px}
.mq small{text-align:right;color:var(--faint);font-size:11px}
.mq.big{background:var(--big);border-radius:6px;margin:0 -6px;padding:2px 6px}
.mq.stale,.mq.missing{opacity:.45}
.mq.missing{grid-template-columns:1fr auto}
.mq.missing .mv{font-weight:400;font-size:12px;color:var(--faint)}
.note{margin:8px 0 0;font-size:11.5px;color:var(--faint)}
.mflow h3 small{font-weight:400;margin-left:4px}
.fl-row{display:grid;grid-template-columns:44px repeat(3,1fr);gap:6px;align-items:baseline;padding:3px 0;font-size:13px;font-variant-numeric:tabular-nums}
.fl-row+.fl-row{border-top:1px dashed var(--line)}
.fl-m{font-weight:600}
.fv{font-weight:700;text-align:right;white-space:nowrap}
.fv small{display:block;font-size:10.5px;font-weight:500;color:var(--faint)}
.fl-src a{color:var(--faint)}
.fl-src a:hover{color:var(--accent)}

/* 관심종목 설정 */
.watchbox{border-bottom:1px solid var(--line);background:var(--soft);padding:12px 20px}
.wb-in input{width:min(360px,100%);padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:14px}
.wb-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.wb-list span{background:var(--accent-soft);color:var(--accent);border-radius:999px;padding:3px 6px 3px 12px;font-size:13px;font-weight:600}
.wb-list button{border:0;background:none;color:var(--accent);cursor:pointer;padding:0 4px}

/* 목록 */
.wrap{display:grid;grid-template-columns:minmax(0,1fr)}
.wrap.open{grid-template-columns:minmax(0,1fr) min(42vw,640px)}
main{min-width:0}
.div{position:sticky;top:var(--bar-h,92px);z-index:2;background:var(--soft);padding:7px 20px;
  font-size:12px;font-weight:700;color:var(--sub);border-bottom:1px solid var(--line)}
.row{position:relative;display:grid;grid-template-columns:42px 14px minmax(0,1fr) auto;align-items:center;column-gap:10px;
  padding:0 20px;min-height:38px;border-bottom:1px solid var(--line);cursor:pointer;transition:background .08s}
.row:hover{background:var(--soft)}
.row.sel{background:var(--accent-soft)}
.row.watch::before{content:"";position:absolute;left:0;top:6px;bottom:6px;width:3px;border-radius:0 3px 3px 0;background:var(--accent)}
.tm{color:var(--faint);font-size:12.5px;font-variant-numeric:tabular-nums;line-height:1.1}
.st{color:var(--star);font-size:12px;text-align:center}
.ti{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:8px 0;font-weight:500}
.top .ti{font-weight:700}
.row.read .ti{color:var(--faint);font-weight:400}
.row.old .ti{color:var(--faint)}
.row.new .tm::after{content:"NEW";display:block;font-size:9.5px;font-weight:800;color:var(--new);margin-top:1px}
.meta{display:flex;gap:6px;align-items:center;white-space:nowrap}
.sk{font-size:12px;color:var(--accent);background:var(--accent-soft);padding:1px 8px;border-radius:6px;font-weight:600}
.sec{font-size:12px;color:#6a4bd8;background:#f3efff;padding:1px 8px;border-radius:6px;font-weight:600}
.sec::before{content:"◆ ";font-size:8px;vertical-align:2px}
.n{color:var(--faint);font-size:12px;font-variant-numeric:tabular-nums;min-width:32px;text-align:right}
.oldb{font-size:11.5px;color:#c77400;font-weight:600}
.wrap.open .sk{display:none}

/* 해외 핵심 */
#world{padding:16px 20px 8px}
.wnote{margin:0 0 12px;color:var(--faint);font-size:12.5px}
.wgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,420px),1fr));gap:12px}
.wcard{background:var(--bg);border:1px solid var(--line);border-radius:14px;padding:16px 18px;cursor:pointer;transition:box-shadow .12s,border-color .12s}
.wcard:hover{box-shadow:var(--shadow);border-color:transparent}
.wcard.sel{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.wcard.read h3{color:var(--faint)}
.wtop{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.wrank{font-weight:800;color:var(--accent);font-size:14px;min-width:18px}
.wcat{font-size:12px;font-weight:700;border-radius:6px;padding:1px 8px;background:var(--soft2);color:var(--sub)}
.c-분쟁·전쟁{background:#ffeef0;color:#d22030}.c-테러·안보{background:#fff1e6;color:#c25400}
.c-정치{background:#f0edff;color:#5b3fd6}.c-외교{background:#e9f7f1;color:#12835a}.c-경제{background:var(--accent-soft);color:var(--accent)}
.wmeta{color:var(--faint);font-size:12px;margin-left:auto;font-variant-numeric:tabular-nums}
.wcard h3{margin:0;font-size:16px;line-height:1.45;font-weight:700}
.wl{margin:6px 0 0;color:var(--sub);font-size:13.5px;line-height:1.6;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

/* 테마 흐름 */
#flow{padding:16px 20px 8px;max-width:1280px}
.fl-note{margin:0 0 12px;color:var(--faint);font-size:12.5px}
.fl-card{border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:14px}
.fl-card h2{font-size:15px;margin:0 0 12px}
.fl-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:8px 28px}
.fl-cols h3{font-size:13px;margin:0 0 6px;color:var(--sub)}
.fl-cols h3 small{color:var(--faint);font-weight:400;margin-left:6px}
.fl-none{color:var(--faint);font-size:13px;margin:4px 0}
.fb{display:grid;grid-template-columns:88px minmax(0,1fr) 40px 64px;align-items:center;gap:8px;padding:4px 0;font-size:13px}
.fb-n{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fb-track{height:10px;background:var(--soft2);border-radius:4px;overflow:hidden}
.fb-bar{display:block;height:100%;border-radius:0 4px 4px 0}
.fb-bar.up{background:var(--up)}.fb-bar.down{background:var(--down)}.fb-bar.seq{background:#3987e5}
.fb-v{text-align:right;font-weight:700;font-variant-numeric:tabular-nums}
.fb-sub{color:var(--faint);font-size:11.5px;font-variant-numeric:tabular-nums}
.hm-wrap{overflow-x:auto}
.hm{border-collapse:separate;border-spacing:2px;font-variant-numeric:tabular-nums}
.hm th{font-size:11.5px;color:var(--faint);font-weight:600;padding:2px 4px;white-space:nowrap}
.hm thead th{text-align:center;line-height:1.2}
.hm thead th small{display:block;font-weight:400}
.hm thead th.today{color:var(--accent)}
.hm thead th.we{color:#b0b8c1}
.hm th.rt{text-align:right;color:var(--sub);font-size:12.5px;padding-right:8px}
.hm td{width:40px;min-width:40px;height:28px;text-align:center;font-size:12px;font-weight:600;border-radius:4px;cursor:default}
.hm td:hover{outline:2px solid var(--text);outline-offset:-1px}
.hm td.z{background:var(--soft);color:#c4cad1;font-weight:400}
.hm td.nd{background:repeating-linear-gradient(45deg,var(--soft),var(--soft) 3px,#fff 3px,#fff 6px)}
.hm-legend{display:flex;align-items:center;gap:3px;margin-top:10px;font-size:11.5px;color:var(--faint)}
.hm-legend i{display:inline-block;width:18px;height:10px;border-radius:2px}
.hm-legend span{margin:0 4px}
.hm-legend .hm-k{margin-left:12px}
.hm-legend i.nd{background:repeating-linear-gradient(45deg,var(--soft),var(--soft) 3px,#fff 3px,#fff 6px);border:1px solid var(--line)}
.arch{display:flex;flex-wrap:wrap;gap:6px}
.arch a{border:1px solid var(--line);border-radius:8px;padding:3px 10px;font-size:12.5px;color:var(--sub);text-decoration:none;font-variant-numeric:tabular-nums}
.arch a:hover{border-color:var(--accent);color:var(--accent)}

/* 오른쪽 패널 */
#panel{position:sticky;top:var(--bar-h,92px);height:calc(100vh - var(--bar-h,92px));overflow-y:auto;
  border-left:1px solid var(--line);background:var(--bg);padding:28px 30px 36px;box-shadow:-12px 0 32px rgba(0,27,55,.04)}
.p-empty{height:100%;min-height:50vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;color:var(--faint)}
.p-empty-ic{font-size:34px;opacity:.5;margin-bottom:10px}
.p-empty p{margin:0 0 6px;font-size:14px;color:var(--sub)}
.p-empty small{font-size:12px}
.close{position:absolute;right:14px;top:12px;border:0;background:var(--soft2);border-radius:8px;width:30px;height:30px;
  font-size:13px;color:var(--sub);cursor:pointer}
.close:hover{background:var(--line)}
.p-tags{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:10px}
.p-tags span{font-size:12px;background:var(--soft2);color:var(--sub);padding:2px 9px;border-radius:6px;font-weight:500}
.p-tags .rel{background:var(--accent);color:#fff;font-weight:700}
#panel h2{font-size:21px;line-height:1.45;margin:0 36px 8px 0;letter-spacing:-.02em}
.p-meta{font-size:12.5px;color:var(--faint);margin-bottom:18px}
.p-meta b{color:var(--sub);font-weight:600}
.p-meta .oldb{margin-left:6px}
.p-lead{font-size:15.5px;line-height:1.8;margin:0 0 20px;color:#333d4b}
.p-none{font-size:13.5px;color:var(--faint);margin:0 0 20px;background:var(--soft);border-radius:10px;padding:12px 14px}
.p-box{background:var(--soft);border-radius:12px;padding:12px 14px;margin:0 0 20px}
.p-box h3{margin:0 0 6px}
.p-stocks{display:flex;flex-wrap:wrap;gap:6px}
.p-stocks a{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:3px 10px;font-size:13px;color:var(--text);text-decoration:none;font-weight:600}
.p-stocks a small{color:var(--faint);font-weight:400;margin-left:4px}
.p-stocks a:hover{border-color:var(--accent);color:var(--accent)}
.p-sec span{background:#f3efff;color:#6a4bd8;border-radius:8px;padding:3px 10px;font-size:13px;font-weight:600}
.p-ai{font-size:13.5px;color:var(--sub);margin-top:8px}
.p-ai b{color:var(--text)}
.p-ai small{display:block;color:var(--faint);font-size:11.5px;margin-top:2px}
#panel h3{font-size:12.5px;color:var(--faint);margin:0 0 8px;font-weight:600}
.p-arts{list-style:none;margin:0 0 24px;padding:0}
.p-arts li{padding:8px 0;border-bottom:1px solid var(--line)}
.p-arts li:last-child{border-bottom:0}
.p-arts a{color:var(--text);text-decoration:none;font-size:14px}
.p-arts a:hover{color:var(--accent)}
.p-arts small{display:block;color:var(--faint);font-size:11.5px;margin-bottom:1px}
.p-src{border-top:1px solid var(--line);padding-top:16px}
.p-src a.url{display:block;word-break:break-all;color:var(--accent);font-size:13px;margin:2px 0 12px;text-decoration:none}
.p-src a.url:hover{text-decoration:underline}
.p-src .via{color:var(--faint);font-size:12.5px;margin:0 0 12px}
.p-src a.open{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;border-radius:10px;padding:9px 18px;font-size:14px;font-weight:700}
.p-src a.open:hover{background:#1b64da}

.empty{text-align:center;color:var(--faint);padding:32px}
.info{margin:20px;font-size:12.5px;color:var(--faint)}
.info summary{cursor:pointer}
.info table{border-collapse:collapse;margin:8px 0;width:100%;max-width:980px}
.info td,.info th{text-align:left;padding:4px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.info .num{text-align:right;font-variant-numeric:tabular-nums}
.info tr.fail td{color:var(--up)}

/* 모바일 */
@media (max-width:760px){
  .bar-row{padding:8px 12px;gap:6px 8px}
  .bar-row.sub{padding:0 12px 6px}
  .logo{display:none}
  .seg{order:3;width:100%;overflow-x:auto}
  .seg button{padding:4px 10px;white-space:nowrap}
  .ctl{order:4;flex-basis:100%;justify-content:flex-start;flex-wrap:wrap}
  .ctl input{flex:1 1 100%}
  .updated{display:none}
  .wrap.open{grid-template-columns:minmax(0,1fr)}
  #panel{position:fixed;inset:0;z-index:20;height:100vh;border:0;padding:52px 20px 32px;display:none}
  body.panel-on #panel{display:block}
  .row{grid-template-columns:38px minmax(0,1fr) auto;padding:0 12px}
  .st,.sk{display:none}
  .top .ti::before{content:"★ ";color:var(--star)}
  .ti{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  .div{padding:7px 12px}
  #world{padding:12px}
}
"""

JS = r"""
(() => {
  const $ = id => document.getElementById(id);
  const list = $('list'), worldBox = $('world'), panel = $('panel'), pbody = $('pbody'), wrap = document.querySelector('.wrap');
  const rows = [...list.querySelectorAll('.row')];
  const cards = [...worldBox.querySelectorAll('.wcard')];
  const items = [...rows, ...cards];
  const q = $('q'), theme = $('theme'), sort = $('sort'), newBtn = $('newonly');
  let cat = '', scope = 'rel', newOnly = false, selected = null, visible = [];

  const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
  const el = (tag, attrs = {}, text) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  };

  // ---- 읽음 ----
  const read = new Set(load('mn_read', []));
  items.forEach(r => { if (read.has(r.dataset.id)) r.classList.add('read'); });
  const markRead = id => {
    read.add(id); save('mn_read', [...read].slice(-4000));
    items.forEach(r => { if (r.dataset.id === id) r.classList.add('read'); });
  };

  // ---- NEW: 이 페이지가 만들어지기 전에 본 적 없는 뉴스 ----
  let seen = load('mn_seen', null);
  if (!seen || seen.gen !== GENERATED) {
    const prev = seen ? seen.ids : [];
    seen = { gen: GENERATED, base: prev, ids: [...new Set([...prev, ...items.map(r => r.dataset.id)])].slice(-8000) };
    save('mn_seen', seen);
  }
  const base = new Set(seen.base);
  if (base.size) rows.forEach(r => { if (!base.has(r.dataset.id)) r.classList.add('new'); });

  // ---- 관심종목 ----
  let watch = load('mn_watch', []);
  const dl = $('stocknames');
  STOCK_NAMES.forEach(n => dl.append(el('option', { value: n })));
  function applyWatch() {
    const w = new Set(watch);
    let n = 0;
    rows.forEach(r => {
      const hit = r.dataset.stocks && r.dataset.stocks.split('|').some(s => w.has(s));
      r.classList.toggle('watch', !!hit); if (hit) n++;
    });
    $('watchcount').textContent = n;
    const box = $('watchlist'); box.replaceChildren();
    watch.forEach(name => {
      const chip = el('span', {}, name);
      const x = el('button', { type: 'button', title: '삭제' }, '✕');
      x.addEventListener('click', () => { watch = watch.filter(v => v !== name); save('mn_watch', watch); applyWatch(); render(); });
      chip.append(x); box.append(chip);
    });
  }
  $('watchbtn').addEventListener('click', () => { $('watchbox').hidden = !$('watchbox').hidden; if (!$('watchbox').hidden) $('watchin').focus(); setBarH(); });
  $('watchin').addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    const v = e.target.value.trim();
    if (v && !watch.includes(v)) { watch.push(v); save('mn_watch', watch); applyWatch(); render(); }
    e.target.value = '';
  });

  // ---- 시장 지표 ----
  const mk = $('mk'), market = $('market');
  const setMarket = open => { market.hidden = !open; mk.classList.toggle('open', open); save('mn_market', open); setBarH(); };
  mk.addEventListener('click', () => setMarket(market.hidden));

  // ---- 오른쪽 패널 ----
  function openPanel(item) {
    const id = item.dataset.id, d = DATA[id];
    if (!d) return;
    selected?.classList.remove('sel');
    selected = item; item.classList.add('sel'); markRead(id);

    const tags = el('div', { class: 'p-tags' });
    if (d.related) tags.append(el('span', { class: 'rel' }, '주식 관련'));
    [...new Set(d.tags)].forEach(t => tags.append(el('span', {}, t)));

    const meta = el('div', { class: 'p-meta' });
    meta.append('첫 보도 ', el('b', {}, d.first), ` · ${d.outlets.length}곳 보도: ${d.outlets.join(', ')}`);
    if (d.old) meta.append(el('span', { class: 'oldb' }, `${d.old}일 전 재료 — 이미 반영됐을 수 있음`));

    const parts = [tags, el('h2', {}, d.title), meta];
    parts.push(d.lead ? el('p', { class: 'p-lead' }, d.lead)
                      : el('p', { class: 'p-none' }, '이 기사는 수집 소스에서 본문 요약을 제공하지 않음. 아래 원문에서 확인.'));

    if (d.stocks.length || d.ai || d.sectors.length) {
      const box = el('div', { class: 'p-box' });
      if (d.sectors.length) {
        box.append(el('h3', {}, '영향 섹터'));
        const sc = el('div', { class: 'p-stocks p-sec' });
        d.sectors.forEach(x => sc.append(el('span', {}, x)));
        box.append(sc);
      }
      if (d.stocks.length) {
        box.append(el('h3', { style: d.sectors.length ? 'margin-top:12px' : '' }, '거론된 종목'));
        const s = el('div', { class: 'p-stocks' });
        d.stocks.forEach(([name, code]) => {
          const a = el('a', { href: `https://finance.naver.com/item/main.naver?code=${code}`, target: '_blank', rel: 'noopener', title: '네이버 증권에서 보기' }, name);
          a.append(el('small', {}, code)); s.append(a);
        });
        box.append(s);
      }
      if (d.ai && (d.ai.sector || d.related)) {
        const ai = el('div', { class: 'p-ai' });
        ai.append('AI 추정 · ', el('b', {}, d.ai.sector || '업종 미정'), ` · ${d.ai.dir}`);
        ai.append(el('small', {}, 'AI가 제목만 보고 분류한 참고용 결과. 매매 판단 근거 아님.'));
        box.append(ai);
      }
      parts.push(box);
    }

    parts.push(el('h3', {}, `같은 사건 보도 ${d.arts.length + d.more}건`));
    const arts = el('ul', { class: 'p-arts' });
    d.arts.forEach(([outlet, time, title, url]) => {
      const li = el('li');
      li.append(el('small', {}, `${outlet} · ${time}`));
      li.append(url ? el('a', { href: url, target: '_blank', rel: 'noopener' }, title) : el('span', {}, title));
      arts.append(li);
    });
    if (d.more) arts.append(el('li', {}, `외 ${d.more}건`));
    parts.push(arts);

    const src = el('div', { class: 'p-src' });
    src.append(el('h3', {}, `원문 · ${d.outlet}`));
    if (d.url) {
      if (d.via_google) src.append(el('p', { class: 'via' }, '구글 뉴스를 거쳐 언론사 페이지로 이동'));
      else src.append(el('a', { class: 'url', href: d.url, target: '_blank', rel: 'noopener' }, d.url));
      src.append(el('a', { class: 'open', href: d.url, target: '_blank', rel: 'noopener' }, '원문 열기 ↗'));
    }
    parts.push(src);

    pbody.replaceChildren(...parts);
    $('close').hidden = false; panel.scrollTop = 0;
    document.body.classList.add('panel-on');   // 모바일: 전체 화면으로 열림
  }
  function emptyPanel() {
    const box = el('div', { class: 'p-empty' });
    box.append(el('div', { class: 'p-empty-ic' }, '📰'),
               el('p', {}, '왼쪽에서 기사를 선택하면 여기에 내용이 표시됨'),
               el('small', {}, '↑ ↓ 키로 기사 이동 · Esc 선택 해제'));
    pbody.replaceChildren(box);
  }
  function closePanel() {
    selected?.classList.remove('sel'); selected = null;
    $('close').hidden = true;
    document.body.classList.remove('panel-on');
    emptyPanel();
  }
  document.querySelector('main').addEventListener('click', e => {
    const it = e.target.closest('.row,.wcard'); if (it) openPanel(it);
  });
  $('close').addEventListener('click', closePanel);
  document.addEventListener('keydown', e => {
    if (e.target.matches('input,select')) return;
    if (e.key === 'Escape') closePanel();
    const down = e.key === 'ArrowDown' || e.key === 'j', up = e.key === 'ArrowUp' || e.key === 'k';
    if ((down || up) && visible.length) {
      e.preventDefault();
      const i = visible.indexOf(selected);
      const next = visible[Math.max(0, Math.min(visible.length - 1, i + (down ? 1 : -1)))];
      openPanel(next); next.scrollIntoView({ block: 'nearest' });
    }
  });

  // ---- 필터·정렬·구분선 ----
  function match(r, words) {
    return (!cat || (r.dataset.cats || '').split(' ').includes(cat)) &&
      (!theme.value || (r.dataset.themes || '').split(' ').includes(theme.value)) &&
      words.every(w => r.dataset.search.includes(w));
  }
  function render() {
    const words = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const isWorld = scope === 'world', isFlow = scope === 'flow';
    wrap.classList.toggle('open', !isFlow); panel.hidden = isFlow;
    list.hidden = isWorld || isFlow; worldBox.hidden = !isWorld; $('flow').hidden = !isFlow;
    $('chiprow').hidden = isWorld || isFlow;
    theme.disabled = isWorld || isFlow; sort.disabled = isWorld || isFlow; q.disabled = isFlow;

    if (isFlow) {
      visible = [];
      $('shown').textContent = ''; $('empty').hidden = true; newBtn.hidden = true;
      setBarH(); return;
    }
    if (isWorld) {
      visible = cards.filter(c => words.every(w => c.dataset.search.includes(w)));
      cards.forEach(c => c.hidden = !visible.includes(c));
    } else {
      const key = sort.value;
      visible = rows.filter(r =>
        (scope === 'rel' ? r.classList.contains('rel') :
         scope === 'dom' ? !r.classList.contains('world') : r.classList.contains('watch')) &&
        (!newOnly || r.classList.contains('new')) && match(r, words));
      visible.sort((a, b) => b.dataset[key] - a.dataset[key]);
      const frag = document.createDocumentFragment();
      let bucket = null;
      for (const r of visible) {
        if (key === 'time' && r.dataset.bucket !== bucket) {
          bucket = r.dataset.bucket;
          frag.append(el('div', { class: 'div' }, r.dataset.label));
        }
        frag.append(r);
      }
      list.replaceChildren(frag);
    }
    $('shown').textContent = visible.length.toLocaleString() + '건';
    $('empty').hidden = visible.length > 0;
    if (scope === 'watch' && !watch.length) { $('empty').hidden = false; $('empty').textContent = '관심종목 설정에서 종목을 추가하면 여기에 모임'; }
    else $('empty').textContent = '조건에 맞는 뉴스 없음';

    const nNew = rows.filter(r => r.classList.contains('new') && (scope !== 'rel' || r.classList.contains('rel'))).length;
    newBtn.hidden = isWorld || (!nNew && !newOnly); $('newcount').textContent = nNew;
    setBarH();
  }

  $('scope').addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    scope = b.dataset.scope;
    $('scope').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
    render();
  });
  document.querySelectorAll('.chips .chip').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.chips .chip').forEach(x => x.classList.toggle('on', x === b));
    cat = b.dataset.cat; render();
  }));
  newBtn.addEventListener('click', () => { newOnly = !newOnly; newBtn.classList.toggle('on', newOnly); render(); });
  q.addEventListener('input', render);
  theme.addEventListener('change', render);
  sort.addEventListener('change', render);

  function setBarH() {
    document.documentElement.style.setProperty('--bar-h', document.querySelector('.bar').offsetHeight + 'px');
  }
  window.addEventListener('resize', setBarH);
  setMarket(load('mn_market', false));
  applyWatch();
  emptyPanel();
  render();
})();
"""
