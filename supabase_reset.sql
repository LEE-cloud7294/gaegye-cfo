-- =============================================
-- 가족 자산 관리 시스템 — 테이블 초기화 SQL
-- Supabase SQL Editor에 전체 붙여넣기 후 실행
-- =============================================

-- 기존 테이블 삭제 (의존성 순서: 자식 먼저)
DROP TABLE IF EXISTS insurance_surrender CASCADE;
DROP TABLE IF EXISTS memo CASCADE;
DROP TABLE IF EXISTS income_history CASCADE;
DROP TABLE IF EXISTS assets_snapshot CASCADE;
DROP TABLE IF EXISTS asset_history CASCADE;
DROP TABLE IF EXISTS family_data CASCADE;
DROP TABLE IF EXISTS insurance CASCADE;

-- =============================================
-- 테이블 재생성
-- =============================================

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
ON income_history (
    date,
    account_name,
    COALESCE(stock_name, ''),
    income_type,
    COALESCE(amount_krw::text, COALESCE(amount_usd::text, '0'))
);

-- 3. 자산 변화 이력 (자산현황 업로드 시 자동 저장)
CREATE TABLE asset_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_date date NOT NULL,
    account_name text NOT NULL,
    total_buy_krw numeric NOT NULL,
    total_eval_krw numeric NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_date, account_name)
);

-- 4. 가족 정보
CREATE TABLE family_data (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    relation text NOT NULL,
    birth_date date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- 5. 보험 기본 정보
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

-- 6. 보험 해약환급금 (insurance 삭제 시 CASCADE)
CREATE TABLE insurance_surrender (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    insurance_id bigint NOT NULL REFERENCES insurance(id) ON DELETE CASCADE,
    year_no int NOT NULL,
    surrender_amount numeric NOT NULL,
    surrender_rate numeric,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (insurance_id, year_no)
);

-- 7. 투자 메모
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
