# 가족 자산 관리 시스템 — 프로젝트 명세서
> KB증권 기반 1인 가족 기업 회계 / Streamlit + Supabase

---

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [DB 스키마](#2-db-스키마)
3. [파서 명세](#3-파서-명세)
4. [앱 화면 명세](#4-앱-화면-명세)

---

## 1. 프로젝트 개요

### 목적
KB증권 4개 계좌의 자산을 통합 관리하며, 배당/이자 수입 추적, 가족 생애주기 재무 계획, 보험 자산 관리, 투자 메모/학습을 한 곳에서 운영한다. 모든 데이터를 JSON으로 LLM에 전달해 재무/투자 의견을 교류할 수 있는 1인 가족 기업 회계 플랫폼.

### 핵심 개념
```
수입        → 배당금, 이자, 세금환급
자산        → 주식 평가금액, 보험 해약환급금, 예수금
신규투자    → 외부에서 직접 투입한 돈 (월급, 저축 등)
계좌이체    → 계좌 간 자금 이동 (자산 총액 변화 없음)
소모 예측   → 타임스톤 이벤트별 예상 비용
```

### 기술 스택
- Frontend: Streamlit
- Backend DB: Supabase (PostgreSQL)
- 현재가 조회: yfinance API
- 차트: Plotly

### 계좌 구성
| 계좌명 | DB 저장명 | 통화 |
|---|---|---|
| 일반주식 (국내) | `일반주식_국내` | KRW |
| 일반주식 (해외) | `일반주식_해외` | USD |
| ISA | `ISA` | KRW |
| IRP | `IRP` | KRW |
| 연금저축 | `연금저축` | KRW |

---

## 2. DB 스키마

### 테이블 목록
| 테이블명 | 설명 |
|---|---|
| `assets_snapshot` | 계좌별 보유 주식 잔고 스냅샷 |
| `income_history` | 배당/이자/신규투자 전체 수입 내역 |
| `family_data` | 가족 구성원 정보 |
| `insurance` | 보험 기본 정보 |
| `insurance_surrender` | 보험 연도별 해약환급금 |
| `memo` | 투자 메모 / 학습 일지 |

---

### 2-1. assets_snapshot (자산 잔고 스냅샷)

업로드 시 해당 계좌 데이터 전체 삭제 후 새로 INSERT (덮어쓰기).
현재가는 yfinance API로 실시간 조회하므로 저장하지 않음.

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| `id` | bigint | NO | PK, auto increment |
| `account_name` | text | NO | 계좌명 |
| `market` | text | YES | 시장구분 (국내/해외) |
| `stock_name` | text | NO | 종목명 |
| `ticker` | text | YES | 티커 (국내: 005930, 해외: AAPL) |
| `quantity` | numeric | NO | 보유수량 |
| `avg_price` | numeric | NO | 평균단가 |
| `currency` | text | NO | 통화 (KRW/USD) |
| `uploaded_at` | timestamptz | NO | 업로드 일시 |

---

### 2-2. income_history (수입 내역)

배당/이자/신규투자/계좌이체 전체 누적 저장.
중복 방지: date + account_name + stock_name + income_type 조합으로 체크.

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| `id` | bigint | NO | PK, auto increment |
| `date` | date | NO | 거래일자 |
| `account_name` | text | NO | 계좌명 |
| `stock_name` | text | YES | 종목명 (이자/입금은 NULL) |
| `income_type` | text | NO | 수입 종류 (아래 허용값) |
| `amount_krw` | numeric | YES | 세전 금액 원화 |
| `amount_usd` | numeric | YES | 세전 금액 달러 (해외 배당) |
| `exchange_rate` | numeric | YES | 적용 환율 |
| `tax_krw` | numeric | YES | 세금 합계 원화 |
| `net_amount_krw` | numeric | YES | 세후 실수령액 원화 환산 |
| `created_at` | timestamptz | NO | DB 입력 일시 |

**income_type 허용값**
| 값 | 설명 | 집계 포함 여부 |
|---|---|---|
| `배당_국내` | 국내 주식 배당금 | 수입 집계 O |
| `배당_해외` | 해외 주식 배당금 | 수입 집계 O |
| `이자_예탁금` | 예탁금이용료 (일반/ISA/연금저축) | 수입 집계 O |
| `이자_현금자산` | 현금자산이자 (IRP) | 수입 집계 O |
| `이자_채권` | 채권이자 (IRP) | 수입 집계 O |
| `세금환급` | 해외원천세 환급 | 수입 집계 O |
| `신규투자` | 전자금융입금 / 은행이체 / IRP부담금 | 투자금 집계 O |
| `계좌이체` | 계좌 간 대체입금/출금 | 집계 제외 |

---

### 2-3. family_data (가족 정보)

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| `id` | bigint | NO | PK, auto increment |
| `name` | text | NO | 이름 (UNIQUE) |
| `relation` | text | NO | 관계 (본인/배우자/자녀/기타) |
| `birth_date` | date | NO | 생년월일 |
| `created_at` | timestamptz | NO | 등록 일시 |

---

### 2-4. insurance (보험 기본 정보)

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| `id` | bigint | NO | PK, auto increment |
| `company` | text | NO | 보험사명 |
| `product_name` | text | NO | 보험상품명 |
| `monthly_premium` | numeric | NO | 월 납입료 (원) |
| `start_date` | date | NO | 가입일 |
| `payment_end_date` | date | YES | 납입 종료일 |
| `contract_end_date` | date | YES | 계약 만기일 |
| `guaranteed_rate` | numeric | YES | 보장 고정금리 (%) |
| `note` | text | YES | 비고 |
| `created_at` | timestamptz | NO | 등록 일시 |

---

### 2-5. insurance_surrender (보험 해약환급금)

insurance와 1:N 관계. insurance 삭제 시 자동 삭제 (CASCADE).

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| `id` | bigint | NO | PK, auto increment |
| `insurance_id` | bigint | NO | FK → insurance.id |
| `year_no` | int | NO | 경과 년수 |
| `surrender_amount` | numeric | NO | 해약환급금 (원) |
| `surrender_rate` | numeric | YES | 납입원금 대비 환급률 (%) |
| `created_at` | timestamptz | NO | 등록 일시 |

---

### 2-6. memo (투자 메모 / 학습 일지)

| 컬럼명 | 타입 | NULL | 설명 |
|---|---|---|---|
| `id` | bigint | NO | PK, auto increment |
| `date` | date | NO | 작성일 |
| `category` | text | NO | 분류 (종목분석/시장동향/포트폴리오/기타) |
| `title` | text | NO | 제목 |
| `content` | text | NO | 내용 |
| `related_ticker` | text | YES | 관련 종목 티커 |
| `tags` | text | YES | 태그 (쉼표 구분) |
| `created_at` | timestamptz | NO | 작성 일시 |
| `updated_at` | timestamptz | YES | 수정 일시 |

---

### Supabase SQL

```sql
-- 1. 자산 잔고 스냅샷
CREATE TABLE assets_snapshot (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_name text NOT NULL,
    market text,
    stock_name text NOT NULL,
    ticker text,
    quantity numeric NOT NULL,
    avg_price numeric NOT NULL,
    currency text NOT NULL DEFAULT 'KRW',
    uploaded_at timestamptz NOT NULL DEFAULT now()
);

-- 2. 수입 내역
CREATE TABLE income_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date date NOT NULL,
    account_name text NOT NULL,
    stock_name text,
    income_type text NOT NULL,
    amount_krw numeric,
    amount_usd numeric,
    exchange_rate numeric,
    tax_krw numeric,
    net_amount_krw numeric,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX income_history_unique
ON income_history (date, account_name, COALESCE(stock_name, ''), income_type);

-- 3. 가족 정보
CREATE TABLE family_data (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    relation text NOT NULL,
    birth_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 4. 보험 기본 정보
CREATE TABLE insurance (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company text NOT NULL,
    product_name text NOT NULL,
    monthly_premium numeric NOT NULL,
    start_date date NOT NULL,
    payment_end_date date,
    contract_end_date date,
    guaranteed_rate numeric,
    note text,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 5. 보험 해약환급금
CREATE TABLE insurance_surrender (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    insurance_id bigint NOT NULL REFERENCES insurance(id) ON DELETE CASCADE,
    year_no int NOT NULL,
    surrender_amount numeric NOT NULL,
    surrender_rate numeric,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (insurance_id, year_no)
);

-- 6. 투자 메모
CREATE TABLE memo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    date date NOT NULL,
    category text NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    related_ticker text,
    tags text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);
```

---

## 3. 파서 명세

### 3-1. 공통 구조 (파서 A — 일반주식/ISA/연금저축)

2행이 1거래 구조.
```
행1: 거래일자 | 거래종류 | 수량 | 거래금액 | 정산금액 | 거래세 | 소득세 | 양도세 | 대출금 | 유가잔고 | 미수변제 | 통화구분 | 환율 | 국외수수료
행2: (빈칸)  | 종목명   | 단가  | 수수료   | 펀드번호  | 농특세  | 지방세  | 과기준가 | 신용이자 | 예수금  | 연체변제 | 외화예수금 | (빈) | 외화정산금액
```

**국내/해외 구분 기준**
- 통화구분 컬럼 = 공백 또는 KRW → 국내
- 통화구분 컬럼 = USD → 해외

**해외 배당 금액 추출**
- 거래금액 = NaN → 외화예수금 차분값 사용
- 실수령 USD = 현재행 외화예수금 - 이전행 외화예수금

**처리할 거래종류 목록**
| 거래종류 | income_type | 비고 |
|---|---|---|
| 배당금 입금 (KRW) | 배당_국내 | 통화구분 공백 |
| 배당금 입금 (USD) | 배당_해외 | 통화구분 USD |
| 예탁금이용료 입금 | 이자_예탁금 | |
| 해외원천세 환급 입금 | 세금환급 | |
| 전자금융입금 | 신규투자 | |
| 은행이체 입금 | 신규투자 | |
| 대체입금 | 계좌이체 | 집계 제외 |
| 대체출금 | 계좌이체 | 집계 제외, 음수 저장 |

**무시할 거래종류**
```
주식장내매수 / KOSDAQ매수 / 매수
주식장내매도 / KOSDAQ매도 / 매도
글로벌원마켓플러스외화매수 출금 (환전)
외화매도 (환전)
전자금융송금 출금 (출금)
해외원천세 출금 (환급과 상계)
배당세금추징 출금 (세금에 포함)
이자소득세추징 출금 (세금에 포함)
액면분할 입고 / 출고
```

---

### 3-2. IRP 전용 구조 (파서 B)

2행이 1거래 구조. 컬럼 순서가 파서 A와 다름. 통화 전부 KRW.
```
행1: 거래일자 | 거래종류 | 수량 | 거래금액 | 거래세 | 소득세 | 양도세 | 정산금액 | 대출금 | 유가잔고
행2: (빈칸)  | 종목명   | 단가  | 수수료   | 농특세  | 지방세  | 평가잔액 | 신용이자 | 대출이자변제 | 예수금
```

**처리할 거래종류**
| 거래종류 | income_type |
|---|---|
| 배당금 입금 | 배당_국내 |
| 현금자산이자(퇴직연금) 입금 | 이자_현금자산 |
| 채권이자(퇴직연금) 입금 | 이자_채권 |
| 기본부담금(퇴직연금) 입금 | 신규투자 |

**무시할 거래종류**
```
운용지시(퇴직연금) 매수
```

---

### 3-3. 잔고 파서 α (국내/ISA/연금저축/해외)

2행이 1종목 구조. 상단 요약 행 스킵 후 종목 데이터 시작.
```
행1: 종목명 | 평가손익 | 손익률 | 보유잔고 | 매도가능 | 평균단가 | 손익분기 | 현재가 | 매입금액
행2: 평가금액 | 투자비중 | 수수료 | 제세금 ...
```

**추출 컬럼**
```
종목명      → stock_name
보유잔고    → quantity
평균단가    → avg_price
```

현재가 / 평가금액 / 손익률은 저장하지 않음 (yfinance로 실시간 조회).

---

### 3-4. 잔고 파서 β (IRP)

3행이 1종목 구조.
```
행1: 계좌명 | 종목군 | 종목명    | 매입원금 | 보유잔고 | 평가금액 ...
행2: 제도명 |       | 종목번호  | 투자비율 | 예약수량 | 평가손익 ...
```

**추출 컬럼**
```
종목명      → stock_name
종목번호    → ticker
보유잔고    → quantity (행1의 보유잔고)
매입원금    → avg_price 계산용
```

---

## 4. 앱 화면 명세

### 메뉴 구성
```
사이드바
├── 대시보드 (홈)
├── 자산 현황
├── 배당 / 이자
├── 타임스톤
├── 보험 관리
├── 투자 메모
├── 데이터 관리 (업로드)
└── AI 재무 컨설팅
```

---

### 4-1. 대시보드 (홈) — 첫 페이지

**상단 핵심 지표 카드 (4개)**
```
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│  순자산 총합     │  이번달 배당/이자 │  계좌별 수익률   │  보험포함 순자산 │
│  ₩ 387,234,000  │  ₩ 1,245,000    │  +59.4%         │  ₩ 412,000,000  │
│  전월比 +2.3%   │  전월比 +12%    │  (평균)          │                 │
└─────────────────┴─────────────────┴─────────────────┴─────────────────┘
```

순자산 총합 계산식
```
순자산 = 전체 주식 평가금액 (yfinance 현재가 기준)
       + 보험 해약환급금 (현재 경과년수 기준)
       + 각 계좌 예수금
```

**중단 차트 (2개)**
```
┌──────────────────────────┬──────────────────────────┐
│  계좌별 자산 비중         │  월별 배당/이자 추이       │
│  (도넛 차트)              │  (바 차트, 최근 12개월)   │
└──────────────────────────┴──────────────────────────┘
```

**하단 차트 (1개)**
```
┌──────────────────────────────────────────────────────┐
│  신규투자 누적 vs 배당수입 누적 vs 자산 증가           │
│  (누적 영역 차트, 연도별)                              │
│  → 내 노동 투입 vs 자산이 스스로 번 돈 시각화          │
└──────────────────────────────────────────────────────┘
```

---

### 4-2. 자산 현황

**상단 전체 요약**
```
총 매입원금          현재 평가금액        총 손익
₩ 180,000,000       ₩ 287,000,000       +₩ 107,000,000 (+59.4%)
```

**계좌별 탭**
```
[전체] [일반주식_국내] [일반주식_해외] [ISA] [IRP] [연금저축]
```

각 탭 내 종목 테이블
```
종목명      수량    평균단가     현재가     평가금액      손익률
삼성전자    180주   73,049원    62,500원   11,250,000   -14.4%
SK하이닉스    8주  478,325원   232,400원   1,859,200   -51.4%
```

현재가는 yfinance 실시간 조회. 조회 시각 표시.

**하단 차트 (2개)**
```
┌──────────────────────────┬──────────────────────────┐
│  종목별 비중              │  종목별 손익률 비교        │
│  (도넛 차트)              │  (가로 바차트)             │
└──────────────────────────┴──────────────────────────┘
```

---

### 4-3. 배당 / 이자

**상단 핵심 지표**
```
올해 누적 배당/이자    이번달 배당/이자    월평균 배당/이자    전체 YOC
₩ 3,240,000          ₩ 487,000         ₩ 270,000          3.8%
```

**중단 좌 — 월별 배당 달력 히트맵**
```
      1월   2월   3월   4월   5월   6월   7월   8월   9월   10월  11월  12월
2024  ■     ■     ■■    ■■■   ■■    ■■■   ■■■   ■■    ■■■   ■■■   ■■    ■■■
2025  ■     ■■    ■■    ■■■   ■■    ■■■   ■■■   ■■    ■■■   ■■■   ■■    ■■■
```
색상 진할수록 배당 금액 큼. 클릭 시 해당 월 상세.

**중단 우 — 연도별 배당 성장 바차트**
```
2021  ▓▓               362,000원
2022  ▓▓▓              480,000원
2023  ▓▓▓▓             650,000원
2024  ▓▓▓▓▓▓▓▓        1,840,000원
2025  ▓▓▓▓▓▓▓▓▓▓▓     2,980,000원
```

**하단 — 월 선택 시 종목별 상세 테이블**
```
종목        보유수량   1주당배당    총배당(세전)  세금      세후실수령   YOC     현재가배당률
삼성전자    180주      361원/분기   181,120원    27,880    153,240    4.9%    5.8%
리얼티인컴  240주      $0.268/월    $64.32       $9.65     $54.67     7.1%    5.2%
SCHD       240주      $0.78/분기   $187.2       $28.08    $159.12    8.2%    3.4%
```

YOC = 매입원금 기준 연간 배당수익률 (장기투자 핵심 지표)

---

### 4-4. 타임스톤

**상단 — 가족 현황 카드**
```
본인 ○○세    배우자 ○○세    자녀1 ○○세    자녀2 ○○세
```

**중단 — 연도별 타임라인**
```
2026  2027  2028  2029  2030  2031  2032  2033 ...
                  자녀1                   자녀1
                  초등입학                중학입학
        자녀2
        어린이집
본인
IRP납입
```

**하단 — 연도별 이벤트 + 자산 대조 테이블**
```
연도   이벤트           예상비용      예상자산      월배당예상    여유
2029  자녀1 초등입학    300만원       4억 2천       80만원       ✅
2032  자녀1 중학입학    500만원       5억 1천       120만원      ✅
2038  자녀1 대학입학   4,000만원      7억 8천       220만원      ✅
2042  본인 은퇴목표       -          10억 목표      350만원      △
```

**자산 시뮬레이션 입력값**
```
현재 자산 (자동)    월 투자금 (입력)    예상 수익률 (입력, 기본 7%)
```

**이벤트 기본값 (수정 가능)**
```
초등입학   200만원
중학입학   500만원
고등입학   800만원
대학입학  4,000만원
결혼      5,000만원
```

---

### 4-5. 보험 관리

**보험 목록 카드**
```
┌──────────────────────────────────────┐
│  [보험사명] 상품명                    │
│  월납입: 300,000원   가입일: 2020-03  │
│  보장금리: 3.5%      만기: 2050-03   │
│  현재 경과년수: 6년차                 │
│  현재 해약환급금: ₩ 18,420,000       │
│  납입원금 대비: 85.3%                │
└──────────────────────────────────────┘
```

**연도별 해약환급금 테이블**
```
년차   해약환급금      납입원금대비    누적납입원금
1년    2,100,000      29.2%         7,200,000
5년   14,500,000      67.1%        36,000,000
10년  32,000,000     111.1%        72,000,000 ← 원금 회복
20년  68,000,000     157.4%        86,400,000
```

---

### 4-6. 투자 메모

**작성 폼**
```
날짜 / 카테고리 (종목분석/시장동향/포트폴리오/기타) / 제목
관련 티커 (선택) / 태그 (쉼표 구분)
내용 (텍스트 에디터)
```

**메모 목록**
```
카테고리 / 태그 필터
날짜 역순 정렬
제목 클릭 시 상세 보기 / 수정 / 삭제
```

---

### 4-7. 데이터 관리 (업로드)

**자산현황 업로드**
```
계좌 선택: [일반주식_국내] [일반주식_해외] [ISA] [IRP] [연금저축]
파일 업로드 (xlsx)
미리보기 후 확인 버튼 → 덮어쓰기 저장
```

**거래내역 업로드**
```
계좌 선택: [일반주식(국내+해외)] [ISA] [IRP] [연금저축]
파일 업로드 (xlsx)
파싱 결과 미리보기 (저장될 항목만 표시)
중복 건수 표시 → 확인 버튼 → 누적 저장
```

---

### 4-8. AI 재무 컨설팅

**JSON 생성**
```
[내 재무 데이터 JSON 생성] 버튼
→ 전체 자산 / 배당 내역 / 가족 정보 / 보험 / 메모 통합
→ 코드블록으로 출력 (복사 버튼)
→ ChatGPT / Claude / Gemini 에 붙여넣기 후 질문
```

---

## 5. 개발 우선순위

```
1단계 (핵심)
├── Supabase 테이블 생성 (SQL 실행)
├── 거래내역 파서 A + B 구현
├── 자산현황 파서 α + β 구현
├── 데이터 관리 페이지 (업로드)
└── 배당/이자 페이지

2단계 (주요)
├── 대시보드 (홈)
├── 자산 현황 페이지 (yfinance 연동)
└── 보험 관리 페이지

3단계 (부가)
├── 타임스톤 페이지
├── 투자 메모 페이지
└── AI 재무 컨설팅 페이지
```
