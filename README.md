# 가족 자산 관리 시스템 (가계 CFO)

> KB증권 기반 개인/가족 자산 통합 관리 · Streamlit + Supabase

---

## 실행 방법

```
run.bat 더블클릭
```
또는 터미널에서:
```
"C:\Users\HG_PC\AppData\Local\Python\pythoncore-3.14-64\Scripts\streamlit.exe" run app.py
```
브라우저 → http://localhost:8501

---

## 프로젝트 구조

```
가계CFO/
├── app.py                  # 메인 앱 (사이드바 라우팅)
├── db.py                   # Supabase 클라이언트
├── utils.py                # 공통 데이터 로딩 + yfinance 헬퍼
├── parser_income.py        # 거래내역 파서 A(일반주식/ISA/연금저축) + B(IRP)
├── parser_assets.py        # 잔고 파서 α(국내/해외) + β(IRP)
├── page_dashboard.py       # 대시보드
├── page_assets.py          # 자산 현황
├── page_income.py          # 배당 / 이자
├── page_insurance.py       # 보험 관리
├── page_memo.py            # 투자 메모
├── page_timestore.py       # 타임스톤
├── page_ai.py              # AI 재무 컨설팅
├── .streamlit/
│   └── secrets.toml        # Supabase URL + anon key
├── supabase_reset.sql      # 테이블 초기화 SQL
└── run.bat                 # 앱 실행 배치파일
```

---

## Supabase 연결 정보

- **URL**: https://pqszqbwpqbdddifqibqb.supabase.co
- **설정 파일**: `.streamlit/secrets.toml`

---

## DB 테이블

| 테이블 | 설명 |
|---|---|
| `assets_snapshot` | 계좌별 보유 주식 잔고 (업로드 시 덮어쓰기) |
| `income_history` | 배당/이자/신규투자 전체 누적 (중복 방지) |
| `family_data` | 가족 구성원 (이름, 관계, 생년월일) |
| `insurance` | 보험 기본 정보 |
| `insurance_surrender` | 보험 연도별 해약환급금 |
| `memo` | 투자 메모 / 학습 일지 |

---

## 페이지별 기능

### 대시보드
- 순자산 / 올해 배당 / 수익률 / 보험포함자산 지표 카드
- 계좌별 자산 비중 (현재가기준 + 매입가기준 동시 표시)
- 배당주 / 성장주 분류 (YOC ≥ 1.5% 기준, 계좌 필터)
- 월별 배당 바차트 + 연도별 배당 성장
- 신규투자 누적 vs 배당 누적 영역 차트

### 자산 현황
- 계좌별 탭 (전체 / 일반주식_국내 / 해외 / ISA / IRP / 연금저축)
- yfinance 실시간 현재가 (30분 캐시)
- 계좌별 자산 비중 도넛 2개 (현재가 / 매입가)
- 종목별 비중 파이 + 수익률 막대 (손익 상위10 + 하위5)
- IRP 현금/채권은 별도 expander로 분리

### 배당 / 이자
- 최근 2개월 배당 내역 나란히
- 연도별 성장 바차트
- 월별 캐시플로우 (KRW/USD 전환)
- **월별 배당 현황 히트맵 표** (연도×월, 금액 클수록 진한 초록)
- 월별 종목 상세 (연도/월 선택)
- 종목별 배당 분석 [티커|종목|총배당|횟수|보유수량|주당배당]
- 수입 종류별 / 계좌별 비중 파이

### 타임스톤
- 가족 구성원 CRUD
- 자녀 생애주기 이벤트 (어린이집~대학)
- 자산 시뮬레이션 (복리 + 월투자금 설정)
- 연도별 이벤트 vs 예상자산 대조표

### 보험 관리
- 보험 추가 / 삭제
- 연도별 해약환급금 입력 (data_editor)
- 현재 경과년수 강조

### 투자 메모
- 카테고리 / 연도 / 검색 필터
- 메모 작성 / 삭제

### 데이터 관리 (업로드)
- 자산현황: 계좌 선택 → 파일 → 파싱 미리보기 → 저장 (덮어쓰기)
- 거래내역: 파일 파싱 → 신규/중복 카운트 표시 → 신규만 저장
- 계좌별 최근 업로드 현황 표시

### AI 재무 컨설팅
- 전체 자산 JSON 생성 (자산 + 배당 + 가족 + 보험 + 메모)
- 다운로드 버튼
- ChatGPT / Claude 질문 예시

---

## 데이터 업로드 순서

1. **자산현황** 탭 → 계좌별 xlsx 업로드 (5개 계좌)
   - 일반주식_국내, 일반주식_해외, ISA, IRP, 연금저축
2. **거래내역** 탭 → 계좌별 xlsx 업로드
   - 일반주식(국내+해외), ISA, IRP, 연금저축

---

## 티커 형식

| 종류 | 형식 | 예시 |
|---|---|---|
| 국내 주식/ETF | 6자리 숫자 | `005930` (삼성전자) |
| 해외 주식 | 심볼 그대로 | `SCHD`, `O`, `AAPL` |
| 버크셔 | `BRK.B` 입력 시 자동변환 | `BRK-B` |
| KODEX 금액티브 | `0064K0` 입력 시 자동변환 | `069660` |

---

## 알려진 사항

- **현재가**: Yahoo Finance 무료 API 사용 (30분 캐시), 과부하 시 매입가로 자동 fallback
- **Supabase 한도**: 1,356건+ 데이터를 페이지네이션(1,000건씩)으로 전체 조회
- **IRP 현금/채권**: 자산현황에서 별도 분리 표시 (주식 목록 제외)
- **배당주 분류**: 최근 1년 YOC ≥ 1.5% 기준

---

## 필요 패키지

```
pip install streamlit supabase==2.9.1 yfinance plotly openpyxl pandas
```
