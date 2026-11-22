"""결과 페이지(HTML 1장) 생성 — ver.2

화면 구성
- 상단 바(고정): 시장 지표 버튼 · 주식 관련/전체 · 분야 · 검색 · 테마 · 정렬 · NEW
- 시장 지표: 버튼을 누를 때만 펼침 (상태는 브라우저에 기억)
- 기사 목록: 한 줄에 한 건. 최신순이면 장 전·장중·장 마감 후 구분선
- 오른쪽 패널: 기사를 누르면 열림. 요약 → 같은 사건 다른 보도 → 맨 아래 원문 URL
- 읽음·NEW 표시: 서버 없이 브라우저 localStorage에만 저장
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from html import escape

import keywords as kw
from process import OLD_NEWS_DAYS, Story
from sources import Quote, SourceStatus

STAR_N = 15  # 주식 관련 중 중요도 상위 몇 건에 ★
WEEKDAYS = "월화수목금토일"


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
    return f'<i class="{d}">{arrow}{value}</i>'


# ---------------------------------------------------------------------------
# 시장 지표 (접힘)
# ---------------------------------------------------------------------------
def render_market(quotes: list[Quote], now: datetime) -> str:
    groups: dict[str, list[Quote]] = {}
    for q in quotes:
        groups.setdefault(q.group, []).append(q)
    cols = []
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
        cols.append(f'<div class="mg"><h3>{escape(group)}</h3>{"".join(rows)}</div>')
    return (f'<section id="market" hidden><div class="mgrid">{"".join(cols)}</div>'
            f'<p class="note">등락은 직전 거래일 종가 대비. 오른쪽은 기준일(오늘이면 KST 시각). '
            f'흐린 값은 4일 이상 갱신 안 됨. 국고채·두바이유는 무료 소스 없음.</p></section>')


def market_button_label(quotes: list[Quote]) -> str:
    """버튼에 코스피 한 줄 요약 + 큰 변동 개수."""
    kospi = next((q for q in quotes if q.name == "코스피" and q.price), None)
    head = f'코스피 <b>{fmt_number(kospi.price)}</b>{change_html(kospi)}' if kospi else "시장 지표"
    n_big = sum("big" in q.flags for q in quotes)
    badge = f'<span class="bigc">큰 변동 {n_big}</span>' if n_big else ""
    return f'<span class="mk-ic">▸</span> {head}{badge}'


# ---------------------------------------------------------------------------
# 기사 한 줄 + 패널 데이터
# ---------------------------------------------------------------------------
def render_row(s: Story, sid: str, now: datetime, starred: bool) -> str:
    first = s.first_published
    time_txt = f"{first:%H:%M}" if first.date() == now.date() or (now - first).total_seconds() < 86400 else md(first)
    bucket_key, bucket_label = session_of(first)
    labels = s.themes[:2] or [kw.CATEGORIES[c][0] for c in s.categories[:1] if c != "issue"]
    tags = "".join(f'<span class="tg{" th" if s.themes else ""}">{escape(t)}</span>' for t in labels)
    old = s.days_old >= OLD_NEWS_DAYS
    old_badge = f'<span class="oldb">{s.days_old}일 전</span>' if old else ""
    search = escape(" ".join([*(a.title for a in s.articles[:5]), s.summary, *s.outlets]).lower())
    classes = "row" + (" top" if starred else "") + (" old" if old else "") + (" rel" if s.stock_related else "")
    return (
        f'<div class="{classes}" data-id="{sid}" '
        f'data-cats="{" ".join(s.categories)}" data-themes="{escape(" ".join(s.themes))}" '
        f'data-score="{s.score:.1f}" data-time="{first.timestamp():.0f}" '
        f'data-bucket="{bucket_key}" data-label="{escape(bucket_label)}" data-search="{search}">'
        f'<span class="tm">{time_txt}</span><span class="st">{"★" if starred else ""}</span>'
        f'<span class="ti">{escape(s.lead.title)}</span>'
        f'<span class="meta">{old_badge}{tags}<span class="n">{len(s.outlets)}곳</span></span>'
        f'</div>'
    )


def panel_data(s: Story, now: datetime) -> dict:
    # 원문 링크: 구글 경유 주소보다 언론사 직접 주소를 우선 (가장 먼저 나온 직접 링크)
    source = next((a for a in s.articles if a.via != "구글"), s.lead)
    return {
        "title": s.lead.title,
        "first": f"{md(s.first_published)} {s.first_published:%H:%M}",
        "old": s.days_old if s.days_old >= OLD_NEWS_DAYS else 0,
        "outlets": s.outlets,
        "tags": [kw.CATEGORIES[c][0] for c in s.categories] + s.themes,
        "related": s.stock_related,
        "lead": s.lead_text or s.summary,
        "url": safe_url(source.url),
        "outlet": source.outlet,
        "arts": [[a.outlet, f"{md(a.published)} {a.published:%H:%M}", a.title, safe_url(a.url)]
                 for a in s.articles[:20]],
        "more": max(0, len(s.articles) - 20),
    }


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
        f'<p>주식 관련 = 시장 검색어로 찾은 기사, 테마·시장 키워드가 있는 기사, 언론사 5곳 이상이 다룬 이슈. '
        f'★ = 주식 관련 중 중요도 상위 {STAR_N}건 (보도 언론사 수 + 지수 영향 키워드 + 급등락 키워드 + 최신성). '
        f'시각 = 첫 보도 시각(KST).</p>'
        f'<table><thead><tr><th></th><th>소스</th><th>기사</th><th>비고</th></tr></thead><tbody>{rows}</tbody></table>'
        f'<p>자동 수집 결과. 투자 판단 전 원문 확인.</p></details>'
    )


# ---------------------------------------------------------------------------
# 페이지
# ---------------------------------------------------------------------------
def render_page(stories: list[Story], quotes: list[Quote], statuses: list[SourceStatus],
                n_articles: int, n_ai: int, now: datetime, window_hours: int) -> str:
    # stories는 중요도순. ★는 주식 관련 중 상위 STAR_N건
    starred = {id(s) for s in [s for s in stories if s.stock_related][:STAR_N]}
    ids = {id(s): story_id(s) for s in stories}
    by_time = sorted(stories, key=lambda s: s.first_published, reverse=True)
    rows = "".join(render_row(s, ids[id(s)], now, id(s) in starred) for s in by_time)
    data = json.dumps({ids[id(s)]: panel_data(s, now) for s in stories}, ensure_ascii=False).replace("</", "<\\/")

    used_themes = sorted({t for s in stories for t in s.themes})
    chips = '<button class="chip on" data-cat="">분야 전체</button>' + "".join(
        f'<button class="chip" data-cat="{key}">{escape(label)}</button>' for key, (label, _) in kw.CATEGORIES.items()
    )
    themes = '<option value="">테마</option>' + "".join(f'<option>{escape(t)}</option>' for t in used_themes)
    n_rel = sum(s.stock_related for s in stories)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>증시 뉴스 {md(now)} {now:%H:%M}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}</style>
</head>
<body>
<header class="bar">
  <button id="mk" class="mk" type="button" title="시장 지표 펼치기">{market_button_label(quotes)}</button>
  <div class="seg" id="scope">
    <button class="on" data-scope="rel" type="button">주식 관련 <span>{n_rel:,}</span></button>
    <button data-scope="all" type="button">전체 <span>{len(stories):,}</span></button>
  </div>
  <div class="chips">{chips}</div>
  <div class="ctl">
    <input id="q" type="search" placeholder="검색: 종목·키워드·언론사">
    <select id="theme">{themes}</select>
    <select id="sort"><option value="time">최신순</option><option value="score">중요도순</option></select>
    <button id="newonly" class="chip" type="button" hidden>NEW <span id="newcount"></span></button>
    <span id="shown" class="shown"></span>
    <span class="updated" title="수집 시각">{md(now)} {now:%H:%M}</span>
  </div>
</header>
{render_market(quotes, now)}
<div class="wrap">
  <main id="list">{rows}</main>
  <aside id="panel" hidden>
    <button id="close" class="close" type="button" title="닫기 (Esc)">✕</button>
    <div id="pbody"></div>
  </aside>
</div>
<p class="empty" id="empty" hidden>조건에 맞는 뉴스 없음</p>
{render_info(statuses, n_articles, n_ai, stories, now, window_hours)}
<script>const GENERATED = {json.dumps(now.isoformat())}; const DATA = {data};{JS}</script>
</body>
</html>"""


