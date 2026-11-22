"""결과 페이지(HTML 1장) 생성. 외부 스크립트 없이 단독으로 열림."""

from __future__ import annotations

from datetime import datetime
from html import escape

import keywords as kw
from process import OLD_NEWS_DAYS, Story
from sources import Quote, SourceStatus

TOP_N = 15
WEEKDAYS = "월화수목금토일"


# ---------------------------------------------------------------------------
# 포맷 도우미
# ---------------------------------------------------------------------------
def fmt_time(dt: datetime, now: datetime) -> str:
    return dt.strftime("%H:%M") if dt.date() == now.date() else f"{dt.month}/{dt.day} {dt:%H:%M}"


def fmt_number(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}" if abs(value) >= 10000 else f"{value:,.2f}"
    return f"{value:,.2f}" if abs(value) >= 10 else f"{value:,.3f}"


def direction(value: float | None) -> str:
    if value is None or value == 0:
        return "flat"
    return "up" if value > 0 else "down"


def safe_url(url: str) -> str:
    return escape(url) if url.startswith(("http://", "https://")) else "#"


# ---------------------------------------------------------------------------
# 시장 숫자
# ---------------------------------------------------------------------------
def render_quotes(quotes: list[Quote], now: datetime) -> str:
    groups: dict[str, list[Quote]] = {}
    for q in quotes:
        groups.setdefault(q.group, []).append(q)

    blocks = []
    for group, items in groups.items():
        rows = []
        for q in items:
            if q.price is None:
                rows.append(f'<div class="q-row missing"><span class="q-name">{escape(q.name)}</span>'
                            f'<span class="q-note">{escape(q.note)}</span></div>')
                continue
            d = direction(q.change)
            arrow = {"up": "▲", "down": "▼", "flat": ""}[d]
            if q.pct is None:
                change = '<span class="q-chg">전일값 없음</span>'
            elif q.unit == "%":  # 금리는 %p 변화가 더 읽기 쉬움
                change = f'<span class="q-chg {d}">{arrow} {abs(q.change):.3f}%p</span>'
            else:
                change = f'<span class="q-chg {d}">{arrow} {abs(q.pct):.2f}%</span>'
            classes = "q-row" + (" big" if "big" in q.flags else "") + (" stale" if "stale" in q.flags else "")
            # 오늘 값은 시각, 지난 값은 날짜만 (시장마다 마감 시각이 달라 시각까지 쓰면 혼란)
            as_of = "" if not q.as_of else (
                f"{q.as_of:%H:%M}" if q.as_of.date() == now.date() else f"{q.as_of.month}/{q.as_of.day}")
            rows.append(
                f'<div class="{classes}">'
                f'<span class="q-name">{escape(q.name)}</span>'
                f'<span class="q-val">{fmt_number(q.price)}</span>'
                f'{change}'
                f'<span class="q-time">{as_of}</span>'
                f'</div>'
            )
        blocks.append(f'<div class="q-group"><h3>{escape(group)}</h3>{"".join(rows)}</div>')
    return "".join(blocks)


# ---------------------------------------------------------------------------
# 뉴스 카드
# ---------------------------------------------------------------------------
def render_tags(s: Story) -> str:
    tags = [f'<span class="tag cat">{escape(kw.CATEGORIES[c][0])}</span>' for c in s.categories]
    tags += [f'<span class="tag theme">{escape(t)}</span>' for t in s.themes]
    return f'<div class="tags">{"".join(tags)}</div>' if tags else ""


