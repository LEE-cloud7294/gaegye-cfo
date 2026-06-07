import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date
from utils import load_assets, load_income, get_usd_krw, INCOME_TYPES

MONTHS_KO = {i: f"{i}월" for i in range(1, 13)}


def _fmt_krw(v) -> str:
    if v is None or pd.isna(v) or v == 0:
        return "-"
    return f"₩{int(v):,}"


def _fmt_usd(v) -> str:
    if v is None or pd.isna(v) or v == 0:
        return "-"
    return f"${v:,.2f}"


def render():
    st.title("배당 / 이자")

    df_all = load_income()
    if df_all.empty:
        st.info("데이터 없음 — 데이터 관리에서 거래내역을 업로드하세요.")
        return

    df_inc = df_all[df_all["income_type"].isin(INCOME_TYPES)].copy()
    if df_inc.empty:
        st.warning("배당/이자 데이터 없음")
        st.caption(f"DB 거래 종류: {', '.join(df_all['income_type'].value_counts().index.tolist())}")
        return

    for col in ["net_amount_krw","amount_krw","amount_usd","tax_krw"]:
        df_inc[col] = pd.to_numeric(df_inc[col], errors="coerce").fillna(0)

    df_inc["year"]  = df_inc["date"].dt.year
    df_inc["month"] = df_inc["date"].dt.month
    df_inc["ym"]    = df_inc["date"].dt.to_period("M").astype(str)

    usd_krw   = get_usd_krw()
    max_year  = int(df_inc["year"].max())
    max_month = int(df_inc[df_inc["year"] == max_year]["month"].max())

    yearly      = float(df_inc[df_inc["year"] == max_year]["net_amount_krw"].sum())
    this_m      = float(df_inc[(df_inc["year"] == max_year) & (df_inc["month"] == max_month)]["net_amount_krw"].sum())
    monthly_avg = yearly / max_month if max_month else 0

    df_assets = load_assets()
    yoc = 0.0
    if not df_assets.empty:
        buy = float((df_assets["quantity"] * df_assets["avg_price"] *
                     df_assets["currency"].map(lambda c: usd_krw if c == "USD" else 1)).sum())
        # YOC: 최근 1년 배당 기준 (page_dashboard와 동일 기준)
        one_yr_ago = df_inc["date"].max() - pd.Timedelta(days=365)
        div_1yr = float(df_inc[
            (df_inc["income_type"].isin({"배당_국내", "배당_해외"})) &
            (df_inc["date"] >= one_yr_ago)
        ]["net_amount_krw"].sum())
        yoc = div_1yr / buy * 100 if buy else 0

    # ── 지표 카드 ─────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{max_year}년 누적 배당/이자", f"₩{yearly:,.0f}")
    c2.metric(f"{max_year}년 {max_month}월", f"₩{this_m:,.0f}")
    c3.metric("월평균 배당/이자", f"₩{monthly_avg:,.0f}")
    c4.metric("전체 YOC", f"{yoc:.2f}%")

    st.divider()

    tab1, tab2 = st.tabs(["📅 캐시플로우", "📊 종목별 분석"])

    # ════════════════════════════════════════════════════════════
    # TAB 1: 캐시플로우
    # ════════════════════════════════════════════════════════════
    with tab1:
        # 이번달 / 전달 나란히
        st.subheader("최근 2개월 배당 내역")

        def month_detail(year, month):
            d = df_inc[(df_inc["year"] == year) & (df_inc["month"] == month)].copy()
            d = d.sort_values("net_amount_krw", ascending=False)
            return d

        # 전달 계산
        if max_month == 1:
            prev_y, prev_m = max_year - 1, 12
        else:
            prev_y, prev_m = max_year, max_month - 1

        mc1, mc2 = st.columns(2)
        for col, y, m, label in [
            (mc1, max_year, max_month, f"{max_year}년 {max_month}월 (최근)"),
            (mc2, prev_y, prev_m, f"{prev_y}년 {prev_m}월 (전월)"),
        ]:
            with col:
                dd = month_detail(y, m)
                total = float(dd["net_amount_krw"].sum())
                st.markdown(f"**{label}**  `₩{total:,.0f}`")
                if not dd.empty:
                    show = dd[["account_name","stock_name","income_type","net_amount_krw"]].copy()
                    show.columns = ["계좌","종목","유형","세후(원)"]
                    show["세후(원)"] = show["세후(원)"].apply(lambda v: f"₩{int(v):,}")
                    st.dataframe(show, use_container_width=True, hide_index=True,
                                 height=min(35 * len(show) + 38, 300))
                else:
                    st.info("데이터 없음")

        st.divider()

        # 연도별 성장
        st.subheader("연도별 배당/이자 성장")
        yr_sum = df_inc.groupby("year")["net_amount_krw"].sum().reset_index()
        yr_sum.columns = ["연도","세후합계"]
        fig_yr = px.bar(yr_sum, x="연도", y="세후합계", text_auto=True,
                        color_discrete_sequence=["#4C72B0"], labels={"세후합계":"원","연도":""})
        fig_yr.update_traces(texttemplate="%{y:,.0f}", textposition="outside")
        fig_yr.update_layout(height=240, margin=dict(t=20,b=0), yaxis_tickformat=",.0f")
        st.plotly_chart(fig_yr, use_container_width=True)

        # 월별 캐시플로우 (KRW / USD 전환)
        st.subheader("월별 배당/이자 캐시플로우")
        ccy = st.radio("통화", ["KRW (원화)", "USD (달러)"], horizontal=True, key="ccy_cf")
        use_usd = ccy == "USD (달러)"

        if use_usd:
            df_cf = df_inc[df_inc["income_type"].isin({"배당_해외"})].copy()
            df_cf["val"] = df_cf["amount_usd"]
            y_label = "달러(USD)"
        else:
            df_cf = df_inc.copy()
            df_cf["val"] = df_cf["net_amount_krw"]
            y_label = "원(KRW)"

        df_cf["val"] = pd.to_numeric(df_cf["val"], errors="coerce").fillna(0)
        cf_monthly = df_cf.groupby("ym")["val"].sum().reset_index().sort_values("ym").tail(24)
        fig_cf = px.bar(cf_monthly, x="ym", y="val",
                        labels={"ym":"","val":y_label},
                        color_discrete_sequence=["#4C72B0"])
        fig_cf.update_layout(height=260, margin=dict(t=10,b=0),
                             yaxis_tickformat=",.2f" if use_usd else ",.0f")
        st.plotly_chart(fig_cf, use_container_width=True)

        st.divider()

        # 월별 배당 현황 — 색상 히트맵 표
        st.subheader("월별 배당 현황 (연도×월)")
        st.caption("셀 색상: 진할수록 금액 높음 | 0원은 회색")

        all_years = sorted(df_inc["year"].unique())
        pivot = df_inc.groupby(["year","month"])["net_amount_krw"].sum().reset_index()
        full_idx = pd.MultiIndex.from_product([all_years, range(1,13)], names=["year","month"])
        pf = pivot.set_index(["year","month"]).reindex(full_idx, fill_value=0).reset_index()
        pw = pf.pivot(index="year", columns="month", values="net_amount_krw").fillna(0)
        pw.columns = [MONTHS_KO[m] for m in pw.columns]
        pw["연간합계"] = pw.sum(axis=1)
        pw.index.name = "연도"

        month_cols = [MONTHS_KO[m] for m in range(1, 13)]
        max_val = pw[month_cols].max().max()

        def _cell_color(v):
            if v <= 0:
                return "background-color:#f0f0f0; color:#aaa"
            intensity = min(v / max_val, 1.0)
            # 연한 초록(낮음) → 진한 초록(높음)
            g = int(180 - intensity * 120)
            b = int(200 - intensity * 160)
            return f"background-color:rgb(80,{g},{b}); color:white; font-weight:500"

        def _fmt_cell(v):
            if v <= 0:
                return "-"
            return f"₩{int(v):,}"

        # 숫자 → 표시용 포맷
        pw_disp = pw.copy()
        for c in pw_disp.columns:
            pw_disp[c] = pw_disp[c].apply(_fmt_cell)

        # 스타일은 원본 숫자 기준
        styled = pw.style.map(
            _cell_color,
            subset=month_cols
        ).format(_fmt_cell).set_table_styles([
            {"selector": "th", "props": [("background","#2c3e50"),("color","white"),
                                          ("font-size","12px"),("text-align","center")]},
            {"selector": "td", "props": [("text-align","right"),("font-size","12px"),
                                          ("padding","4px 8px"),("min-width","65px")]},
            {"selector": "th.row_heading", "props": [("min-width","50px"),("text-align","center")]},
        ])
        # 연간합계 열 강조
        styled = styled.map(
            lambda v: "background-color:#1a252f; color:#f9c74f; font-weight:bold",
            subset=["연간합계"]
        )

        st.dataframe(styled, use_container_width=True,
                     height=min(42*(len(all_years)+2), 520))

        st.divider()

        # 월 선택 상세
        st.subheader("월별 종목 상세")
        col_y2, col_m2, _ = st.columns([1,1,2])
        sel_y = col_y2.selectbox("연도", sorted(df_inc["year"].unique(), reverse=True), key="inc_y2")
        sel_m = col_m2.selectbox("월", sorted(df_inc[df_inc["year"]==sel_y]["month"].unique()),
                                  key="inc_m2", format_func=lambda m: f"{m}월")
        detail = df_inc[(df_inc["year"]==sel_y) & (df_inc["month"]==sel_m)].copy()
        if not detail.empty:
            detail = detail.sort_values("net_amount_krw", ascending=False)
            sh = detail[["date","account_name","stock_name","income_type",
                          "amount_krw","amount_usd","exchange_rate","tax_krw","net_amount_krw"]].copy()
            sh.columns = ["날짜","계좌","종목","유형","금액(원)","금액(USD)","환율","세금","세후(원)"]
            sh["날짜"] = sh["날짜"].dt.strftime("%Y-%m-%d")
            sh["금액(원)"]  = sh["금액(원)"].apply(lambda v: f"₩{int(v):,}" if v else "-")
            sh["세금"]      = sh["세금"].apply(lambda v: f"₩{int(v):,}" if v else "-")
            sh["세후(원)"]  = sh["세후(원)"].apply(lambda v: f"₩{int(v):,}" if v else "-")
            sh["금액(USD)"] = sh["금액(USD)"].apply(lambda v: f"${v:,.4f}" if v else "-")
            sh["환율"]      = sh["환율"].apply(lambda v: f"{v:,.1f}" if v else "-")
            st.dataframe(sh, use_container_width=True, hide_index=True)
            st.markdown(f"**{sel_y}년 {sel_m}월 합계: ₩{int(detail['net_amount_krw'].sum()):,}**")
        else:
            st.info("해당 월 데이터 없음")

    # ════════════════════════════════════════════════════════════
    # TAB 2: 종목별 분석
    # ════════════════════════════════════════════════════════════
    with tab2:
        df_assets = load_assets()   # 명시적 재선언 (스코프 명확화)
        st.subheader("종목별 배당 분석")
        ccy2 = st.radio("통화", ["KRW (원화)", "USD (달러)"], horizontal=True, key="ccy_stock")
        use_usd2 = ccy2 == "USD (달러)"

        # 종목별 배당 집계
        df_div = df_inc[df_inc["income_type"].isin({"배당_국내","배당_해외"})].copy()
        if df_div.empty:
            st.info("배당 데이터 없음")
        else:
            if use_usd2:
                df_div["val"] = pd.to_numeric(df_div["amount_usd"], errors="coerce").fillna(0)
            else:
                df_div["val"] = df_div["net_amount_krw"]

            agg = df_div.groupby(["stock_name","account_name","income_type"]).agg(
                total=("val","sum"),
                count=("val","count"),
            ).reset_index()

            # 티커 조인
            if not df_assets.empty:
                tmap = df_assets[["stock_name","ticker"]].drop_duplicates().set_index("stock_name")["ticker"].to_dict()
            else:
                tmap = {}
            agg["ticker"] = agg["stock_name"].map(tmap)

            # 보유수량 조인 (계좌별로 분리 — 동일 종목이라도 계좌마다 보유량이 다름)
            if not df_assets.empty:
                qmap = df_assets.groupby(["stock_name", "account_name"])["quantity"].sum().to_dict()
            else:
                qmap = {}
            agg["보유수량"] = agg.apply(
                lambda r: qmap.get((r["stock_name"], r["account_name"]), 0), axis=1)
            agg["주당배당(회당)"] = (agg["total"] / agg["count"] / agg["보유수량"].replace(0, float("nan"))).round(4)

            agg = agg.sort_values("total", ascending=False)
            disp = agg[["ticker","stock_name","account_name","income_type","total","count","보유수량","주당배당(회당)"]].copy()
            disp.columns = ["티커","종목명","계좌","유형","총배당","횟수","보유수량","주당배당(회당)"]
            unit = "USD" if use_usd2 else "원"
            disp["총배당"] = disp["총배당"].apply(lambda v: f"${v:,.2f}" if use_usd2 else f"₩{int(v):,}")
            disp["주당배당(회당)"] = disp["주당배당(회당)"].apply(
                lambda v: f"${v:,.4f}" if use_usd2 else f"₩{int(v):,}" if pd.notna(v) else "-")
            st.dataframe(disp, use_container_width=True, hide_index=True)

            # 종목별 누적 배당 바차트 (상위 15)
            top15 = agg.nlargest(15, "total")
            fig_s = px.bar(top15, x="stock_name", y="total",
                           color="income_type",
                           labels={"total":unit,"stock_name":"","income_type":"유형"},
                           color_discrete_sequence=px.colors.qualitative.Set2)
            fig_s.update_layout(height=300, margin=dict(t=10,b=0),
                                yaxis_tickformat=",.2f" if use_usd2 else ",.0f")
            st.plotly_chart(fig_s, use_container_width=True)

