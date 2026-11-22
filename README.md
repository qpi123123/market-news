# 증시 뉴스 수집기

매일 아침 06:30(KST) 구글 뉴스 검색과 언론사 RSS로 시장 관련 뉴스를 모아 웹페이지 1장으로 정리함.
기획 내용은 [SPEC.md](SPEC.md).

## 처음 설정 (한 번만)

### 1. GitHub 저장소 만들고 올리기
1. GitHub에서 **Public** 저장소 생성 (예: `market-news`)
2. 이 폴더 전체를 올림 (`.env`는 자동 제외됨)

### 2. Pages 켜기
저장소 → Settings → Pages → Source: **Deploy from a branch** → Branch: `main`, 폴더: `/docs` → Save

### 3. 첫 실행
저장소 → Actions → "아침 뉴스 수집" → **Run workflow**
1~2분 뒤 `https://<GitHub아이디>.github.io/<저장소이름>/` 에서 확인.

이후 매일 06:30쯤 자동 실행. API 키 없이 동작함 (구글 뉴스 검색 + 언론사 RSS).

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
python collector/main.py    # 결과: docs/index.html
```
Python 3.12, 외부 패키지 없음.

## 고치고 싶을 때
| 바꿀 것 | 파일 |
|---|---|
| 검색어, RSS 주소, 언론사 목록, 시세 항목, 수집 기간 | `collector/config.py` |
| 분야·테마 키워드, 지수 영향 단어 | `collector/keywords.py` |
| 중요도 점수, 같은 사건 묶는 기준 | `collector/process.py` |
| 페이지 디자인 | `collector/render.py` |
| 실행 시각 | `.github/workflows/collect.yml` 의 `cron` (UTC 기준, KST −9시간) |

## 알아둘 점
- **시세**: Yahoo Finance 비공식 API라 예고 없이 막힐 수 있음. 국고채·두바이유·투자자별 순매수는 무료 소스가 없어 "확인 못 함"으로 표시됨.
- **첫 보도 시각**: 수집된 기사 중 가장 이른 시각. 첫 실행 뒤부터 `data/history.json`에 쌓여서 "N일 전 재료" 판단이 정확해짐.
- **구글 뉴스 검색**: 공식 API가 아니라 형식이 바뀌거나 일시 차단(503)될 수 있음. 그래도 언론사 RSS는 계속 수집됨.
- **실패한 소스**: 페이지 왼쪽(모바일은 위쪽) 시장 숫자 아래 "수집 상태"에 표시됨. 매일경제 RSS는 봇 차단이 간헐적으로 걸림.
- **공개**: 저장소와 페이지 모두 공개됨. 네이버 키를 쓰는 경우에도 Secrets에만 있어서 노출되지 않음.
- **예약 실행 중단**: GitHub은 60일간 커밋이 없는 저장소의 예약 실행을 멈춤. 이 수집기는 매일 커밋하므로 해당 없음.
