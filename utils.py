"""공통 데이터 로딩 + yfinance 헬퍼"""
import re
import streamlit as st
import pandas as pd
import yfinance as yf
from db import get_client

_SKIP_TICKER = re.compile(r'^(RI\d+|KR[A-Z0-9]{10}|[A-Z]{2}\d{10,})$')

# DB 저장 티커 → yfinance 실제 티커 변환 테이블
_TICKER_MAP: dict[str, str] = {
    "BRK.B":  "BRK-B",   # 버크셔 해서웨이 B
    "0064K0": "069660",   # KODEX 금액티브 (KRX 실제 코드)
}


def _yf_ticker(t: str) -> str | None:
    if not t:
        return None
    t = _TICKER_MAP.get(t, t)        # 특수 매핑 먼저 적용
    if _SKIP_TICKER.match(t):
        return None
    if re.match(r'^\d{6}$', t):
        return f"{t}.KS"
    return t


@st.cache_data(ttl=1800)   # 30분 캐시 — API 과부하 방지
def get_usd_krw() -> float:
    try:
        hist = yf.Ticker("USDKRW=X").history(period="5d")
        if not hist.empty:
            return float(hist["Close"].dropna().iloc[-1])
    except Exception:
        pass
    return 1380.0


@st.cache_data(ttl=1800)   # 30분 캐시
def get_prices_bulk(tickers: tuple) -> dict:
    """DB 티커 → {db_ticker: price}. 국내/해외 모두 yf.download 배치 처리."""
    if not tickers:
        return {}

    mapping = {t: _yf_ticker(t) for t in tickers}
    yf_list = list({v for v in mapping.values() if v})   # 중복 제거
    if not yf_list:
        return {}

    yf_prices: dict[str, float] = {}

    # 20개씩 나눠서 배치 다운로드 (Yahoo 과부하 방지)
    BATCH = 20
    for i in range(0, len(yf_list), BATCH):
        batch = yf_list[i: i + BATCH]
        try:
            if len(batch) == 1:
                hist = yf.Ticker(batch[0]).history(period="5d")
                if not hist.empty:
                    yf_prices[batch[0]] = float(hist["Close"].dropna().iloc[-1])
            else:
                raw = yf.download(batch, period="5d", progress=False,
                                  auto_adjust=True, group_by="ticker")
                for sym in batch:
                    try:
                        if sym in raw.columns.get_level_values(0):
                            s = raw[sym]["Close"].dropna()
                        elif "Close" in raw.columns:
                            s = raw["Close"].dropna()
                        else:
                            continue
                        if not s.empty:
                            yf_prices[sym] = float(s.iloc[-1])
                    except Exception:
                        pass
        except Exception:
            pass

    return {db_t: yf_prices[yf_t] for db_t, yf_t in mapping.items()
            if yf_t and yf_t in yf_prices}


def _fetch_all(table: str, query_fn=None) -> list:
    """Supabase 1000행 한도 우회 — 페이지네이션으로 전체 조회"""
    PAGE = 1000
    all_data, offset = [], 0
    while True:
        q = get_client().table(table).select("*")
        if query_fn:
            q = query_fn(q)
        chunk = q.range(offset, offset + PAGE - 1).execute().data
        if not chunk:
            break
        all_data.extend(chunk)
        if len(chunk) < PAGE:
            break
        offset += PAGE
    return all_data


def load_assets() -> pd.DataFrame:
    data = _fetch_all("assets_snapshot")
    return pd.DataFrame(data) if data else pd.DataFrame()


def load_income() -> pd.DataFrame:
    data = _fetch_all("income_history", lambda q: q.order("date", desc=False))
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    return df


def load_family() -> pd.DataFrame:
    data = get_client().table("family_data").select("*").execute().data
    return pd.DataFrame(data) if data else pd.DataFrame()


def load_insurance() -> pd.DataFrame:
    data = get_client().table("insurance").select("*").execute().data
    return pd.DataFrame(data) if data else pd.DataFrame()


def load_surrender(insurance_id: int) -> pd.DataFrame:
    data = (get_client().table("insurance_surrender")
            .select("*").eq("insurance_id", insurance_id)
            .order("year_no").execute().data)
    return pd.DataFrame(data) if data else pd.DataFrame()


def load_memo() -> pd.DataFrame:
    data = _fetch_all("memo", lambda q: q.order("date", desc=True))
    return pd.DataFrame(data) if data else pd.DataFrame()


def load_asset_history() -> pd.DataFrame:
    data = _fetch_all("asset_history", lambda q: q.order("snapshot_date", desc=False))
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


INCOME_TYPES = {"배당_국내", "배당_해외", "이자_예탁금", "이자_현금자산", "이자_채권", "세금환급", "세금추징"}

# 계좌별 색상 (모든 페이지에서 공용)
ACCT_COLORS = {
    "일반주식_국내": "#4C72B0",
    "일반주식_해외": "#DD8452",
    "ISA":          "#55A868",
    "IRP":          "#C44E52",
    "연금저축":     "#8172B2",
}

# 의미별 색상
COLORS = {
    "asset":    "#4C72B0",
    "income":   "#55A868",
    "loss":     "#C44E52",
    "insurance":"#8172B2",
}


def fmt_won(v: float) -> str:
    """테이블용 — ₩387,234,000"""
    if v is None:
        return "-"
    return f"₩{int(v):,}"


def calc_net_worth(df_assets: "pd.DataFrame", prices: dict,
                   usd_krw: float, df_ins: "pd.DataFrame") -> dict:
    """
    순자산 = 주식 평가금액(현재가) + 보험 해약환급금
    Returns: {eval_total, cash, insurance, net_worth}
    """
    from datetime import date as _date
    today = _date.today()

    eval_total = 0.0
    if df_assets is not None and not df_assets.empty:
        for _, r in df_assets.iterrows():
            ticker = r.get("ticker") if r.get("ticker") else None
            if r["currency"] == "USD" and ticker and ticker in prices:
                eval_total += r["quantity"] * prices[ticker] * usd_krw
            elif r["currency"] == "KRW" and ticker and ticker in prices:
                eval_total += r["quantity"] * prices[ticker]
            else:
                eval_total += r["quantity"] * r["avg_price"] * (usd_krw if r["currency"] == "USD" else 1)

    insurance = 0.0
    if df_ins is not None and not df_ins.empty:
        for _, ins in df_ins.iterrows():
            start = pd.to_datetime(ins["start_date"]).date()
            elapsed = max(1, (today - start).days // 365)
            df_s = load_surrender(ins["id"])
            if not df_s.empty:
                row = df_s[df_s["year_no"] == elapsed]
                if not row.empty:
                    insurance += float(row.iloc[0]["surrender_amount"])
                else:
                    nearest = df_s.iloc[(df_s["year_no"] - elapsed).abs().argsort()[:1]]
                    insurance += float(nearest.iloc[0]["surrender_amount"])

    return {
        "eval_total": eval_total,
        "cash": 0.0,
        "insurance": insurance,
        "net_worth": eval_total + insurance,
    }
