# 가계 CFO 앱 — 최종 수정 지시서

GitHub: https://github.com/LEE-cloud7294/gaegye-cfo

아래 순서대로 진행해줘.

---

## 1. Supabase — asset_history 테이블 추가

supabase_reset.sql에 아래 테이블 추가 및 Supabase에서 직접 실행:

```sql
CREATE TABLE asset_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_date date NOT NULL,
    account_name text NOT NULL,
    total_buy_krw numeric NOT NULL,
    total_eval_krw numeric NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (snapshot_date, account_name)
);
```

---

## 2. app.py — 자산현황 업로드 시 asset_history 자동 저장

데이터 관리 탭에서 자산현황 파일 저장 시
기존 assets_snapshot 덮어쓰기는 그대로 유지하고
추가로 asset_history에 계좌별 합산 금액 자동 저장.

저장 내용:
- snapshot_date: 오늘 날짜
- account_name: 업로드한 계좌명
- total_buy_krw: sum(quantity × avg_price), USD는 get_usd_krw() 환율 적용
- total_eval_krw: total_buy_krw와 동일 저장
  (현재가 조회는 업로드 시 속도 문제로 매입가 기준 저장)

같은 날짜+계좌가 이미 있으면 upsert로 덮어쓰기.

---

## 3. utils.py — load_asset_history() 함수 추가

```python
def load_asset_history() -> pd.DataFrame:
    data = _fetch_all("asset_history", lambda q: q.order("snapshot_date", desc=False))
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
```

---

## 4. page_dashboard.py — 자산 추이 차트 추가

utils.py에서 load_asset_history() 호출.
대시보드 [요약] 탭 하단에 섹션 추가:

차트 내용:
- 제목: "자산 변화 추이"
- x축: snapshot_date
- y축: 계좌별 total_buy_krw 스택 영역 차트
- 계좌별 색상: 기존 ACCT_COLORS 사용
- 데이터가 1개 이하면:
  st.info("업로드를 누적하면 자산 변화 추이가 표시됩니다.")

---

## 5. page_dashboard.py — 신규투자 누적 섹션 제거

현재 대시보드 마지막 섹션:
"신규투자 누적 vs 배당/이자 누적" 영역 차트 전체 제거.

제거 이유:
- 매수/매도 미추적으로 인한 부정확한 수치
- 투자금 회수 개념 없음
- 2021년 이전 데이터 누락
- 잘못된 정보를 보여줄 수 있음

---

## 6. parser_income.py — 금액 파싱 버그 수정

**버그 1: 세금환급 금액 None**
'해외원천세 환급 입금' 거래의 net_amount_krw가 None으로 저장됨.
실제 엑셀에서 해당 거래의 금액 컬럼 위치 확인 후 파싱 로직 수정.

**버그 2: 이자_예탁금 금액 None**
'예탁금이용료 입금' 거래의 net_amount_krw가 None으로 저장됨.
r1[3](거래금액)을 fallback으로 사용하는지 확인 및 수정.

---

## 7. income_history 중복 방지 인덱스 수정

**문제:**
현재 unique index: date + account_name + stock_name + income_type
같은 날 동일 유형 거래가 2건이면 두 번째 건이 DB에 누락됨.
(예: 하루 2번 입금, 같은 날 다른 금액 신규투자 2건)

**수정:**
supabase_reset.sql의 unique index를 아래로 변경:

```sql
-- 기존 인덱스 삭제
DROP INDEX IF EXISTS income_history_unique;

-- 신규 인덱스 (amount_krw 추가)
CREATE UNIQUE INDEX income_history_unique
ON income_history (
    date,
    account_name,
    COALESCE(stock_name, ''),
    income_type,
    COALESCE(amount_krw::text, COALESCE(amount_usd::text, '0'))
);
```

Supabase에서 직접 실행 필요.

---

## 작업 순서

```
1 → Supabase SQL 실행 (테이블 생성, 인덱스 수정)
2 → utils.py 수정 (load_asset_history 추가)
3 → app.py 수정 (asset_history 자동 저장)
4 → page_dashboard.py 수정 (추이 차트 추가, 신규투자 섹션 제거)
5 → parser_income.py 수정 (버그 2건)
6 → GitHub push
```

---

## 완료 후 확인 사항

- [ ] Supabase에 asset_history 테이블 생성됐는가
- [ ] 자산현황 업로드 시 asset_history에 자동 저장되는가
- [ ] 대시보드에 자산 추이 섹션이 표시되는가
- [ ] 신규투자 누적 차트가 제거됐는가
- [ ] 세금환급/이자_예탁금 금액이 정상 저장되는가
- [ ] 같은 날 동일 유형 2건 업로드 시 둘 다 저장되는가