CSS = """
:root{
  --bg:#fff;--panel:#fafbfc;--text:#14161a;--sub:#4f5663;--faint:#8b919c;--line:#eceef1;--hover:#f4f6f9;--sel:#e9efff;
  --accent:#2f5bea;--up:#e0312b;--down:#1f6feb;--big:#fff2dc;--chip:#eef0f4;--star:#e8a400;--new:#e0312b;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1115;--panel:#14171d;--text:#e8eaee;--sub:#aab0bb;--faint:#6f7683;--line:#22262e;--hover:#171a21;--sel:#1b2440;
  --accent:#7c9cff;--up:#ff6b63;--down:#5b9dff;--big:#2e2412;--chip:#20242c;--star:#ffc233;--new:#ff6b63;
}}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--text);
  font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:14.5px;line-height:1.5;-webkit-font-smoothing:antialiased}
button,input,select{font:inherit;color:inherit}
.up{color:var(--up)}.down{color:var(--down)}

/* 상단 바 */
.bar{position:sticky;top:0;z-index:10;background:var(--bg);border-bottom:1px solid var(--line);
  display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;padding:7px 14px}
.mk{border:1px solid var(--line);background:var(--bg);border-radius:8px;padding:3px 10px;cursor:pointer;
  font-size:13px;white-space:nowrap;font-variant-numeric:tabular-nums;color:var(--sub)}
.mk b{color:var(--text);margin-left:3px}
.mk i{font-style:normal;margin-left:4px}
.mk-ic{display:inline-block;transition:transform .15s}
.mk.open .mk-ic{transform:rotate(90deg)}
.bigc{margin-left:8px;background:var(--big);color:var(--text);border-radius:4px;padding:0 5px;font-size:11.5px;font-weight:600}
.seg{display:flex;background:var(--chip);border-radius:8px;padding:2px}
.seg button{border:0;background:none;border-radius:6px;padding:2px 10px;font-size:13px;cursor:pointer;color:var(--sub)}
.seg button span{color:var(--faint);font-size:11.5px;margin-left:2px;font-variant-numeric:tabular-nums}
.seg button.on{background:var(--bg);color:var(--text);font-weight:600;box-shadow:0 1px 2px rgba(0,0,0,.08)}
.chips{display:flex;gap:4px;overflow-x:auto;scrollbar-width:none;flex:0 1 auto}
.chip{flex:0 0 auto;border:0;background:var(--chip);color:var(--sub);border-radius:999px;padding:3px 10px;font-size:12.5px;cursor:pointer}
.chip.on{background:var(--text);color:var(--bg)}
#newonly{color:var(--new);font-weight:700}
#newonly.on{background:var(--new);color:#fff}
.ctl{display:flex;gap:6px;align-items:center;flex:1 1 320px;justify-content:flex-end}
.ctl input,.ctl select{font-size:13px;padding:3px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg)}
.ctl input{flex:0 1 220px;min-width:0}
.shown,.updated{color:var(--faint);font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}

/* 시장 지표 (펼침) */
#market{border-bottom:1px solid var(--line);background:var(--panel);padding:10px 14px}
.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:4px 18px}
.mg h3{margin:4px 0 2px;font-size:11.5px;color:var(--faint);font-weight:600}
.mq{display:grid;grid-template-columns:1fr auto 64px 34px;gap:6px;align-items:baseline;font-size:13px;padding:1px 0;
  font-variant-numeric:tabular-nums}
.mq i{font-style:normal;text-align:right;font-size:12px}
.mq small{text-align:right;color:var(--faint);font-size:11px}
.mq.big{background:var(--big);border-radius:4px;margin:0 -4px;padding:1px 4px}
.mq.stale,.mq.missing{opacity:.45}
.mq.missing{grid-template-columns:1fr auto}
.mq.missing .mv{font-size:12px;color:var(--faint)}
.note{margin:6px 0 0;font-size:11.5px;color:var(--faint)}

/* 목록 + 패널 */
.wrap{display:grid;grid-template-columns:minmax(0,1fr)}
.wrap.open{grid-template-columns:minmax(0,1fr) min(46vw,680px)}
.div{position:sticky;top:var(--bar-h,44px);z-index:2;background:var(--bg);padding:9px 14px 3px;
  font-size:12px;font-weight:700;color:var(--accent);border-bottom:1px solid var(--line)}
.row{display:grid;grid-template-columns:40px 14px minmax(0,1fr) auto;align-items:center;column-gap:8px;
  padding:0 14px;min-height:33px;border-bottom:1px solid var(--line);cursor:pointer}
.row:hover{background:var(--hover)}
.row.sel{background:var(--sel)}
.tm{color:var(--faint);font-size:12.5px;font-variant-numeric:tabular-nums;line-height:1.1}
.st{color:var(--star);font-size:12px;text-align:center}
.ti{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;padding:6px 0}
.top .ti{font-weight:700}
.row.read .ti{color:var(--faint);font-weight:400}
.row.old .ti{color:var(--faint)}
.row.new .tm::after{content:"NEW";display:block;font-size:9.5px;font-weight:800;color:var(--new)}
.meta{display:flex;gap:5px;align-items:center;white-space:nowrap}
.n{color:var(--faint);font-size:12px;font-variant-numeric:tabular-nums;min-width:30px;text-align:right}
.tg{font-size:11.5px;color:var(--sub);background:var(--chip);padding:0 7px;border-radius:999px}
.tg.th{color:var(--accent)}
.oldb{font-size:11.5px;color:#b86e00;font-weight:600}
.wrap.open .tg{display:none}

#panel{position:sticky;top:var(--bar-h,44px);height:calc(100vh - var(--bar-h,44px));overflow-y:auto;
  border-left:1px solid var(--line);background:var(--panel);padding:22px 26px 28px}
.close{position:absolute;right:12px;top:10px;border:0;background:none;font-size:16px;color:var(--faint);cursor:pointer;padding:6px}
.p-tags{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.p-tags span{font-size:11.5px;background:var(--chip);color:var(--sub);padding:0 8px;border-radius:999px}
.p-tags .rel{background:var(--accent);color:#fff}
#panel h2{font-size:19px;line-height:1.45;margin:0 28px 6px 0;letter-spacing:-.01em}
.p-meta{font-size:12.5px;color:var(--faint);margin-bottom:16px}
.p-meta b{color:var(--sub)}
.p-meta .oldb{margin-left:6px}
.p-lead{font-size:15px;line-height:1.75;margin:0 0 20px;white-space:pre-line}
.p-none{font-size:13.5px;color:var(--faint);margin:0 0 20px}
#panel h3{font-size:12.5px;color:var(--faint);margin:0 0 6px;font-weight:600}
.p-arts{list-style:none;margin:0 0 22px;padding:0;border-left:2px solid var(--line)}
.p-arts li{padding:4px 0 4px 10px}
.p-arts a{color:var(--text);text-decoration:none}
.p-arts a:hover{text-decoration:underline}
.p-arts small{display:block;color:var(--faint);font-size:11.5px}
.p-src{border-top:1px solid var(--line);padding-top:14px}
.p-src a.url{display:block;word-break:break-all;color:var(--accent);font-size:13px;margin:4px 0 10px}
.p-src a.open{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;border-radius:8px;padding:7px 14px;font-size:13.5px;font-weight:600}

.empty{text-align:center;color:var(--faint);padding:24px}
.info{margin:14px;font-size:12.5px;color:var(--faint)}
.info summary{cursor:pointer}
.info table{border-collapse:collapse;margin:8px 0;width:100%;max-width:900px}
.info td,.info th{text-align:left;padding:3px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.info .num{text-align:right;font-variant-numeric:tabular-nums}
.info tr.fail td{color:var(--up)}

/* 모바일: 패널은 전체 화면, 제목 두 줄 */
@media (max-width:760px){
  .bar{padding:6px 10px}
  .ctl{flex-basis:100%;justify-content:flex-start}
  .ctl input{flex:1 1 auto}
  .updated{display:none}
  .wrap.open{grid-template-columns:minmax(0,1fr)}
  #panel{position:fixed;inset:0;z-index:20;height:100vh;border:0;padding:46px 18px 28px}
  .row{grid-template-columns:38px minmax(0,1fr) auto;padding:0 10px}
  .st,.tg{display:none}
  .top .ti::before{content:"★ ";color:var(--star)}
  .ti{white-space:normal;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
}
"""

