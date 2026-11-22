"""AI 주식 관련 판별 — 현재 꺼짐 (config.AI_ENABLED).

GitHub Models가 2026-07-30 서비스 종료되어 이 엔드포인트는 더 이상 동작하지 않음.
다른 제공자(예: Gemini)로 바꿀 때 _call()만 교체하면 됨.

- 기사를 쓰거나 요약하지 않음. 제목을 보고 '주식 관련 여부 / 영향 업종 / 방향'만 분류.
- 토큰이 없거나(로컬 실행), 한도 초과·오류가 나면 키워드 규칙 결과를 그대로 사용.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error

import config
from process import Story
from sources import SourceStatus, http_get

ENDPOINT = "https://models.github.ai/inference/chat/completions"
BATCH = 40          # 요청 1회에 보내는 제목 수
PAUSE = 4.5         # 요청 사이 간격(초) — 분당 요청 제한 대비

SYSTEM = """너는 한국 주식시장 뉴스 분류기다. 각 뉴스 제목이 국내 상장 주식(개별 종목, 업종, 코스피·코스닥 지수)의 가격이나 투자심리에 영향을 줄 수 있는지 판단한다.
- 관련(rel=1): 기업 실적·수주·공시, 금리·환율·원자재, 정책·규제, 지정학, 해외 증시·빅테크, 그리고 사회·산업 이슈라도 특정 업종이나 기업 매출·비용·규제로 번질 수 있는 것(예: 대형 게임 흥행, AI 부정행위 논란에 따른 규제·보안 수요, 파업, 대형 사고, 소비 트렌드).
- 무관(rel=0): 스포츠 경기 결과, 연예 가십, 지역 행정, 개인 사건사고, 날씨 일반, 인사·부고.
- sector: 영향받을 국내 업종이나 테마를 짧게(예: 반도체, 게임, 보안, 항공, 건설). 없으면 빈 문자열.
- dir: 해당 업종 주가에 상승 압력이면 "+", 하락 압력이면 "-", 불분명하면 "0".
- imp: 세계·국내 정세에서 이 뉴스의 중요도 0~3 (3=전쟁 발발·대형 테러·주요국 정권 교체·글로벌 시장 급변, 0=가십).
- wcat: 해외 뉴스면 "경제", "분쟁·전쟁", "테러·안보", "정치", "외교" 중 하나, 국내 뉴스면 빈 문자열.
반드시 JSON만 출력: {"items":[{"id":"...","rel":1,"sector":"...","dir":"+","imp":2,"wcat":""}]}"""


def _call(token: str, model: str, batch: list[tuple[str, str]]) -> dict[str, dict]:
    user = "\n".join(f"{sid}\t{title}" for sid, title in batch)
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"아래 뉴스(id<TAB>제목)를 분류:\n{user}"}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode()
    raw = http_get(ENDPOINT, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                      "Accept": "application/vnd.github+json",
                                      "X-GitHub-Api-Version": "2022-11-28"}, data=body, timeout=60, retries=1)
    try:
        content = json.loads(raw)["choices"][0]["message"]["content"] or ""
    except Exception:
        raise ValueError(f"응답 형식 이상: {raw[:150]!r}")
    # 코드블록(```json ... ```) 등으로 감싸 오는 경우 대비: 가장 바깥 { ... }만 사용
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"JSON 없음: {content[:150]!r}")
    items = json.loads(content[start:end + 1]).get("items", [])
    out = {}
    for it in items:
        sid = str(it.get("id", ""))
        if sid:
            out[sid] = {"rel": bool(int(it.get("rel", 0))), "sector": str(it.get("sector", ""))[:20],
                        "dir": it.get("dir") if it.get("dir") in ("+", "-", "0") else "0",
                        "imp": max(0, min(3, int(it.get("imp", 0) or 0))),
                        "wcat": str(it.get("wcat", ""))[:10]}
    return out


def classify(stories: list[Story], ids: dict[int, str]) -> SourceStatus:
    """stories에 AI 판별 결과를 반영. ids: id(story) → 페이지에서 쓰는 사건 id."""
    name = f"AI 판별 (GitHub Models {config.AI_MODEL})"
    token = os.environ.get("GITHUB_TOKEN", "")
    if not config.AI_ENABLED:
        return SourceStatus("AI 판별", True, error="꺼짐 (GitHub Models 서비스 종료) — 키워드 규칙 사용")
    if not token:
        return SourceStatus(name, True, error="토큰 없음(로컬 실행) — 키워드 규칙 사용")

    by_sid = {ids[id(s)]: s for s in stories}
    pending = [(sid, s.lead.title) for sid, s in by_sid.items()]
    done = 0
    error = ""
    for i in range(0, len(pending), BATCH):
        batch = pending[i:i + BATCH]
        try:
            results = _call(token, config.AI_MODEL, batch)
        except urllib.error.HTTPError as e:
            detail = e.read()[:150].decode("utf-8", "replace") if e.fp else ""
            error = f"HTTP {e.code}" + (" 한도 초과" if e.code == 429 else "") + f" {detail} — {i}건 이후 키워드 규칙 사용"
            break
        except Exception as e:
            error = f"{str(e)[:200]} — {i}건 이후 키워드 규칙 사용"
            break
        for sid, r in results.items():
            s = by_sid.get(sid)
            if s:
                s.ai = r
                s.stock_related = r["rel"]
                if s.is_world:
                    s.world_score += 3.0 * r["imp"]
                    if r["wcat"] and r["wcat"] not in s.world_cats:
                        s.world_cats.insert(0, r["wcat"])
                done += 1
        time.sleep(PAUSE)

    return SourceStatus(name, done > 0 or not pending, done,
                        error=error or f"{len(pending)}건 중 {done}건 판별")
