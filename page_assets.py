import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import load_assets, get_usd_krw, get_prices_bulk, ACCT_COLORS, fmt_won
from db import get_client

# IRP 비투자자산 필터 (현금/채권)
_NON_STOCK = {"현금자산"}
_NON_STOCK_TICKER = {"RI9010000001", "KR103502GD64"}


def _color_seq(accounts):
    return [ACCT_COLORS.get(a, "#999999") for a in accounts]


def render():
    st.title("자산 현황")

    df_all = load_assets()
    if df_all.empty:
        st.info("데이터 없음 — 데이터 관리에서 잔고 파일을 업로드하세요.")
        return

    usd_krw = get_usd_krw()

    # 주식/ETF vs 현금/채권 분리
    df_cash = df_all[
        df_all["stock_name"].isin(_NON_STOCK) |
        df_all["ticker"].isin(_NON_STOCK_TICKER)
    ].copy()
    df = df_all[
        ~(df_all["stock_name"].isin(_NON_STOCK) |
          df_all["ticker"].isin(_NON_STOCK_TICKER))
    ].copy()

    tickers = tuple(df.dropna(subset=["ticker"])["ticker"].unique())
    with st.spinner("현재가 조회 중... (캐시: 30분)"):
        try:
            prices = get_prices_bulk(tickers)
        except Exception:
            prices = {}
            st.warning("현재가 조회 실패 — 매입가 기준으로 표시합니다. 잠시 후 새로고침 하세요.")

    def eval_unit(r):
        if r["currency"] == "USD" and r["ticker"] and r["ticker"] in prices:
            return prices[r["ticker"]] * usd_krw, prices[r["ticker"]]
        if r["currency"] == "KRW" and r["ticker"] and r["ticker"] in prices:
            return prices[r["ticker"]], prices[r["ticker"]]
        return r["avg_price"], None

    df[["eval_unit_krw", "cur_price"]] = df.apply(lambda r: pd.Series(eval_unit(r)), axis=1)
    df["eval_amount"] = df["quantity"] * df["eval_unit_krw"]
    df["buy_amount"]  = df.apply(
        lambda r: r["quantity"] * r["avg_price"] * (usd_krw if r["currency"] == "USD" else 1), axis=1)
    df["gain"]        = df["eval_amount"] - df["buy_amount"]
    df["return_pct"]  = ((df["gain"] / df["buy_amount"]) * 100).round(2).where(df["buy_amount"] > 0)

    total_eval = df["eval_amount"].sum()
    total_buy  = df["buy_amount"].sum()
    total_ret  = (total_eval / total_buy - 1) * 100 if total_buy else 0

    # ── 전체 요약 카드 ────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 매입원금 (매입가)",  f"₩{total_buy:,.0f}")
    c2.metric("현재 평가금액 (현재가)", f"₩{total_eval:,.0f}")
    c3.metric("총 손익",             f"₩{df['gain'].sum():,.0f}", delta=f"{total_ret:+.1f}%")
    c4.metric("현재가 조회",          f"{len(prices)}/{len(tickers)}종목  |  USD/KRW {usd_krw:,.0f}")

    # ── IRP 비투자자산 알림 ───────────────────────────────────────
    if not df_cash.empty:
        with st.expander(f"ℹ️ IRP 현금/채권 자산 ({len(df_cash)}개 — 주식 목록에서 분리됨)"):
            dc = df_cash[["account_name","stock_name","ticker","quantity","avg_price","currency"]].copy()
            dc["평가금액(원)"] = (dc["quantity"] * dc["avg_price"]).apply(lambda v: f"₩{v:,.0f}")
            st.dataframe(dc.rename(columns={"account_name":"계좌","stock_name":"종목명",
                                             "ticker":"코드","quantity":"수량","avg_price":"단가"}),
                         use_container_width=True, hide_index=True)

    st.divider()

    # ── ticker 직접 입력 ──────────────────────────────────────────
    with st.expander("국내 종목 ticker 입력 (예: 005930)"):
        no_t = df[df["ticker"].isna() & (df["currency"] == "KRW")][["stock_name","account_name"]].drop_duplicates()
        if not no_t.empty:
            for _, row in no_t.iterrows():
                safe = f"{row['account_name']}_{row['stock_name']}".replace(" ","_")
                ca, cb = st.columns([2,1])
                ca.write(f"**{row['stock_name']}** ({row['account_name']})")
                tv = cb.text_input("ticker", key=f"tk_{safe}", placeholder="005930")
                if tv and st.button("저장", key=f"sv_{safe}"):
                    get_client().table("assets_snapshot").update({"ticker": tv})\
                        .eq("stock_name", row["stock_name"]).eq("account_name", row["account_name"])\
                        .execute()
                    st.success(f"{row['stock_name']} → {tv} 저장"); st.rerun()
        else:
            st.write("모든 종목에 ticker 입력됨")

    # ── 계좌별 탭 ─────────────────────────────────────────────────
    accounts = ["전체"] + sorted(df["account_name"].unique().tolist())
    tabs = st.tabs(accounts)
    for tab, acct in zip(tabs, accounts):
        with tab:
            sub = df if acct == "전체" else df[df["account_name"] == acct]
            disp = sub[["stock_name","ticker","quantity","avg_price","cur_price",
                         "eval_amount","gain","return_pct","currency"]].copy()
            disp.columns = ["종목명","티커","수량","평균단가","현재가","평가금액(현재가)","손익","수익률(%)","통화"]
            disp["평균단가"] = disp.apply(
                lambda r: f"${r['평균단가']:,.2f}" if r["통화"]=="USD" else f"₩{r['평균단가']:,.0f}", axis=1)
            disp["현재가"] = disp.apply(
                lambda r: (f"${r['현재가']:,.2f}" if r["통화"]=="USD" else f"₩{r['현재가']:,.0f}")
                if r["현재가"] else "조회불가", axis=1)
            disp["평가금액(현재가)"] = disp["평가금액(현재가)"].apply(lambda v: f"₩{v:,.0f}")
            disp["손익"] = disp["손익"].apply(lambda v: f"₩{v:,.0f}")
            disp = disp.drop(columns=["통화"])
            st.dataframe(disp, use_container_width=True, hide_index=True)

    st.divider()

    # ── 계좌별 자산 비중 (현재가 기준 + 매입가 기준 나란히) ─────────
    st.subheader("계좌별 자산 비중")
    st.caption("*현재가 기준*은 yfinance 실시간 가격 반영  |  *매입가 기준*은 실제 투입 금액")

    acct_eval = df.groupby("account_name").agg(
        현재가기준=("eval_amount","sum"),
        매입가기준=("buy_amount","sum")
    ).reset_index()
    accts = acct_eval["account_name"].tolist()
    colors = _color_seq(accts)

    col_e, col_b = st.columns(2)
    with col_e:
        fig_e = px.pie(acct_eval, values="현재가기준", names="account_name",
                       hole=0.42, title="현재가 평가기준",
                       color="account_name",
                       color_discrete_map=ACCT_COLORS)
        fig_e.update_traces(texttemplate="%{label}<br>%{percent:.1%}")
        fig_e.update_layout(height=320, margin=dict(t=40,b=0), showlegend=False)
        st.plotly_chart(fig_e, use_container_width=True)
        # 수치 표
        tbl_e = acct_eval[["account_name","현재가기준"]].copy()
        tbl_e["비중(%)"] = (tbl_e["현재가기준"]/tbl_e["현재가기준"].sum()*100).round(1)
        tbl_e["현재가기준"] = tbl_e["현재가기준"].apply(fmt_won)
        st.dataframe(tbl_e.rename(columns={"account_name":"계좌","현재가기준":"금액"}),
                     use_container_width=True, hide_index=True)

    with col_b:
        fig_b = px.pie(acct_eval, values="매입가기준", names="account_name",
                       hole=0.42, title="매입가 기준 (실투입금액)",
                       color="account_name",
                       color_discrete_map=ACCT_COLORS)
        fig_b.update_traces(texttemplate="%{label}<br>%{percent:.1%}")
        fig_b.update_layout(height=320, margin=dict(t=40,b=0), showlegend=False)
        st.plotly_chart(fig_b, use_container_width=True)
        tbl_b = acct_eval[["account_name","매입가기준"]].copy()
        tbl_b["비중(%)"] = (tbl_b["매입가기준"]/tbl_b["매입가기준"].sum()*100).round(1)
        tbl_b["매입가기준"] = tbl_b["매입가기준"].apply(fmt_won)
        st.dataframe(tbl_b.rename(columns={"account_name":"계좌","매입가기준":"금액"}),
                     use_container_width=True, hide_index=True)

    st.divider()

    # ── 종목별 비중 + 수익률 (현재가 기준 선택) ───────────────────
    basis_opt = st.radio("종목 차트 기준", ["현재가 평가기준", "매입가 기준"], horizontal=True, key="basis_stock")
    val_col = "eval_amount" if basis_opt == "현재가 평가기준" else "buy_amount"

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("종목별 비중 (상위 20)")
        top20 = df.nlargest(20, val_col)
        fig3 = go.Figure(go.Pie(
            labels=top20["stock_name"],
            values=top20[val_col],
            hole=0.4,
            textinfo="label+percent",
            textposition="auto"
        ))
        fig3.update_layout(height=380, margin=dict(t=10,b=0), showlegend=False)
        st.plotly_chart(fig3, use_container_width=True)

    with col2:
        st.subheader("종목별 수익률 (손익 상위10 + 하위5)")
        df_ret = df[df["cur_price"].notna()].copy()
        if not df_ret.empty:
            top10 = df_ret.nlargest(10, "gain")
            bot5  = df_ret.nsmallest(5, "gain")
            df_show = pd.concat([top10, bot5]).drop_duplicates().sort_values("return_pct")
            fig4 = px.bar(df_show, y="stock_name", x="return_pct", orientation="h",
                          color="return_pct", color_continuous_scale="RdYlGn",
                          labels={"return_pct":"수익률(%)","stock_name":""})
            fig4.update_layout(height=380, margin=dict(t=10,b=0), coloraxis_showscale=False)
            st.plotly_chart(fig4, use_container_width=True)
            no_cnt = df["cur_price"].isna().sum()
            if no_cnt:
                st.caption(f"현재가 없는 종목 {no_cnt}개 제외")
        else:
            st.info("현재가 조회 가능한 종목 없음")
