"""날짜별 보관과 테마 흐름 기록.

저장소에는 작은 JSON만 남김 (페이지 자체는 커밋하지 않음):
- data/themes.json            : 날짜별 테마 건수 {"2026-11-22": {"반도체": 12, ...}}
- data/archive/YYYY-MM-DD.json : 그날의 주식 관련 상위 60건 + 해외 상위 10건
같은 날 여러 번 실행되면 마지막 실행 결과로 덮어씀.
지난 날짜 페이지(docs/archive/*.html)는 실행할 때마다 이 JSON으로 다시 만듦.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path

from process import Story

KEEP_DAYS = 400
SNAPSHOT_TOP = 60
SNAPSHOT_WORLD = 10


def theme_counts(stories: list[Story]) -> dict[str, int]:
    """주식 관련 사건 중 테마별 건수."""
    counts: dict[str, int] = {}
    for s in stories:
        if s.stock_related:
            for t in s.themes:
                counts[t] = counts.get(t, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def update_theme_log(path: Path, now: datetime, stories: list[Story]) -> dict[str, dict[str, int]]:
    log = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    log[now.date().isoformat()] = theme_counts(stories)
    log = dict(sorted(log.items())[-KEEP_DAYS:])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=0), encoding="utf-8")
    return log


def _story_record(s: Story) -> dict:
    direct = next((a for a in s.articles if a.via != "구글"), s.lead)
    return {
        "title": s.lead.title, "url": direct.url, "outlet": direct.outlet,
        "first": s.first_published.strftime("%m/%d %H:%M"), "outlets": len(s.outlets),
        "themes": s.themes, "sectors": s.sectors, "stocks": [st[0] for st in s.stocks],
        "lead": (s.lead_text or s.summary)[:200], "world": s.world_cats[:1],
    }


def save_snapshot(folder: Path, now: datetime, stories: list[Story]) -> None:
    by_score = sorted(stories, key=lambda s: s.score, reverse=True)
    world = sorted([s for s in stories if s.is_world], key=lambda s: s.world_score, reverse=True)
    snap = {
        "date": now.date().isoformat(), "updated": now.strftime("%H:%M"),
        "themes": theme_counts(stories),
        "top": [_story_record(s) for s in by_score if s.stock_related][:SNAPSHOT_TOP],
        "world": [_story_record(s) for s in world][:SNAPSHOT_WORLD],
    }
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{snap['date']}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


ARCHIVE_CSS = """
*{box-sizing:border-box}body{margin:0;background:#fff;color:#191f28;font-family:"Pretendard Variable",Pretendard,-apple-system,
"Apple SD Gothic Neo","Malgun Gothic",sans-serif;font-size:14.5px;line-height:1.55;letter-spacing:-.01em}
.wrap{max-width:920px;margin:0 auto;padding:24px 20px 60px}
a{color:inherit}.back{color:#3182f6;text-decoration:none;font-size:13px}
h1{font-size:22px;margin:8px 0 4px}.sub{color:#8b95a1;font-size:13px;margin:0 0 20px}
h2{font-size:15px;margin:28px 0 8px}
.th{display:flex;flex-wrap:wrap;gap:6px}.th span{background:#e8f3ff;color:#3182f6;border-radius:6px;padding:2px 9px;font-size:12.5px;font-weight:600}
ol{margin:0;padding:0;list-style:none;border-top:1px solid #eceef1}
li{padding:9px 0;border-bottom:1px solid #eceef1}
li a{text-decoration:none;font-weight:600}li a:hover{color:#3182f6}
.m{color:#8b95a1;font-size:12px;margin-top:2px}.m b{color:#6a4bd8;font-weight:600}
.l{color:#4e5968;font-size:13px;margin-top:3px}
"""


def render_archive_page(snap: dict) -> str:
    def items(records: list[dict], show_lead: bool) -> str:
        out = []
        for r in records:
            tags = " · ".join(r["world"] + r["sectors"] + r["stocks"][:2])
            lead = f'<div class="l">{escape(r["lead"])}</div>' if show_lead and r["lead"] else ""
            out.append(f'<li><a href="{escape(r["url"])}" target="_blank" rel="noopener">{escape(r["title"])}</a>'
                       f'<div class="m">{escape(r["first"])} 첫 보도 · {r["outlets"]}곳 · {escape(r["outlet"])}'
                       f'{" · <b>" + escape(tags) + "</b>" if tags else ""}</div>{lead}</li>')
        return "".join(out)

    themes = "".join(f"<span>{escape(t)} {n}</span>" for t, n in snap["themes"].items())
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>증시 뉴스 기록 · {snap['date']}</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
<style>{ARCHIVE_CSS}</style></head><body><div class="wrap">
<a class="back" href="../index.html">← 오늘 페이지</a>
<h1>{snap['date']} 기록</h1><p class="sub">그날 마지막 수집({snap['updated']}) 기준 · 주식 관련 상위 {len(snap['top'])}건 · 해외 상위 {len(snap['world'])}건</p>
<h2>테마별 주식 관련 뉴스 건수</h2><div class="th">{themes or "기록 없음"}</div>
<h2>주식 관련 뉴스 (중요도순)</h2><ol>{items(snap['top'], False)}</ol>
<h2>해외 핵심</h2><ol>{items(snap['world'], True)}</ol>
</div></body></html>"""


def build_archive_pages(folder: Path, out_dir: Path) -> list[str]:
    """보관 JSON으로 지난 날짜 페이지를 만들고, 날짜 목록(최신순)을 반환."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = []
    for f in sorted(folder.glob("*.json"), reverse=True):
        snap = json.loads(f.read_text(encoding="utf-8"))
        (out_dir / f"{snap['date']}.html").write_text(render_archive_page(snap), encoding="utf-8")
        dates.append(snap["date"])
    return dates