def render_story(s: Story, now: datetime, rank: int | None = None) -> str:
    lead = s.lead
    outlets = s.outlets
    who = escape(outlets[0]) + (f" 외 {len(outlets) - 1}곳" if len(outlets) > 1 else "")
    old = s.days_old >= OLD_NEWS_DAYS

    meta = [f'<span class="first">{fmt_time(s.first_published, now)} 첫 보도</span>', f"<span>{who}</span>"]
    if old:
        meta.append(f'<span class="old-badge">{s.days_old}일 전 재료</span>')
    if s.latest_published > s.first_published and s.latest_published.date() != s.first_published.date():
        meta.append(f"<span>최신 {fmt_time(s.latest_published, now)}</span>")

    related = ""
    if len(s.articles) > 1:
        items = "".join(
            f'<li><span class="r-meta">{escape(a.outlet)} · {fmt_time(a.published, now)}</span>'
            f'<a href="{safe_url(a.url)}" target="_blank" rel="noopener">{escape(a.title)}</a></li>'
            for a in s.articles[1:12]
        )
        more = f"<li class='r-more'>외 {len(s.articles) - 12}건</li>" if len(s.articles) > 12 else ""
        related = f'<details class="related"><summary>관련 기사 {len(s.articles) - 1}건</summary><ul>{items}{more}</ul></details>'

    rank_html = f'<span class="rank">{rank}</span>' if rank else ""
    search_text = escape(" ".join([lead.title, s.summary, *outlets]).lower())
    return (
        f'<article class="story{" old" if old else ""}" '
        f'data-cats="{" ".join(s.categories)}" data-themes="{escape(" ".join(s.themes))}" '
        f'data-score="{s.score:.1f}" data-time="{s.latest_published.timestamp():.0f}" data-search="{search_text}">'
        f'{rank_html}<div class="body">'
        f'<h4><a href="{safe_url(lead.url)}" target="_blank" rel="noopener">{escape(lead.title)}</a></h4>'
        f'<div class="meta">{" · ".join(meta)}</div>'
        f'{f"<p class=summary>{escape(s.summary)}</p>" if s.summary else ""}'
        f'{render_tags(s)}{related}'
        f'</div></article>'
    )


# ---------------------------------------------------------------------------
# 수집 상태
# ---------------------------------------------------------------------------
def render_status(statuses: list[SourceStatus]) -> str:
    rows = "".join(
        f'<tr class="{"ok" if st.ok else "fail"}"><td>{"✓" if st.ok else "✕"}</td>'
        f'<td>{escape(st.name)}</td><td class="num">{st.count:,}</td><td>{escape(st.error)}</td></tr>'
        for st in statuses
    )
    failed = sum(not st.ok for st in statuses)
    label = f"수집 상태 — 소스 {len(statuses)}개 중 {failed}개 실패" if failed else f"수집 상태 — 소스 {len(statuses)}개 모두 정상"
    return (f'<details class="status"><summary>{label}</summary>'
            f'<table><thead><tr><th></th><th>소스</th><th>기사</th><th>비고</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></details>')


# ---------------------------------------------------------------------------
# 페이지
# ---------------------------------------------------------------------------
def render_page(stories: list[Story], quotes: list[Quote], statuses: list[SourceStatus],
                n_articles: int, now: datetime, window_hours: int) -> str:
    outlets = {o for s in stories for o in s.outlets}
    used_themes = sorted({t for s in stories for t in s.themes})
    title_date = f"{now.month}월 {now.day}일({WEEKDAYS[now.weekday()]})"

    cat_chips = '<button class="chip active" data-cat="">전체</button>' + "".join(
        f'<button class="chip" data-cat="{key}">{escape(label)}</button>' for key, (label, _) in kw.CATEGORIES.items()
    )
    theme_options = '<option value="">테마 전체</option>' + "".join(
        f'<option value="{escape(t)}">{escape(t)}</option>' for t in used_themes
    )
    top = "".join(render_story(s, now, i + 1) for i, s in enumerate(stories[:TOP_N]))
    everything = "".join(render_story(s, now) for s in stories)
    big_quotes = [q for q in quotes if "big" in q.flags]
    big_note = ("큰 변동: " + ", ".join(f"{q.name} {q.pct:+.2f}%" for q in big_quotes)) if big_quotes else ""

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>증시 뉴스 · {title_date}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <h1>증시 뉴스 <span class="date">{title_date} {now:%H:%M} 기준</span></h1>
  <p class="sub">지난 {window_hours}시간 · 기사 {n_articles:,}건 → 사건 {len(stories):,}개 · 언론사 {len(outlets)}곳</p>
</header>

<div class="layout">
<aside class="side">
  <section>
    <h2>시장 숫자</h2>
    {f'<p class="alert">{escape(big_note)}</p>' if big_note else ''}
    <div class="quotes">{render_quotes(quotes, now)}</div>
    <p class="hint">오른쪽은 마지막 거래일(오늘이면 KST 시각). 등락은 직전 거래일 종가 대비. 흐린 값은 4일 이상 갱신 안 됨.</p>
  </section>
  {render_status(statuses)}
</aside>

