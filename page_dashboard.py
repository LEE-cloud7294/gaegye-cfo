import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from utils import (load_assets, load_income, load_insurance, load_asset_history,
                   get_usd_krw, get_prices_bulk, calc_net_worth,
                   INCOME_TYPES, ACCT_COLORS, fmt_short, fmt_won)

_NON_STOCK_TICKER = {"RI9010000001", "KR103502GD64"}
_NON_STOCK_NAME   = {"현금자산"}
YOC_THRESHOLD = 1.5


def render():
    st.title("대시보드")

    df_assets_all = load_assets()
    df_income     = load_income()
    usd_krw       = get_usd_krw()
    today         = date.today()

    if df_assets_all.empty and df_income.empty:
        st.info("데이터가 없습니다. 데이터 관리에서 파일을 업로드하세요.")
        return

    # 주식/ETF vs 현금/채권 분리
    df_assets = df_assets_all[
        ~(df_assets_all["ticker"].isin(_NON_STOCK_TICKER) |
          df_assets_all["stock_name"].isin(_NON_STOCK_NAME))
    ].copy()
    df_cash_bonds = df_assets_all[
        df_assets_all["ticker"].isin(_NON_STOCK_TICKER) |
        df_assets_all["stock_name"].isin(_NON_STOCK_NAME)
    ].copy()

    # 현재가 조회 (30분 캐시)
    tickers = tuple(df_assets.dropna(subset=["ticker"])["ticker"].unique()) if not df_assets.empty else ()
    with st.spinner("현재가 조회 중..."):
        try:
            prices = get_prices_bulk(tickers)
        except Exception:
            prices = {}
            st.info("현재가 조회 일시 실패 — 매입가 기준으로 표시. 30분 후 자동 갱신됩니다.")

    # ── 평가금액 계산 ──────────────────────────────────────────
    if not df_assets.empty:
        def _eval(r):
            if r["currency"] == "USD" and r["ticker"] and r["ticker"] in prices:
                return r["quantity"] * prices[r["ticker"]] * usd_krw
            if r["currency"] == "KRW" and r["ticker"] and r["ticker"] in prices:
                return r["quantity"] * prices[r["ticker"]]
            return r["quantity"] * r["avg_price"] * (usd_krw if r["currency"] == "USD" else 1)

        df_assets["eval_amount"] = df_assets.apply(_eval, axis=1)
        df_assets["buy_amount"]  = df_assets.apply(
            lambda r: r["quantity"] * r["avg_price"] * (usd_krw if r["currency"] == "USD" else 1), axis=1)
        eval_total = float(df_assets["eval_amount"].sum())
        buy_total  = float(df_assets["buy_amount"].sum())   # 투입원금 (Cost Basis)
    else:
        eval_total = buy_total = 0.0

    # 현금/채권 평가금액
    cash_val = 0.0
    if not df_cash_bonds.empty:
        cash_val = float((df_cash_bonds["quantity"] * df_cash_bonds["avg_price"]).sum())

    # ── 보험 해약환급금 ──────────────────────────────────────
    df_ins = load_insurance()
    nw = calc_net_worth(df_assets_all, prices, usd_krw, df_ins)
    insurance_val = nw["insurance"]
    net_asset = eval_total + insurance_val

    # ── 수입/배당 지표 전처리 ────────────────────────────────
    annual_income = prev_annual = cumul_income = 0.0
    ref_year = today.year
    net_cash_in = 0.0
    first_invest_date = None
    df_iw = pd.DataFrame()   # income working copy

    if not df_income.empty:
        df_iw = df_income.copy()
        df_iw["net_amount_krw"] = pd.to_numeric(df_iw["net_amount_krw"], errors="coerce").fillna(0)
        df_iw["amount_krw"]     = pd.to_numeric(df_iw["amount_krw"],     errors="coerce").fillna(0)
        df_iw["ym"] = df_iw["date"].dt.to_period("M").astype(str)

        df_inc_f = df_iw[df_iw["income_type"].isin(INCOME_TYPES)]
        if not df_inc_f.empty:
            ref_year      = int(df_inc_f["date"].dt.year.max())
            annual_income = float(df_inc_f[df_inc_f["date"].dt.year == ref_year]["net_amount_krw"].sum())
            prev_annual   = float(df_inc_f[df_inc_f["date"].dt.year == ref_year - 1]["net_amount_krw"].sum())
            cumul_income  = float(df_inc_f["net_amount_krw"].sum())

        invest_df = df_iw[df_iw["income_type"] == "신규투자"]
        net_cash_in = float(invest_df["amount_krw"].sum())
        if not invest_df.empty:
            first_invest_date = invest_df["date"].min()

    # ── 수익률 지표 ──────────────────────────────────────────
    capital_gain_pct     = (eval_total / buy_total - 1) * 100 if buy_total else 0.0
    dividend_contrib_pct = cumul_income / buy_total * 100 if buy_total else 0.0
    total_return_pct     = capital_gain_pct + dividend_contrib_pct
    delta_div = f"{(annual_income - prev_annual) / prev_annual * 100:+.1f}%" if prev_annual else None

    st.caption(f"USD/KRW {usd_krw:,.0f}  |  현재가 조회 {len(prices)}/{len(tickers)}종목  |  기준일 {today}")

    # ══ 4탭 구조 ══════════════════════════════════════════════
    tab_sum, tab_asset, tab_div, tab_cf = st.tabs(["📊 요약", "🏦 자산분석", "💰 배당분석", "📈 현금흐름"])

    # ──────────────────────────────────────────────────────────
    # TAB 1: 요약
    # ──────────────────────────────────────────────────────────
    with tab_sum:
        st.markdown("### 핵심 지표")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("순자산 (현재가)", fmt_short(eval_total),
                  help="주식 평가금액 합계 (yfinance 현재가)")
        c2.metric(f"{ref_year}년 배당/이자", fmt_short(annual_income), delta=delta_div,
                  help=f"전년({ref_year-1}년) 대비 증감")
        c3.metric("보험포함 순자산", fmt_short(net_asset),
                  help="주식 평가금액 + 보험 해약환급금")
        c4.metric("토탈리턴", f"{total_return_pct:+.1f}%",
                  help="자본이득률 + 배당기여률 합산")

        st.divider()
        st.markdown("### 자본 지표")
        st.caption("투입원금과 누적순현금투입은 서로 다른 질문에 답하는 지표이므로 절대 합산하지 않습니다.")
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("투입원금 (Cost Basis)", fmt_short(buy_total),
                   help="보유주식 수량 × 평균단가 (증권사 확정값, 수익률 계산 분모)")
        cc2.metric("누적 순현금투입", fmt_short(net_cash_in),
                   help="실제 외부 입금 누계 (계좌이체 제외 | 2021년~ 데이터 기준)")
        reinvest = max(buy_total - net_cash_in, 0.0)
        cc3.metric("배당재투자·복리효과", fmt_short(reinvest),
                   help="투입원금 − 누적순현금투입 = 내 돈 없이 굴려서 키운 원금")

        st.divider()
        st.markdown("### 수익률 분해")
        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("자본이득률", f"{capital_gain_pct:+.1f}%",
                   delta=fmt_short(eval_total - buy_total),
                   help="(현재가 − 투입원금) / 투입원금")
        rc2.metric("배당기여률", f"{dividend_contrib_pct:+.1f}%",
                   delta=fmt_short(cumul_income),
                   help="2021년 이후 누적 배당/이자 합계 ÷ 현재 투입원금 (시간축이 다른 참고 지표)")
        rc3.metric("토탈리턴", f"{total_return_pct:+.1f}%",
                   help="자본이득률 + 배당기여률")

        st.divider()
        st.markdown("### 목표 대비 진행률")
        goal_c1, goal_c2 = st.columns([1, 3])
        goal = goal_c1.number_input("목표 순자산 (억원)", value=10.0, step=0.5, key="goal_nw") * 1e8
        if goal > 0:
            progress = min(eval_total / goal, 1.0)
            goal_c2.markdown(f"**달성: {progress*100:.1f}%** ({fmt_short(eval_total)} / {fmt_short(goal)})")
            goal_c2.progress(progress)

            if first_invest_date is not None:
                years_elapsed = (pd.Timestamp(today) - first_invest_date).days / 365.25
                if years_elapsed > 0.5 and buy_total > 0:
                    cagr = ((eval_total / buy_total) ** (1 / years_elapsed) - 1) * 100
                    goal_c1.metric("연복리수익률 (CAGR)", f"{cagr:.1f}%",
                                   help=f"투입원금 기준 {years_elapsed:.1f}년 연환산")
                    goal_c2.caption("※ 2021년 이후 거래내역 기준. 이전 투자분 포함 시 실제 CAGR은 낮을 수 있음")

        st.divider()
        st.markdown("### 자산 변화 추이")
        df_ah = load_asset_history()
        if df_ah.empty or df_ah["snapshot_date"].nunique() <= 1:
            st.info("업로드를 누적하면 자산 변화 추이가 표시됩니다.")
        else:
            pivot = df_ah.pivot_table(
                index="snapshot_date", columns="account_name", values="total_buy_krw", aggfunc="sum"
            ).fillna(0).reset_index()
            acct_cols = [c for c in pivot.columns if c != "snapshot_date"]
            fig_ah = go.Figure()
            for acct in acct_cols:
                fig_ah.add_trace(go.Scatter(
                    x=pivot["snapshot_date"], y=pivot[acct],
                    name=acct, stackgroup="one", fill="tonexty",
                    line=dict(color=ACCT_COLORS.get(acct, "#999999")),
                ))
            fig_ah.update_layout(height=300, margin=dict(t=10, b=0),
                                 yaxis_title="원", legend=dict(orientation="h"))
            st.plotly_chart(fig_ah, use_container_width=True)

    # ──────────────────────────────────────────────────────────
    # TAB 2: 자산분석
    # ──────────────────────────────────────────────────────────
    with tab_asset:
        if not df_assets.empty:
            st.markdown("### 계좌별 자산 비중")
            acct_grp = df_assets.groupby("account_name").agg(
                현재가기준=("eval_amount", "sum"),
                매입가기준=("buy_amount",  "sum")
            ).reset_index()

            col1, col2 = st.columns(2)

            def _pie(col, val_col, title):
                with col:
                    st.caption(title)
                    fig = px.pie(acct_grp, values=val_col, names="account_name",
                                 hole=0.42, color="account_name",
                                 color_discrete_map=ACCT_COLORS)
                    fig.update_traces(texttemplate="%{label}<br>%{percent:.1%}", textfont_size=11)
                    fig.update_layout(height=300, margin=dict(t=10, b=0), showlegend=True,
                                      legend=dict(orientation="h", y=-0.1))
                    col.plotly_chart(fig, use_container_width=True)
                    t = acct_grp[["account_name", val_col]].copy()
                    t["비중(%)"] = (t[val_col] / t[val_col].sum() * 100).round(1)
                    t[val_col]  = t[val_col].apply(fmt_won)
                    t.columns   = ["계좌", "금액", "비중(%)"]
                    col.dataframe(t, use_container_width=True, hide_index=True)

            _pie(col1, "현재가기준", "📌 현재가 평가기준 (yfinance)")
            _pie(col2, "매입가기준", "📌 매입가 기준 (실제 투입금액)")

            st.divider()
            st.markdown("### 자산배분 분석")
            ab_c1, ab_c2 = st.columns(2)

            with ab_c1:
                st.caption("국내 vs 해외 (market 기준)")
                if "market" in df_assets.columns and df_assets["market"].notna().any():
                    region_grp = (df_assets.groupby(df_assets["market"].fillna("기타"))["eval_amount"]
                                  .sum().reset_index())
                    region_grp.columns = ["지역", "금액"]
                else:
                    # market 컬럼 없을 때 currency fallback
                    region_grp = pd.DataFrame({
                        "지역": ["국내", "해외"],
                        "금액": [
                            float(df_assets[df_assets["currency"] == "KRW"]["eval_amount"].sum()),
                            float(df_assets[df_assets["currency"] == "USD"]["eval_amount"].sum()),
                        ]
                    })
                region_grp = region_grp[region_grp["금액"] > 0]
                _color_map_r = {r: c for r, c in zip(
                    region_grp["지역"], ["#4C72B0", "#DD8452", "#55A868", "#C44E52"])}
                fig_r = px.pie(region_grp, values="금액", names="지역", hole=0.45,
                               color_discrete_map=_color_map_r)
                fig_r.update_traces(texttemplate="%{label}<br>%{percent:.1%}")
                fig_r.update_layout(height=260, margin=dict(t=0, b=0), showlegend=True)
                st.plotly_chart(fig_r, use_container_width=True)

            with ab_c2:
                st.caption("자산군별")
                asset_class = pd.DataFrame({
                    "자산군": ["주식/ETF", "현금/채권", "보험"],
                    "금액":   [eval_total, cash_val, insurance_val]
                })
                asset_class = asset_class[asset_class["금액"] > 0]
                fig_ac = px.pie(asset_class, values="금액", names="자산군", hole=0.45,
                                color_discrete_map={
                                    "주식/ETF":  "#4C72B0",
                                    "현금/채권": "#55A868",
                                    "보험":      "#8172B2"
                                })
                fig_ac.update_traces(texttemplate="%{label}<br>%{percent:.1%}")
                fig_ac.update_layout(height=260, margin=dict(t=0, b=0), showlegend=True)
                st.plotly_chart(fig_ac, use_container_width=True)
        else:
            st.info("자산 데이터 없음 — 데이터 관리에서 잔고 파일을 업로드하세요.")

    # ──────────────────────────────────────────────────────────
    # TAB 3: 배당분석
    # ──────────────────────────────────────────────────────────
    with tab_div:
        if not df_assets.empty and not df_income.empty:
            st.markdown("### 배당주 / 성장주 분류")
            st.caption(f"분류 기준: 최근 1년 YOC ≥ {YOC_THRESHOLD}% → 배당주 / 미만 또는 배당 없음 → 성장주")

            one_yr = df_income["date"].max() - pd.Timedelta(days=365)
            df_div_yr = df_income[
                (df_income["income_type"].isin({"배당_국내", "배당_해외"})) &
                (df_income["date"] >= one_yr)
            ].copy()
            df_div_yr["net_amount_krw"] = pd.to_numeric(
                df_div_yr["net_amount_krw"], errors="coerce").fillna(0)
            stock_div = df_div_yr.groupby("stock_name")["net_amount_krw"].sum().to_dict()

            df_yoc = df_assets.copy()
            df_yoc["annual_div"] = df_yoc["stock_name"].map(stock_div).fillna(0)
            df_yoc["yoc"] = (
                df_yoc["annual_div"] / df_yoc["buy_amount"].replace(0, float("nan")) * 100
            ).fillna(0)
            df_yoc["분류"] = df_yoc["yoc"].apply(lambda v: "배당주" if v >= YOC_THRESHOLD else "성장주")

            acct_opts = ["전체"] + sorted(df_yoc["account_name"].unique().tolist())
            sel_acct = st.selectbox("계좌 필터", acct_opts, key="dg_dash")
            sub = df_yoc if sel_acct == "전체" else df_yoc[df_yoc["account_name"] == sel_acct]

            dg_col1, dg_col2 = st.columns([1, 2])
            with dg_col1:
                grp = sub.groupby("분류")["eval_amount"].sum().reset_index()
                grp["비중(%)"] = (grp["eval_amount"] / grp["eval_amount"].sum() * 100).round(1)
                fig_dg = px.pie(grp, values="eval_amount", names="분류", hole=0.45,
                                color_discrete_map={"배당주": "#55A868", "성장주": "#DD8452"})
                fig_dg.update_traces(texttemplate="%{label}<br>%{percent:.1%}")
                fig_dg.update_layout(height=280, margin=dict(t=10, b=0), showlegend=False)
                st.plotly_chart(fig_dg, use_container_width=True)
                st.dataframe(
                    grp[["분류", "비중(%)"]].assign(금액=grp["eval_amount"].apply(fmt_won))[["분류", "금액", "비중(%)"]],
                    use_container_width=True, hide_index=True)

            with dg_col2:
                tbl = sub[["분류", "account_name", "stock_name", "eval_amount", "yoc"]]\
                    .sort_values(["분류", "yoc"], ascending=[True, False]).copy()
                tbl["평가금액"] = tbl["eval_amount"].apply(fmt_won)
                tbl["YOC(%)"]  = tbl["yoc"].apply(lambda v: f"{v:.2f}%")
                tbl = tbl.rename(columns={"account_name": "계좌", "stock_name": "종목명"})
                st.dataframe(tbl[["분류", "계좌", "종목명", "평가금액", "YOC(%)"]],
                             use_container_width=True, hide_index=True, height=280)

        st.divider()

        if not df_iw.empty:
            df_inc2 = df_iw[df_iw["income_type"].isin(INCOME_TYPES)].copy()
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.subheader("월별 배당/이자 (최근 18개월)")
                monthly = df_inc2.groupby("ym")["net_amount_krw"].sum().reset_index().sort_values("ym").tail(18)
                fig_m = px.bar(monthly, x="ym", y="net_amount_krw",
                               color_discrete_sequence=["#4C72B0"],
                               labels={"ym": "", "net_amount_krw": "원"})
                fig_m.update_layout(height=260, margin=dict(t=10, b=0))
                st.plotly_chart(fig_m, use_container_width=True)

            with col_c2:
                st.subheader("연도별 배당/이자")
                yr = df_inc2.groupby(df_inc2["date"].dt.year)["net_amount_krw"].sum().reset_index()
                yr.columns = ["연도", "합계"]
                fig_yr = px.bar(yr, x="연도", y="합계", text_auto=True,
                                color_discrete_sequence=["#55A868"],
                                labels={"합계": "원", "연도": ""})
                fig_yr.update_traces(texttemplate="%{y:,.0f}", textposition="outside")
                fig_yr.update_layout(height=260, margin=dict(t=10, b=0))
                st.plotly_chart(fig_yr, use_container_width=True)
        else:
            st.info("수입 데이터 없음")

    # ──────────────────────────────────────────────────────────
    # TAB 4: 현금흐름
    # ──────────────────────────────────────────────────────────
    with tab_cf:
        if not df_iw.empty:
            st.markdown("### 현금흐름 지표")
            fire_c1, fire_c2, fire_c3 = st.columns(3)

            monthly_div_avg = annual_income / 12 if annual_income else 0.0
            invest_months = max(
                df_iw[df_iw["income_type"] == "신규투자"]["date"].dt.to_period("M").nunique(), 1)
            monthly_invest_avg = net_cash_in / invest_months

            fire_c1.metric("월평균 배당/이자", fmt_short(monthly_div_avg),
                           help=f"{ref_year}년 기준 월평균")
            fire_c2.metric("월평균 신규투입", fmt_short(monthly_invest_avg),
                           help="누적 신규투자 ÷ 투자 월수")

            monthly_expense = fire_c3.number_input(
                "월 생활비 (만원)", value=300, step=10, key="fire_exp") * 10000
            fire_ratio = monthly_div_avg / monthly_expense * 100 if monthly_expense else 0.0
            fire_c3.metric("배당 생활비 커버율 (FIRE)", f"{fire_ratio:.1f}%",
                           help="월 평균 배당 / 월 생활비 × 100")

        else:
            st.info("수입 데이터 없음")
