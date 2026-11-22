"""수집한 기사 정리: 시장 관련 필터 → 같은 사건 묶기 → 첫 보도 시각 → 태그 → 중요도."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import config
import keywords as kw
from sources import KST, Article

# 같은 사건 판정: 제목 글자쌍(bigram)이 MIN_SHARED개 이상 겹치고, 짧은 쪽 제목의 MIN_OVERLAP 이상이 겹치면 같은 사건.
# (2026-11-22 실측: 같은 사건은 7개 이상·30~64% 겹침, 다른 사건은 3개 이하)
MIN_SHARED = 6
MIN_OVERLAP = 0.35
HISTORY_DAYS = 14        # 첫 보도 기록 보관 기간
OLD_NEWS_DAYS = 2        # 이 이상 지난 재료는 '오래된 재료'로 표시
BIG_ISSUE_OUTLETS = 5    # 시장 키워드가 없어도 이만큼 많은 언론사가 다루면 주식 관련으로 봄


@dataclass
class Story:
    """같은 사건을 다룬 기사 묶음."""
    articles: list[Article]
    first_published: datetime
    latest_published: datetime
    categories: list[str] = field(default_factory=list)  # keywords.CATEGORIES 키
    themes: list[str] = field(default_factory=list)
    score: float = 0.0
    stock_related: bool = False  # 주식 관련 판별 결과
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

    @property
    def lead_text(self) -> str:
        """가장 긴 리드 (구글 기사는 리드가 없어서 같은 사건의 RSS 기사에서 가져옴)."""
        return max((a.lead for a in self.articles), key=len, default="")


# ---------------------------------------------------------------------------
# 제목 유사도
# ---------------------------------------------------------------------------
EN_STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "after", "over", "into", "says", "will", "its", "are"}


def bigrams(title: str) -> frozenset[str]:
    """제목 비교 단위. 한글 제목은 글자쌍, 영어 제목은 단어 (영어 글자쌍은 흔한 조합이 많아 오판이 잦음)."""
    t = re.sub(r"\[[^\]]*\]|【[^】]*】", "", title)      # [특징주] 같은 말머리 제거
    if len(re.findall(r"[가-힣]", t)) < 3:
        words = re.findall(r"[a-z0-9]{3,}", t.lower())
        return frozenset(w for w in words if w not in EN_STOPWORDS)
    t = re.sub(r"[^0-9A-Za-z가-힣]", "", t).lower()
    return frozenset(t[i:i + 2] for i in range(len(t) - 1))


class SimilarIndex:
    """bigram 역색인으로 비슷한 제목을 빠르게 찾음. 각 제목은 그룹 번호(key)에 속함."""

    def __init__(self):
        self.grams: list[frozenset[str]] = []
        self.keys: list[int] = []
        self.index: dict[str, list[int]] = defaultdict(list)

    def add(self, grams: frozenset[str], key: int | None = None) -> int:
        idx = len(self.grams)
        self.grams.append(grams)
        self.keys.append(idx if key is None else key)
        for g in grams:
            self.index[g].append(idx)
        return self.keys[idx]

    def best_match(self, grams: frozenset[str]) -> int | None:
        """가장 비슷한 제목이 속한 그룹 번호. 없으면 None."""
        if len(grams) < MIN_SHARED:
            return None
        shared: dict[int, int] = defaultdict(int)
        for g in grams:
            for idx in self.index.get(g, ()):
                shared[idx] += 1
        best, best_overlap = None, MIN_OVERLAP
        for idx, n in shared.items():
            overlap = n / min(len(grams), len(self.grams[idx]))
            if n >= MIN_SHARED and overlap >= best_overlap:
                best, best_overlap = self.keys[idx], overlap
        return best


# ---------------------------------------------------------------------------
# 단계별 처리
# ---------------------------------------------------------------------------
def is_ai_written(a: Article) -> bool:
    """AI·로봇 자동 작성 기사 여부 (config.AI_ARTICLE_MARKERS)."""
    text = f"{a.title} {a.summary} {a.author}"
    return any(m in text for m in config.AI_ARTICLE_MARKERS)


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
            match = len(groups)
            groups.append([])
        groups[match].append(a)
        index.add(grams, key=match)  # 묶음 안 모든 제목과 비교되도록 전부 등록

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
    s.categories = [key for key, (_, words) in kw.CATEGORIES.items() if kw.find(text, words)] or ["issue"]
    s.themes = [name for name, words in kw.THEMES.items() if kw.find(text, words)]

    # 주식 관련 판별: 시장 검색어로 찾음 / 테마 키워드 / 시장 분야 키워드 / 언론사 다수가 다룬 큰 이슈
    s.stock_related = (
        any(a.targeted for a in s.articles)
        or bool(s.themes)
        or any(c != "issue" for c in s.categories)
        or len(s.outlets) >= BIG_ISSUE_OUTLETS
    )

    title_text = " ".join(a.title for a in s.articles[:5])
    hours_since = (now - s.latest_published).total_seconds() / 3600

    s.score = (
        3.0 * min(len(s.outlets), 8)                               # 여러 매체가 다룰수록 중요
        + 2.0 * len(kw.find(title_text, kw.INDEX_MOVERS))         # 지수 영향 단어
        + 2.0 * bool(kw.find(title_text, kw.SURGE_WORDS))         # 급등락
        + 0.5 * len(s.themes)
        + 2.0 * any(a.targeted for a in s.articles)              # 시장 검색어로 찾은 사건
        + max(0.0, 6.0 - hours_since / 4)                         # 최신일수록 가산
        - (4.0 if s.days_old >= OLD_NEWS_DAYS else 0.0)           # 오래된 재료 감점
    )


def process(articles: list[Article], history_path: Path, now: datetime) -> tuple[list[Story], int]:
    """반환: (중요도순 사건 목록, 제외한 AI 작성 기사 수)"""
    # 국내 주요 뉴스는 분야와 상관없이 전부 남김 (AI 작성 기사만 제외).
    # 시장 영향은 거르지 않고 중요도 점수·★로 표시.
    ai_written = [a for a in articles if is_ai_written(a)]
    stories = group_stories([a for a in articles if not is_ai_written(a)])
    apply_history(stories, history_path, now)
    for s in stories:
        tag_and_score(s, now)
    return sorted(stories, key=lambda s: s.score, reverse=True), len(ai_written)