<main>
<section>
  <h2>주요 뉴스 <span class="count">TOP {min(TOP_N, len(stories))}</span></h2>
  <p class="hint">점수 = 보도한 언론사 수 + 지수 영향 키워드 + 급등락 키워드 + 최신성. 판단은 직접.</p>
  <div class="list">{top}</div>
</section>

<section id="all">
  <h2>전체 뉴스 <span class="count" id="shown">{len(stories):,}</span></h2>
  <div class="filters">
    <div class="chips">{cat_chips}</div>
    <div class="controls">
      <input id="q" type="search" placeholder="검색 (종목, 키워드, 언론사)">
      <select id="theme">{theme_options}</select>
      <select id="sort"><option value="score">중요도순</option><option value="time">최신순</option></select>
    </div>
  </div>
  <div class="list" id="all-list">{everything}</div>
  <p class="empty" id="empty" hidden>조건에 맞는 뉴스 없음</p>
</section>
</main>
</div>
<footer>자동 수집 결과. 투자 판단의 근거로 쓰기 전에 원문 확인.</footer>
<script>{JS}</script>
</body>
</html>"""


CSS = """
:root{
  --bg:#f6f7f9;--card:#fff;--text:#16181d;--sub:#5b6270;--faint:#8b919c;--line:#e6e8ec;
  --accent:#2f5bea;--up:#e0312b;--down:#1f6feb;--big:#fff4e5;--chip:#eef0f4;--tag-theme:#eef3ff;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1115;--card:#171a21;--text:#e8eaee;--sub:#a3a9b5;--faint:#737a87;--line:#272b34;
  --accent:#7c9cff;--up:#ff6b63;--down:#5b9dff;--big:#2b2214;--chip:#232731;--tag-theme:#1d2540;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:"Pretendard Variable",Pretendard,-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:15px;line-height:1.6;word-break:keep-all;-webkit-font-smoothing:antialiased}
header.top,footer,.layout{padding:0 16px}
.layout{display:block}
header.top{padding-top:28px}
h1{font-size:24px;margin:0;letter-spacing:-.02em}
h1 .date{display:block;font-size:15px;font-weight:500;color:var(--sub);margin-top:2px}
.sub{color:var(--faint);margin:4px 0 0;font-size:13px}
section{margin-top:28px}
h2{font-size:18px;margin:0 0 10px;letter-spacing:-.01em}
h2 .count{font-size:13px;font-weight:600;color:var(--faint);margin-left:4px}
.hint{color:var(--faint);font-size:12px;margin:6px 0 10px}
.alert{background:var(--big);border-radius:8px;padding:8px 12px;font-size:14px;font-weight:600;margin:0 0 10px}

/* 시장 숫자 */
.quotes{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr));gap:10px}
.q-group{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px}
.q-group h3{font-size:12px;color:var(--faint);margin:0 0 4px;font-weight:600}
.q-row{display:grid;grid-template-columns:1fr auto 84px 44px;gap:8px;align-items:baseline;padding:4px 0;
  font-variant-numeric:tabular-nums}
.q-row+.q-row{border-top:1px dashed var(--line)}
.q-name{font-weight:500}
.q-val{text-align:right;font-weight:600}
.q-chg{text-align:right;font-size:13px;color:var(--faint)}
.q-time{text-align:right;font-size:11px;color:var(--faint)}
.q-row.big{background:var(--big);margin:0 -8px;padding:4px 8px;border-radius:6px}
.q-row.stale{opacity:.5}
.q-row.missing{grid-template-columns:1fr auto}
.q-note{font-size:12px;color:var(--faint);text-align:right}
.up{color:var(--up)!important}.down{color:var(--down)!important}