JS = r"""
(() => {
  const $ = id => document.getElementById(id);
  const list = $('list'), panel = $('panel'), pbody = $('pbody'), wrap = document.querySelector('.wrap');
  const rows = [...list.querySelectorAll('.row')];
  const byId = Object.fromEntries(rows.map(r => [r.dataset.id, r]));
  const q = $('q'), theme = $('theme'), sort = $('sort'), newBtn = $('newonly');
  let cat = '', scope = 'rel', newOnly = false, selected = null, visible = [];

  // ---- 브라우저 저장소 ----
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };

  // 읽음
  const read = new Set(load('mn_read', []));
  rows.forEach(r => { if (read.has(r.dataset.id)) r.classList.add('read'); });
  const markRead = row => { row.classList.add('read'); read.add(row.dataset.id); save('mn_read', [...read].slice(-4000)); };

  // NEW: 이 페이지 이전에 본 적 없는 뉴스. 같은 페이지를 새로고침해도 유지
  let seen = load('mn_seen', null);
  if (!seen || seen.gen !== GENERATED) {
    const prev = seen ? seen.ids : [];
    seen = { gen: GENERATED, base: prev, ids: [...new Set([...prev, ...rows.map(r => r.dataset.id)])].slice(-6000) };
    save('mn_seen', seen);
  }
  const base = new Set(seen.base);
  if (base.size) rows.forEach(r => { if (!base.has(r.dataset.id)) r.classList.add('new'); });

  // ---- 시장 지표 토글 ----
  const mk = $('mk'), market = $('market');
  const setMarket = open => { market.hidden = !open; mk.classList.toggle('open', open); save('mn_market', open); setBarH(); };
  mk.addEventListener('click', () => setMarket(market.hidden));

  // ---- 오른쪽 패널 ----
  const el = (tag, attrs = {}, text) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text != null) e.textContent = text;
    return e;
  };
  function openPanel(row) {
    const d = DATA[row.dataset.id];
    if (!d) return;
    selected?.classList.remove('sel');
    selected = row; row.classList.add('sel'); markRead(row);

    const tags = el('div', { class: 'p-tags' });
    if (d.related) tags.append(el('span', { class: 'rel' }, '주식 관련'));
    d.tags.forEach(t => tags.append(el('span', {}, t)));

    const meta = el('div', { class: 'p-meta' });
    meta.append('첫 보도 ', el('b', {}, d.first), ` · 언론사 ${d.outlets.length}곳: ${d.outlets.join(', ')}`);
    if (d.old) meta.append(el('span', { class: 'oldb' }, `${d.old}일 전 재료 — 이미 반영됐을 수 있음`));

    const lead = d.lead ? el('p', { class: 'p-lead' }, d.lead)
                        : el('p', { class: 'p-none' }, '이 기사는 수집 소스에서 본문 요약을 제공하지 않음. 아래 원문에서 확인.');

    const arts = el('ul', { class: 'p-arts' });
    d.arts.forEach(([outlet, time, title, url]) => {
      const li = el('li');
      li.append(el('small', {}, `${outlet} · ${time}`));
      li.append(url ? el('a', { href: url, target: '_blank', rel: 'noopener' }, title) : el('span', {}, title));
      arts.append(li);
    });
    if (d.more) arts.append(el('li', {}, `외 ${d.more}건`));

    const src = el('div', { class: 'p-src' });
    src.append(el('h3', {}, `원문 · ${d.outlet}`));
    if (d.url) {
      src.append(el('a', { class: 'url', href: d.url, target: '_blank', rel: 'noopener' }, d.url));
      src.append(el('a', { class: 'open', href: d.url, target: '_blank', rel: 'noopener' }, '원문 열기 ↗'));
    }

    pbody.replaceChildren(tags, el('h2', {}, d.title), meta, lead,
                          el('h3', {}, `같은 사건 보도 ${d.arts.length + d.more}건`), arts, src);
    panel.hidden = false; wrap.classList.add('open'); panel.scrollTop = 0;
  }
  function closePanel() {
    panel.hidden = true; wrap.classList.remove('open');
    selected?.classList.remove('sel'); selected = null;
  }
  list.addEventListener('click', e => { const r = e.target.closest('.row'); if (r) openPanel(r); });
  $('close').addEventListener('click', closePanel);
  document.addEventListener('keydown', e => {
    if (e.target.matches('input,select')) return;
    if (e.key === 'Escape') closePanel();
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'j' || e.key === 'k') && visible.length) {
      e.preventDefault();
      const i = visible.indexOf(selected);
      const next = visible[Math.max(0, Math.min(visible.length - 1, i + (e.key === 'ArrowDown' || e.key === 'j' ? 1 : -1)))];
      openPanel(next); next.scrollIntoView({ block: 'nearest' });
    }
  });

  // ---- 필터·정렬·구분선 ----
  function render() {
    const words = q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const key = sort.value;
    visible = rows.filter(r =>
      (scope === 'all' || r.classList.contains('rel')) &&
      (!cat || r.dataset.cats.split(' ').includes(cat)) &&
      (!theme.value || r.dataset.themes.split(' ').includes(theme.value)) &&
      (!newOnly || r.classList.contains('new')) &&
      words.every(w => r.dataset.search.includes(w)));
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
    $('shown').textContent = visible.length.toLocaleString() + '건';
    $('empty').hidden = visible.length > 0;

    const nNew = rows.filter(r => r.classList.contains('new') && (scope === 'all' || r.classList.contains('rel'))).length;
    newBtn.hidden = !nNew && !newOnly; $('newcount').textContent = nNew;
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
  render();
})();
"""
