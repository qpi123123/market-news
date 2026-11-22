# 증시 뉴스 수집기

매일 06:30, 평일 08:00·12:00·15:40(KST)에 공신력 있는 언론사의 국내 주요 뉴스를 전부 모아 주식 관련 뉴스를 고르고, 해외 핵심 뉴스 20건과 함께 웹페이지 1장으로 정리함. AI 자동 작성 기사는 제외.
기획 내용은 [SPEC.md](SPEC.md).

## 처음 설정 (한 번만)

### 1. GitHub 저장소 만들고 올리기
1. GitHub에서 **Public** 저장소 생성 (예: `market-news`)
2. 이 폴더 전체를 올림 (`.env`는 자동 제외됨)

### 2. Pages 켜기
저장소 → Settings → Pages → Source: **GitHub Actions** 선택
(페이지는 저장소에 커밋하지 않고 실행 때마다 바로 게시함. 저장소에는 `data/`의 작은 기록만 쌓임.)

### 3. 첫 실행
저장소 → Actions → "아침 뉴스 수집" → **Run workflow**
1~2분 뒤 `https://<GitHub아이디>.github.io/<저장소이름>/` 에서 확인.

이후 자동 실행. API 키 없이 동작함.

### (권장) AI 판별 켜기 — Groq 무료
제목만 보내 '주식 관련 여부 · 영향 업종 · 방향 · 중요도'를 분류. 기사·요약은 쓰지 않음.
1. https://console.groq.com 가입 (카드 불필요) → **API Keys** → **Create API Key** → 키 복사
2. 저장소 → Settings → Secrets and variables → Actions → New repository secret → 이름 `GROQ_API_KEY`, 값에 키 붙여넣기
3. Actions → Run workflow 로 한 번 실행 → 페이지 맨 아래 '수집 정보'에서 "AI 판별 (Groq …)" 줄 확인

- 한 번 판별한 사건은 `data/ai_cache.json`에 저장해 다시 보내지 않음 → 하루 요청 수십 회 수준.
- 한 실행에 최대 300건까지 판별, 남은 건은 키워드 규칙으로 표시하고 다음 실행에서 이어서 판별.
- 키가 없거나 한도 초과·오류면 키워드 규칙으로 자동 전환. 요금은 청구되지 않음(무료 플랜은 결제수단 없음).

### (선택) 네이버 뉴스 검색 추가
네이버 API를 같이 쓰면 검색어당 최대 300건까지 받아 누락이 줄어듦. 현재 한시적 무료, 유료 전환 가능성 있음.
1. https://www.ncloud.com 가입 → 콘솔 → Services → Application Services → **NAVER API HUB**
2. Application 등록 → **검색** API 선택 → 인증 정보에서 Client ID / Secret 확인
3. 저장소 → Settings → Secrets and variables → Actions → `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 등록

유료로 바뀌면 Secrets 두 개를 지우면 됨. 키가 없으면 자동으로 건너뜀.
기존 개발자센터 키가 있으면 `collector/config.py`의 `NAVER_API = "legacy"` (2027-06-30까지).

## 로컬에서 실행
```
copy .env.example .env      # (선택) 네이버 키 입력
python collector/main.py    # 결과: docs/index.html, docs/archive/*.html
```
Python 3.12, 외부 패키지 없음.

## 고치고 싶을 때
| 바꿀 것 | 파일 |
|---|---|
| 검색어, RSS 주소, 언론사 목록, 시세 항목, 수집 기간 | `collector/config.py` |
| AI 작성 기사 판별 표현, 해외 소스, AI 판별 켜기/끄기·모델 | `collector/config.py` |
| AI 판별 기준(프롬프트), 요청 간격 | `collector/ai.py` |
| 종목 오탐 예외 | `collector/stocks.py` |
| 분야·테마 키워드, 지수 영향 단어 | `collector/keywords.py` |
| 중요도 점수, 같은 사건 묶는 기준, 주식 관련 판별 | `collector/process.py` |
| 페이지 디자인 | `collector/render.py` |
| 실행 시각 | `.github/workflows/collect.yml` 의 `cron` (UTC 기준, KST −9시간) |

## 알아둘 점
- **시세**: Yahoo Finance 비공식 API라 예고 없이 막힐 수 있음. 국고채·두바이유·투자자별 순매수는 무료 소스가 없어 "확인 못 함"으로 표시됨.
- **주식 관련 판별**: Groq 키가 있으면 AI 판별, 없거나 실패하면 키워드 규칙(시장 검색어·종목·테마·시장 키워드·언론사 5곳 이상). 놓친 기사는 '국내 전체'에서 확인 가능.
- **Groq 무료 정책**: 한도 수치는 공식 확인 못 함(외부 정리글 기준 하루 1,000회 이상). 무료 정책은 바뀔 수 있음.
- **테마 흐름**: `data/themes.json`에 날짜별 테마 건수가 쌓임. 8일째부터 이번 주와 지난주 비교가 나옴.
- **지난 날짜 페이지**: `data/archive/날짜.json`(하루 약 30KB)으로 실행 때마다 다시 만듦.
- **첫 보도 시각**: 수집된 기사 중 가장 이른 시각. 첫 실행 뒤부터 `data/history.json`에 쌓여서 "N일 전 재료" 판단이 정확해짐.
- **구글 뉴스 검색**: 공식 API가 아니라 형식이 바뀌거나 일시 차단(503)될 수 있음. 그래도 언론사 RSS는 계속 수집됨.
- **실패한 소스**: 페이지 맨 아래 "수집 정보"를 펼치면 표시됨. 매일경제 RSS는 봇 차단이 간헐적으로 걸림.
- **공개**: 저장소와 페이지 모두 공개됨. 네이버 키를 쓰는 경우에도 Secrets에만 있어서 노출되지 않음.
- **예약 실행 중단**: GitHub은 60일간 커밋이 없는 저장소의 예약 실행을 멈춤. 이 수집기는 매 실행마다 기록을 커밋하므로 해당 없음.
