# 가계 CFO 앱 — 수정 완료 보고서

> 모든 항목 완료 · 2026-06-06 기준

---

## A. 지표 정확성 ✅ 전체 완료

### A-1. 순자산 정의 통일 ✅
- `utils.py`에 `calc_net_worth()` 함수 신설
- 반환값: `{eval_total, cash, insurance, net_worth}`
- 대시보드, 타임스톤 모두 이 함수 기준으로 통일
- **버그 수정**: `page_timestore.py`의 현재 자산이 매입가(avg_price) → **현재가(yfinance)** 기준으로 수정

---

### A-2. 투입자본 2개 지표 분리 ✅
`page_dashboard.py` 요약탭 "자본 지표" 섹션에 3개 카드로 분리 표시:

| 카드 | 내용 |
|---|---|
| 투입원금 (Cost Basis) | `quantity × avg_price` — 수익률 계산 분모 |
| 누적 순현금투입 | `income_type='신규투자'` 누계 (계좌이체 제외) |
| 배당재투자·복리효과 | 투입원금 − 순현금투입 |

---

### A-3. 총수익률 = 토탈리턴 ✅
`page_dashboard.py` 요약탭 "수익률 분해" 섹션에 3개 카드:

```
자본이득률  = (평가금액 − 투입원금) / 투입원금
배당기여률  = 누적배당/이자 / 투입원금
토탈리턴   = 자본이득률 + 배당기여률
```

---

### A-4. 신규투자 분류 재검증 ✅
- `parser_income.py`에서 대체입금/대체출금은 `계좌이체`로 분류됨 확인
- 대시보드 현금흐름 탭 집계에서도 `INCOME_TYPES` 필터로 제외 보장

---

### A-5. YOC 계산 기준 통일 ✅
- `page_income.py` YOC → **최근 1년 배당 기준**으로 수정
- `page_dashboard.py`와 동일 기준 (최근 365일 배당합계 / 투입원금)

---

## B. 누락 기능 추가 ✅ 전체 완료

### B-1. 현금흐름 지표 ✅
`page_dashboard.py` 현금흐름 탭 신설:
- 월평균 배당/이자
- 월평균 신규투입
- **FIRE 지표**: 월 생활비 입력 → 배당 생활비 커버율 자동 계산

### B-2. 자산배분 분석 ✅
`page_dashboard.py` 자산분석 탭에 파이 차트 3개 추가:
- 국내(KRW) vs 해외(USD) 비중
- 자산군별: 주식/ETF vs 현금/채권 vs 보험
- 통화 노출: KRW vs USD

### B-3. 목표 대비 진행률 ✅
`page_dashboard.py` 요약 탭:
- 목표 순자산(억원) 입력 → progress bar 표시
- CAGR(연복리수익률) 자동 계산 (첫 투자일 기준)

---

## C. UI / 가독성 ✅ 전체 완료

### C-1. 대시보드 탭 분리 ✅
기존 긴 세로 스크롤 → **4탭 구조**로 재편:

```
[📊 요약]     핵심지표 + 자본지표 + 수익률분해 + 목표진행률
[🏦 자산분석] 계좌별 비중 + 자산배분(국내/해외/자산군/통화)
[💰 배당분석] 배당주/성장주 분류 + 월별/연도별 배당 차트
[📈 현금흐름] FIRE지표 + 신규투자 vs 배당 누적 차트
```

### C-2. 색상 체계 통일 ✅
`utils.py`에 `ACCT_COLORS`, `COLORS` 중앙 관리:
```python
ACCT_COLORS = { 일반주식_국내, 일반주식_해외, ISA, IRP, 연금저축 }
COLORS = { asset, income, loss, insurance }
```
`page_assets.py`, `page_dashboard.py` 모두 `utils.py`에서 import

### C-3. 숫자 단위 헬퍼 ✅
`utils.py`에 추가:
```python
fmt_short(v)  # ₩3.87억, ₩1,200만  (대시보드 카드용)
fmt_won(v)    # ₩387,234,000        (테이블용)
```

---

## D. 정리 / 보안 ✅ 전체 완료

### D-1. 디버그 파일 정리 ✅
9개 파일 → `debug/` 폴더로 이동:
```
check_tickers.py, check_tickers2.py, check_pagination.py,
check_2026.py, check_data.py, full_check.py,
debug_raw.py, verify_parser.py, reset_income.py
```

### D-2. 보안 ✅
`.gitignore`에 추가됨:
```
.streamlit/secrets.toml   ← Supabase 키 보호
debug/                    ← 디버그 파일
.claude/                  ← Claude Code 설정
file_structure.txt        ← 임시 파일
```

---

## E. 버그 수정 ✅ 전체 완료

### E-1. page_timestore.py ✅
```python
# 수정 전: 루프 안에서 매번 DB 조회 (N회 호출)
for yr in ...:
    df_inc = load_income()  # ← 매번 호출

# 수정 후: 루프 밖에서 1회만 호출
df_inc = load_income()
for yr in ...:
    ...
```

### E-2. page_insurance.py ✅
```python
cur_surr = 0
surr_rate = 0   # ← 초기값 추가 (미정의 방지)
if not df_s.empty:
    ...
```

### E-3. page_income.py ✅
TAB 2 상단에 `df_assets = load_assets()` 명시적 재선언 추가

---

## 추가 작업 (수정지시서 외)

### Git + GitHub 배포 ✅
- Git 설치 (v2.54.0)
- `requirements.txt` 생성
- GitHub 레포: `LEE-cloud7294/gaegye-cfo` (Public)
- Initial commit → push 완료

### Streamlit Cloud 배포 ✅
- `share.streamlit.io` 연동
- Secrets 등록 완료
- 온라인 접속 가능

---

## 검증 체크리스트

- [x] 대시보드/타임스톤/AI의 순자산 값이 동일한 함수 사용
- [x] 투입원금과 누적순현금투입이 별도로 표시됨
- [x] 대체입금/출금이 신규투자 집계에서 제외됨
- [x] YOC가 모든 페이지에서 최근 1년 기준
- [x] 색상이 utils.py에서 중앙 관리됨
- [x] 디버그 파일 debug/ 정리, secrets .gitignore 적용
- [x] GitHub push 완료
- [x] Streamlit Cloud 배포 완료
