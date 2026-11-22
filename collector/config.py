"""수집기 설정. 소스·검색어·키워드는 여기만 고치면 됨."""

# 수집 기간: 지금부터 몇 시간 전 기사까지 받을지
WINDOW_HOURS = 24

# ---------------------------------------------------------------------------
# 1) RSS 소스 (2026-11-22 응답 확인)
#    실패한 소스는 결과 페이지 하단 '수집 상태'에 표시됨
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    # (출처명, 섹션, URL)
    ("연합뉴스", "마켓+", "https://www.yna.co.kr/rss/market.xml"),
    ("연합뉴스", "경제", "https://www.yna.co.kr/rss/economy.xml"),
    ("연합인포맥스", "전체", "https://news.einfomax.co.kr/rss/allArticle.xml"),
    ("한국경제", "증권", "https://www.hankyung.com/feed/finance"),
    ("한국경제", "경제", "https://www.hankyung.com/feed/economy"),
    ("매일경제", "증권", "https://www.mk.co.kr/rss/50200011/"),  # 봇 차단 간헐적
    ("매일경제", "경제", "https://www.mk.co.kr/rss/30100041/"),
    ("뉴시스", "경제", "https://www.newsis.com/RSS/economy.xml"),
    ("파이낸셜뉴스", "증권", "https://www.fnnews.com/rss/r20/fn_realnews_stock.xml"),
    ("아시아경제", "증권", "https://www.asiae.co.kr/rss/stock.htm"),
    ("헤럴드경제", "경제", "https://biz.heraldcorp.com/rss/google/economy"),
    ("머니투데이", "전체", "https://rss.mt.co.kr/mt_news.xml"),  # EUC-KR (자동 처리)
    ("CNBC", "Top News", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
    ("CNBC", "Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
    ("CNBC", "Finance", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10000664"),
]

# ---------------------------------------------------------------------------
# 2) 검색어 — 구글 뉴스 검색(주력, 무료)과 네이버 API(선택)가 같이 사용
# ---------------------------------------------------------------------------
# 구글 뉴스 RSS 검색: 키 불필요. 검색어당 최대 약 100건. 비공식 사용이라 형식이 바뀔 수 있음.
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"

# 네이버 뉴스 검색 API (선택): NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 있을 때만 사용.
#   신규 키는 네이버클라우드 'NAVER API HUB'에서 발급 (현재 한시적 무료).
NAVER_API = "hub"     # "hub": API 허브 키 / "legacy": 기존 개발자센터 키 (2027-06-30까지)
NAVER_MAX_PAGES = 3   # 검색어 1개당 최대 호출 수 (1회 = 100건)
NAVER_ENDPOINTS = {
    "hub": ("https://naverapihub.apigw.ntruss.com/search/v1/news",
            "X-NCP-APIGW-API-KEY-ID", "X-NCP-APIGW-API-KEY"),
    "legacy": ("https://openapi.naver.com/v1/search/news.json",
               "X-Naver-Client-Id", "X-Naver-Client-Secret"),
}

SEARCH_QUERIES = {
    "시황": ["코스피 마감", "코스닥 마감", "코스피 외국인 순매도", "코스피 외국인 순매수", "증시 전망",
            "프로그램 매매", "공매도", "사이드카", "서킷브레이커", "신용융자"],
    "특징주": ["특징주", "상한가", "급등주", "하한가", "52주 신고가", "급락 종목", "테마주"],
    "미국장": ["뉴욕증시", "나스닥 마감", "엔비디아 주가", "필라델피아 반도체지수", "빅테크 실적",
             "미국 국채 금리", "연준 금리", "FOMC", "파월", "미국 고용지표", "미국 CPI"],
    "금리·환율·원자재": ["원달러 환율", "기준금리 한국은행", "금통위", "국고채 금리", "소비자물가",
                    "수출 실적", "경상수지", "국제유가", "금값", "구리 가격", "천연가스 가격", "엔화 환율",
                    "중국 경기"],
    "정책": ["금융위원회 발표", "기획재정부 발표", "밸류업 프로그램", "상법 개정", "세제 개편",
           "예산안", "부동산 대책", "가계부채", "증시 부양책"],
    "지정학·무역": ["관세 부과", "미중 무역", "중동 정세", "러시아 우크라이나", "북한 미사일", "대만 해협",
                "반도체 수출 규제"],
    "기업": ["잠정실적", "어닝 서프라이즈", "어닝 쇼크", "단일판매 공급계약", "대규모 수주",
           "유상증자 결정", "자사주 소각", "인수합병", "기술이전 계약", "임상 결과", "공모주 청약", "신규 상장"],
    "테마": ["HBM", "AI 반도체", "로봇주", "휴머노이드", "2차전지주", "바이오 임상", "원전 SMR",
           "방산 수출", "조선 수주", "전력기기", "우주항공", "양자컴퓨터", "비트코인", "스테이블코인",
           "엔터주", "게임주", "자동차 관세"],
}

# 검색 결과 중 아래 도메인만 남김 (None으로 바꾸면 모든 매체 허용 — 블로그성 매체도 섞임)
OUTLETS = {
    "yna.co.kr": "연합뉴스", "einfomax.co.kr": "연합인포맥스", "hankyung.com": "한국경제",
    "mk.co.kr": "매일경제", "sedaily.com": "서울경제", "edaily.co.kr": "이데일리",
    "mt.co.kr": "머니투데이", "news.mt.co.kr": "머니투데이", "news1.kr": "뉴스1", "newsis.com": "뉴시스",
    "fnnews.com": "파이낸셜뉴스", "asiae.co.kr": "아시아경제", "heraldcorp.com": "헤럴드경제",
    "biz.chosun.com": "조선비즈", "chosun.com": "조선일보", "joongang.co.kr": "중앙일보",
    "donga.com": "동아일보", "hani.co.kr": "한겨레", "khan.co.kr": "경향신문", "hankookilbo.com": "한국일보",
    "etnews.com": "전자신문", "thebell.co.kr": "더벨", "newspim.com": "뉴스핌", "ajunews.com": "아주경제",
    "dt.co.kr": "디지털타임스", "ddaily.co.kr": "디지털데일리", "thelec.kr": "디일렉",
    "wowtv.co.kr": "한국경제TV", "biz.sbs.co.kr": "SBS Biz", "mbn.co.kr": "MBN", "ytn.co.kr": "YTN",
    "news.kbs.co.kr": "KBS", "imbc.com": "MBC", "news.sbs.co.kr": "SBS", "bizwatch.co.kr": "비즈니스워치",
    "infostock.co.kr": "인포스탁", "seoul.co.kr": "서울신문", "kmib.co.kr": "국민일보",
    "munhwa.com": "문화일보", "segye.com": "세계일보", "businesspost.co.kr": "비즈니스포스트",
    "korea.kr": "정책브리핑", "bok.or.kr": "한국은행",
}

# ---------------------------------------------------------------------------
# 3) 시장 숫자 — Yahoo Finance 차트 API (비공식, 키 불필요)
#    symbol=None: 무료 소스 없음 → '확인 못 함'
# ---------------------------------------------------------------------------
QUOTES = [
    # (그룹, 이름, 심볼, 배율, 단위)
    ("국내", "코스피", "^KS11", 1, ""),
    ("국내", "코스닥", "^KQ11", 1, ""),
    ("미국", "다우", "^DJI", 1, ""),
    ("미국", "S&P500", "^GSPC", 1, ""),
    ("미국", "나스닥", "^IXIC", 1, ""),
    ("미국", "반도체(SOX)", "^SOX", 1, ""),
    ("미국", "VIX", "^VIX", 1, ""),
    ("아시아", "닛케이225", "^N225", 1, ""),
    ("아시아", "상해종합", "000001.SS", 1, ""),
    ("아시아", "항셍", "^HSI", 1, ""),
    ("유가", "WTI", "CL=F", 1, "$"),
    ("유가", "브렌트", "BZ=F", 1, "$"),
    ("유가", "두바이유", None, 1, "$"),
    ("원자재", "금", "GC=F", 1, "$"),
    ("원자재", "구리", "HG=F", 1, "$"),
    ("원자재", "천연가스", "NG=F", 1, "$"),
    ("환율", "원/달러", "KRW=X", 1, "원"),
    ("환율", "원/엔(100엔)", "JPYKRW=X", 100, "원"),
    ("환율", "달러인덱스", "DX-Y.NYB", 1, ""),
    ("금리", "국고채 3년", None, 1, "%"),
    ("금리", "국고채 10년", None, 1, "%"),
    ("금리", "미 국채 2년", "2YY=F", 1, "%"),
    ("금리", "미 국채 10년", "^TNX", 1, "%"),
    ("가상자산", "비트코인", "BTC-USD", 1, "$"),
]

# 이 기준 이상 움직이면 표에서 강조
BIG_MOVE = {"index_pct": 2.0, "oil_pct": 3.0, "usdkrw_won": 10.0}
