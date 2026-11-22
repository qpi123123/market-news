# 한국투자증권 Open API 메모 (나중에 연결할 때)

2026-11-22 조사. 출처: 공식 GitHub 예제 저장소 [koreainvestment/open-trading-api](https://github.com/koreainvestment/open-trading-api)의 샘플 코드.
API 포털의 개별 명세 페이지는 열리지 않아(404) **공식 명세로는 확인 못 함** — 연결할 때 포털에서 다시 확인할 것.

## 공통
- 실전 도메인: `https://openapi.koreainvestment.com:9443`
- 토큰: `POST /oauth2/tokenP`, body `{grant_type:"client_credentials", appkey, appsecret}`
  - 응답 `access_token`, `access_token_token_expired`. 유효 1일. 6시간 안에 다시 요청하면 기존 토큰 반환.
  - 발급 1분당 1회 제한, 발급마다 카카오톡 알림 → **토큰을 저장해 재사용해야 함**.
- 호출 헤더: `authorization: Bearer <token>`, `appkey`, `appsecret`, `tr_id`, `custtype: P`
- 성공 여부: `rt_cd == "0"`. 초당 호출 초과 오류 `EGW00201` (실전 계좌 초당 한도 수치는 미확인).

## 쓸 만한 것
1. **시장별 투자자매매동향(일별)** — `GET /uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market`, tr_id `FHPTJ04040000`
   - 예: `FID_COND_MRKT_DIV_CODE=U, FID_INPUT_ISCD=0001, FID_INPUT_DATE_1=20250701, FID_INPUT_ISCD_1=KSP(코스닥 KSQ), FID_INPUT_DATE_2=20250701, FID_INPUT_ISCD_2=0001`
   - `output[]`: `frgn_ntby_tr_pbmn`(외국인 순매수 대금), `orgn_ntby_tr_pbmn`(기관계), `prsn_ntby_tr_pbmn`(개인), `stck_bsop_date`
   - **금액 단위 미확인** (원 / 백만원) — 첫 연결 때 기사 숫자와 대조해 확인할 것.
2. **외국인·기관 매매종목 가집계** — `GET /uapi/domestic-stock/v1/quotations/foreign-institution-total`, tr_id `FHPTJ04400000`
   - `FID_COND_MRKT_DIV_CODE=V, FID_COND_SCR_DIV_CODE=16449, FID_INPUT_ISCD=0000(전체)/0001(코스피)/1001(코스닥), FID_DIV_CLS_CODE=1(금액), FID_RANK_SORT_CLS_CODE=0(순매수상위)/1(순매도상위), FID_ETC_CLS_CODE=1(외국인)/2(기관계)`
   - `output[]`: `hts_kor_isnm`, `mksc_shrn_iscd`, `frgn_ntby_tr_pbmn`, `orgn_ntby_tr_pbmn`, `prdy_ctrt`
   - 장중 증권사 직원 집계(외국인 09:30·11:20·13:20·14:30, 기관 10:00·11:20·13:20·14:30), ±10분.
3. 국고채 3년·10년 금리: 샘플에서 **찾지 못함** (`comp-interest`는 해외 금리 지표로 표시됨).

## 사용자가 준비할 것
- 한국투자증권 계좌 → KIS Developers에서 API 신청 → 앱키·앱시크릿 → GitHub Secrets (`KIS_APP_KEY`, `KIS_APP_SECRET`)
