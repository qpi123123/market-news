"""수집한 기사 정리: 시장 관련 필터 → 같은 사건 묶기 → 첫 보도 시각 → 태그 → 중요도."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import keywords as kw
from sources import KST, Article

SIMILARITY = 0.45        # 제목 유사도(Jaccard) 이 이상이면 같은 사건으로 묶음
HISTORY_DAYS = 14        # 첫 보도 기록 보관 기간
OLD_NEWS_DAYS = 2        # 이 이상 지난 재료는 '오래된 재료'로 표시


@dataclass
class Story:
    """같은 사건을 다룬 기사 묶음."""
    articles: list[Article]
    first_published: datetime
    latest_published: datetime
    categories: list[str] = field(default_factory=list)  # keywords.CATEGORIES 키
    themes: list[str] = field(default_factory=list)
    score: float = 0.0
    days_old: int = 0   # 첫 보도 후 지난 일수 (실행 기록 기준)

    @property
    def lead(self) -> Article:
        return self.articles[0]  # 가장 먼저 나온 기사

    @property
    def outlets(self) -> list[str]:
        return list(dict.fromkeys(a.outlet for a in self.articles))

    @property
    def summary(self) -> str:
        return next((a.summary for a in self.articles if a.summary), "")


# ---------------------------------------------------------------------------
# 제목 유사도
# ---------------------------------------------------------------------------
def bigrams(title: str) -> frozenset[str]:
    t = re.sub(r"\[[^\]]*\]|【[^】]*】", "", title)      # [특징주] 같은 말머리 제거
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t).lower()
    return frozenset(t[i:i + 2] for i in range(len(t) - 1))


class SimilarIndex:
    """bigram 역색인으로 비슷한 제목을 빠르게 찾음."""

    def __init__(self):
        self.grams: list[frozenset[str]] = []
        self.index: dict[str, list[int]] = defaultdict(list)

    def add(self, grams: frozenset[str]) -> int:
        idx = len(self.grams)
        self.grams.append(grams)
        for g in grams:
            self.index[g].append(idx)
        return idx

    def best_match(self, grams: frozenset[str]) -> int | None:
        if len(grams) < 4:
            return None
        shared: dict[int, int] = defaultdict(int)
        for g in grams:
            for idx in self.index.get(g, ()):
                shared[idx] += 1
        best, best_sim = None, SIMILARITY
        for idx, n in shared.items():
            sim = n / (len(grams) + len(self.grams[idx]) - n)
            if sim >= best_sim:
                best, best_sim = idx, sim
        return best


# ---------------------------------------------------------------------------
# 단계별 처리
# ---------------------------------------------------------------------------
def is_market_related(a: Article) -> bool:
    return bool(kw.find(f"{a.title} {a.summary}", kw.ALL_MARKET_WORDS))


def group_stories(articles: list[Article]) -> list[Story]:
    # 같은 URL(네이버·RSS 양쪽에서 받은 기사) 제거
    unique = {a.url: a for a in sorted(articles, key=lambda a: a.published, reverse=True)}
    ordered = sorted(unique.values(), key=lambda a: a.published)  # 오래된 것부터 → 묶음 대표 = 첫 보도

    index = SimilarIndex()
    groups: list[list[Article]] = []
    for a in ordered:
        grams = bigrams(a.title)
        match = index.best_match(grams)
        if match is None:
            index.add(grams)
            groups.append([a])
        else:
            groups[match].append(a)

    return [Story(articles=g, first_published=g[0].published, latest_published=g[-1].published) for g in groups]


def apply_history(stories: list[Story], path: Path, now: datetime) -> None:
    """이전 실행에서 본 사건이면 그때의 첫 보도 시각을 사용하고, 기록을 갱신."""
    records = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    cutoff = now - timedelta(days=HISTORY_DAYS)
    records = [r for r in records if datetime.fromisoformat(r["first"]) >= cutoff]

    index = SimilarIndex()
    for r in records:
        index.add(bigrams(r["title"]))

    for s in stories:
        match = index.best_match(bigrams(s.lead.title))
        if match is not None:
            earlier = datetime.fromisoformat(records[match]["first"])
            if earlier < s.first_published:
                s.first_published = earlier
        else:
            records.append({"title": s.lead.title, "first": s.first_published.isoformat()})
            index.add(bigrams(s.lead.title))
        s.days_old = (now.date() - s.first_published.date()).days

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=0), encoding="utf-8")


def tag_and_score(s: Story, now: datetime) -> None:
    text = " ".join(f"{a.title} {a.summary}" for a in s.articles[:5])
    s.categories = [key for key, (_, words) in kw.CATEGORIES.items() if kw.find(text, words)]
    s.themes = [name for name, words in kw.THEMES.items() if kw.find(text, words)]

    title_text = " ".join(a.title for a in s.articles[:5])
    hours_since = (now - s.latest_published).total_seconds() / 3600

    s.score = (
        3.0 * min(len(s.outlets), 8)                               # 여러 매체가 다룰수록 중요
        + 2.0 * len(kw.find(title_text, kw.INDEX_MOVERS))         # 지수 영향 단어
        + 2.0 * bool(kw.find(title_text, kw.SURGE_WORDS))         # 급등락
        + 0.5 * len(s.themes)
        + max(0.0, 6.0 - hours_since / 4)                         # 최신일수록 가산
        - (4.0 if s.days_old >= OLD_NEWS_DAYS else 0.0)           # 오래된 재료 감점
    )


def process(articles: list[Article], history_path: Path, now: datetime) -> list[Story]:
    related = [a for a in articles if is_market_related(a)]
    stories = group_stories(related)
    apply_history(stories, history_path, now)
    for s in stories:
        tag_and_score(s, now)
    return sorted(stories, key=lambda s: s.score, reverse=True)