/* 뉴스 카드 */
.list{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,360px),1fr));gap:10px;align-items:start}
.story{display:flex;gap:12px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.story.old{opacity:.62}
.rank{flex:0 0 22px;font-weight:700;color:var(--accent);font-size:16px;line-height:1.5;text-align:center}
.body{min-width:0;flex:1}
.story h4{margin:0;font-size:16px;line-height:1.45;font-weight:650;letter-spacing:-.01em}
.story h4 a{color:inherit;text-decoration:none}
.story h4 a:hover{text-decoration:underline}
.meta{font-size:12.5px;color:var(--faint);margin-top:3px}
.meta .first{color:var(--sub);font-weight:600}
.old-badge{color:#b86e00;font-weight:600}
.summary{margin:6px 0 0;color:var(--sub);font-size:14px;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.tag{font-size:11.5px;padding:1px 8px;border-radius:999px;background:var(--chip);color:var(--sub)}
.tag.theme{background:var(--tag-theme);color:var(--accent)}
.related{margin-top:8px;font-size:13px}
.related summary{cursor:pointer;color:var(--accent);font-weight:500;list-style:none}
.related summary::-webkit-details-marker{display:none}
.related summary::before{content:"▸ "}.related[open] summary::before{content:"▾ "}
.related ul{margin:6px 0 0;padding:0;list-style:none;border-left:2px solid var(--line)}
.related li{padding:3px 0 3px 10px}
.related a{color:var(--text);text-decoration:none}
.related a:hover{text-decoration:underline}
.r-meta{display:block;font-size:11.5px;color:var(--faint)}
.r-more{color:var(--faint)}

/* 필터 */
.filters{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0 10px;margin-bottom:4px}
.chips{display:flex;gap:6px;overflow-x:auto;padding-bottom:6px;scrollbar-width:none}
.chip{flex:0 0 auto;border:0;background:var(--chip);color:var(--sub);border-radius:999px;padding:6px 12px;
  font:inherit;font-size:13px;font-weight:500;cursor:pointer}
.chip.active{background:var(--text);color:var(--bg)}
.controls{display:flex;gap:6px}
.controls input,.controls select{font:inherit;font-size:14px;padding:7px 10px;border:1px solid var(--line);
  border-radius:8px;background:var(--card);color:var(--text)}
.controls input{flex:1;min-width:0}
.empty{text-align:center;color:var(--faint);padding:24px}

/* 수집 상태 */
.status{margin:24px 0 0;font-size:13px;color:var(--sub)}
.status summary{cursor:pointer}
.status table{width:100%;border-collapse:collapse;margin-top:8px}
.status td,.status th{text-align:left;padding:5px 6px;border-bottom:1px solid var(--line);vertical-align:top}
.status .num{text-align:right;font-variant-numeric:tabular-nums}
.status tr.fail td{color:var(--up)}
footer{color:var(--faint);font-size:12px;padding-top:24px;padding-bottom:40px}

/* PC: 왼쪽 시장 숫자 고정 + 오른쪽 뉴스 여러 열 */
@media (min-width:1100px){
  header.top,footer,.layout{padding-left:28px;padding-right:28px}
  .layout{display:grid;grid-template-columns:360px minmax(0,1fr);gap:28px;align-items:start}
  .side{position:sticky;top:0;max-height:100vh;overflow-y:auto;padding-bottom:24px;scrollbar-width:thin}
  .side .quotes{grid-template-columns:1fr}
  .filters{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
  .filters .chips{padding-bottom:0;flex:1 1 auto}
  .filters .controls{flex:0 1 520px}
}
@media (max-width:480px){
  .quotes{grid-template-columns:1fr}
  .q-row{grid-template-columns:1fr auto 76px 40px}
  .story{padding:12px 14px}
  .controls{flex-wrap:wrap}.controls input{flex-basis:100%}
}
"""

JS = """
(() => {
  const list = document.getElementById('all-list');
  const cards = [...list.children];
  const q = document.getElementById('q'), theme = document.getElementById('theme'), sort = document.getElementById('sort');
  let cat = '';

  function apply() {
    const words = q.value.trim().toLowerCase().split(/\\s+/).filter(Boolean);
    let shown = 0;
    for (const c of cards) {
      const ok = (!cat || c.dataset.cats.split(' ').includes(cat))
        && (!theme.value || c.dataset.themes.split(' ').includes(theme.value))
        && words.every(w => c.dataset.search.includes(w));
      c.hidden = !ok;
      if (ok) shown++;
    }
    document.getElementById('shown').textContent = shown.toLocaleString();
    document.getElementById('empty').hidden = shown > 0;
  }

  function reorder() {
    const key = sort.value;
    cards.sort((a, b) => Number(b.dataset[key]) - Number(a.dataset[key]));
    list.append(...cards);
  }

  document.querySelectorAll('.chip').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach(b => b.classList.toggle('active', b === btn));
    cat = btn.dataset.cat;
    apply();
  }));
  q.addEventListener('input', apply);
  theme.addEventListener('change', apply);
  sort.addEventListener('change', reorder);
})();
"""
