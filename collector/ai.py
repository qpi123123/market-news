"""AI 주식 관련 판별 — Groq 무료 사용량 + 판별 결과 저장(캐시).

- 기사를 쓰거나 요약하지 않음. 제목만 보고 '주식 관련 여부 / 영향 업종 / 방향 / 중요도'만 분류.
- 한 번 판별한 사건은 data/ai_cache.json에 저장 → 다음 실행부터는 새 사건만 보냄 (무료 한도 절약).
- 키(GROQ_API_KEY)가 없거나 오류·한도 초과면 그 사건은 키워드 규칙 결과를 그대로 사용.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

import config
from process import Story
from sources import KST, SourceStatus, http_get

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
BATCH = 25            # 요청 1회에 보내는 제목 수
PAUSE = 20.0          # 요청 사이 간격(초) — 무료 '분당 토큰' 제한(약 6,000) 대비
MAX_REQUESTS = 12     # 한 번 실행에 보낼 최대 요청 수 (나머지는 다음 실행에서)
CACHE_DAYS = 14

SYSTEM = """너는 한국 주식시장 뉴스 분류기다. 각 뉴스 제목이 국내 상장 주식(개별 종목, 업종, 코스피·코스닥 지수)의 가격이나 투자심리에 영향을 줄 수 있는지 판단한다.
- 관련(rel=1): 기업 실적·수주·공시, 금리·환율·원자재, 정책·규제, 지정학, 해외 증시·빅테크, 그리고 사회·산업 이슈라도 특정 업종이나 기업 매출·비용·규제로 번질 수 있는 것(예: 대형 게임 흥행, AI 부정행위 논란에 따른 규제·보안 수요, 파업, 대형 사고, 소비 트렌드).
- 무관(rel=0): 스포츠 경기 결과, 연예 가십, 지역 행정, 개인 사건사고, 날씨 일반, 인사·부고.
- sector: 영향받을 국내 업종이나 테마를 짧게(예: 반도체, 게임, 보안, 항공, 건설). 없으면 빈 문자열.
- dir: 해당 업종 주가에 상승 압력이면 "+", 하락 압력이면 "-", 불분명하면 "0".
- imp: 세계·국내 정세에서 이 뉴스의 중요도 0~3 (3=전쟁 발발·대형 테러·주요국 정권 교체·글로벌 시장 급변, 0=가십).
- wcat: 해외 뉴스면 "경제", "분쟁·전쟁", "테러·안보", "정치", "외교" 중 하나, 국내 뉴스면 빈 문자열.
출력 형식: 뉴스 하나당 한 줄, 다른 말 없이 아래 6칸을 | 로 구분.
id|rel|sector|dir|imp|wcat
예) a1b2c3|1|게임|+|2|
예) d4e5f6|0||0|0|"""


def _parse(content: str, valid_ids: set[str]) -> dict[str, dict]:
    """'id|rel|sector|dir|imp|wcat' 줄들 → 결과. 형식이 깨진 줄은 버림."""
    out = {}
    for line in content.splitlines():
        cells = [c.strip() for c in line.strip().strip("`").split("|")]
        if len(cells) < 5 or cells[0] not in valid_ids:
            continue
        sid, rel, sector, direction, imp = cells[:5]
        wcat = cells[5] if len(cells) > 5 else ""
        try:
            rel_b = bool(int(rel))
            imp_i = max(0, min(3, int(imp or 0)))
        except ValueError:
            continue
        out[sid] = {"rel": rel_b, "sector": sector[:20], "dir": direction if direction in ("+", "-", "0") else "0",
                    "imp": imp_i, "wcat": wcat[:10]}
    return out


def _call(key: str, model: str, batch: list[tuple[str, str]]) -> dict[str, dict]:
    user = "\n".join(f"{sid}\t{title}" for sid, title in batch)
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"아래 뉴스(id<TAB>제목)를 분류:\n{user}"}],
        "temperature": 0,
        "max_tokens": 4000,
    }).encode()
    raw = http_get(ENDPOINT, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                   data=body, timeout=90, retries=2)
    try:
        content = json.loads(raw)["choices"][0]["message"]["content"] or ""
    except Exception:
        raise ValueError(f"응답 형식 이상: {raw[:150]!r}")
    return _parse(content, {sid for sid, _ in batch})


def _apply(s: Story, r: dict) -> None:
    s.ai = r
    s.stock_related = r["rel"]
    if s.is_world:
        s.world_score += 3.0 * r["imp"]
        if r["wcat"] and r["wcat"] not in s.world_cats:
            s.world_cats.insert(0, r["wcat"])


def classify(stories: list[Story], ids: dict[int, str], cache_path: Path) -> SourceStatus:
    """stories에 AI 판별 결과를 반영. ids: id(story) → 사건 id."""
    if not config.AI_ENABLED:
        return SourceStatus("AI 판별 (Groq)", True, error="꺼짐 — 키워드 규칙 사용")

    now = datetime.now(KST)
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    cache = {k: v for k, v in cache.items() if datetime.fromisoformat(v["at"]) > now - timedelta(days=CACHE_DAYS)}

    by_sid = {ids[id(s)]: s for s in stories}
    reused = 0
    for sid, s in by_sid.items():
        if sid in cache:
            _apply(s, cache[sid])
            reused += 1

    # 중요도 높은 새 사건부터 판별
    pending = [(sid, s.lead.title) for sid, s in sorted(by_sid.items(), key=lambda kv: -kv[1].score)
               if sid not in cache]
    key = os.environ.get("GROQ_API_KEY", "")
    models = list(config.AI_MODELS)
    done, error, bad_batches = 0, "", 0
    if pending and not key:
        error = "GROQ_API_KEY 없음 — 새 기사는 키워드 규칙 사용"
    elif pending:
        for n, i in enumerate(range(0, min(len(pending), BATCH * MAX_REQUESTS), BATCH)):
            if n:
                time.sleep(PAUSE)
            batch = pending[i:i + BATCH]
            results = None
            while results is None:
                try:
                    results = _call(key, models[0], batch)
                except urllib.error.HTTPError as e:
                    detail = e.read()[:150].decode("utf-8", "replace") if e.fp else ""
                    if e.code in (400, 404) and len(models) > 1:   # 모델 문제 → 다음 모델로
                        models.pop(0)
                        continue
                    error = f"HTTP {e.code}{' 한도 초과' if e.code == 429 else ''} {detail}".strip()
                    break
                except Exception:            # 응답 형식 문제 → 이 묶음만 건너뜀
                    results = {}
            if results is None:              # 한도 초과·인증 오류 → 중단
                break
            if not results:
                bad_batches += 1
            for sid, r in results.items():
                if sid in by_sid:
                    _apply(by_sid[sid], r)
                    cache[sid] = {**r, "at": now.isoformat()}
                    done += 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    left = len(pending) - done
    note = f"저장된 결과 {reused}건 재사용 · 새로 {done}건 판별"
    if left > 0:
        note += f" · 미판별 {left}건(키워드 규칙, 다음 실행에서 이어서)"
    if bad_batches:
        note += f" · 응답 형식 오류로 건너뛴 묶음 {bad_batches}개"
    if error:
        note += f" · {error}"
    ok = not error or done > 0 or reused > 0 or not key   # 키 미설정은 실패가 아님
    return SourceStatus(f"AI 판별 (Groq {models[0]})", ok, done + reused, note)
