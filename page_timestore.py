import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date
from db import get_client
from utils import load_family, load_assets, load_income, get_usd_krw, get_prices_bulk, INCOME_TYPES

DEFAULT_EVENTS = {
    "어린이집": 100,
    "초등입학": 200,
    "중학입학": 500,
    "고등입학": 800,
    "대학입학": 4000,
    "결혼":    5000,
}

RELATIONS = ["본인", "배우자", "자녀", "기타"]


def render():
    st.title("타임스톤")

    df_fam = load_family()

    # ── 가족 정보 관리 ────────────────────────────────────────────
    with st.expander("👨‍👩‍👧‍👦 가족 구성원 관리", expanded=df_fam.empty):
        with st.form("add_family"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("이름 *")
            rel = c2.selectbox("관계", RELATIONS)
            birth = c3.date_input("생년월일", value=date(1990, 1, 1))
            if st.form_submit_button("추가"):
                if not name:
                    st.error("이름을 입력하세요.")
                else:
                    try:
                        get_client().table("family_data").insert({
                            "name": name, "relation": rel, "birth_date": str(birth)
                        }).execute()
                        st.rerun()
                    except Exception as e:
                        st.error(f"오류: {e}")

        if not df_fam.empty:
            for _, row in df_fam.iterrows():
                today = date.today()
                birth = pd.to_datetime(row["birth_date"]).date()
                age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
                cc1, cc2 = st.columns([4, 1])
                cc1.write(f"**{row['name']}** ({row['relation']}) — {age}세 (생년: {birth.year}년)")
                if cc2.button("삭제", key=f"del_fam_{row['id']}"):
                    get_client().table("family_data").delete().eq("id", row["id"]).execute()
                    st.rerun()

    if df_fam.empty:
        st.info("가족 구성원을 먼저 등록하세요.")
        return

    st.divider()

    # ── 가족 현황 카드 ────────────────────────────────────────────
    today = date.today()
    cols = st.columns(len(df_fam))
    for col, (_, row) in zip(cols, df_fam.iterrows()):
        birth = pd.to_datetime(row["birth_date"]).date()
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        col.metric(f"{row['relation']} {row['name']}", f"{age}세")

    st.divider()

    # ── 이벤트 비용 설정 ──────────────────────────────────────────
    st.subheader("이벤트 예상 비용 설정 (만원)")
    event_costs = {}
    cols_ev = st.columns(len(DEFAULT_EVENTS))
    for col, (ev, default) in zip(cols_ev, DEFAULT_EVENTS.items()):
        event_costs[ev] = col.number_input(ev, value=default, step=100, key=f"ev_{ev}") * 10000

    # ── 자산 시뮬레이션 입력 ──────────────────────────────────────
    st.subheader("자산 시뮬레이션")
    df_assets = load_assets()
    usd_krw = get_usd_krw()
    if not df_assets.empty:
        _tickers = tuple(df_assets.dropna(subset=["ticker"])["ticker"].unique())
        _prices  = get_prices_bulk(_tickers) if _tickers else {}
        def _eval_ts(r):
            if r["currency"] == "USD" and r.get("ticker") and r["ticker"] in _prices:
                return r["quantity"] * _prices[r["ticker"]] * usd_krw
            if r["currency"] == "KRW" and r.get("ticker") and r["ticker"] in _prices:
                return r["quantity"] * _prices[r["ticker"]]
            return r["quantity"] * r["avg_price"] * (usd_krw if r["currency"] == "USD" else 1)
        cur_asset = float(df_assets.apply(_eval_ts, axis=1).sum())
    else:
        cur_asset = 0.0

    c1, c2, c3 = st.columns(3)
    cur_asset_input = c1.number_input("현재 자산 (원)", value=int(cur_asset), step=1000000)
    monthly_invest = c2.number_input("월 투자금 (원)", value=1000000, step=100000)
    annual_rate = c3.number_input("예상 연 수익률 (%)", value=7.0, step=0.5) / 100

    # ── 연도별 이벤트 + 자산 대조 테이블 ─────────────────────────
    st.subheader("연도별 타임라인")

    # 자녀 이벤트 생성
    rows = []
    child_members = df_fam[df_fam["relation"] == "자녀"]
    year_range = range(today.year, today.year + 30)

    # 연도별 예상 자산 계산 (복리)
    asset_by_year = {}
    asset = cur_asset_input
    for yr in year_range:
        asset = asset * (1 + annual_rate) + monthly_invest * 12
        asset_by_year[yr] = asset

    # 연도별 이벤트
    events_by_year = {}
    for _, member in child_members.iterrows():
        birth_year = pd.to_datetime(member["birth_date"]).year
        milestones = {
            "어린이집": birth_year + 3,
            "초등입학": birth_year + 8,
            "중학입학": birth_year + 14,
            "고등입학": birth_year + 17,
            "대학입학": birth_year + 20,
        }
        for ev_name, ev_year in milestones.items():
            if ev_year in asset_by_year:
                events_by_year.setdefault(ev_year, []).append(
                    (member["name"], ev_name, event_costs.get(ev_name, 0))
                )

    # 본인 이벤트
    self_member = df_fam[df_fam["relation"] == "본인"]
    if not self_member.empty:
        self_birth = pd.to_datetime(self_member.iloc[0]["birth_date"]).year
        retire_year = self_birth + 60
        if retire_year in asset_by_year:
            events_by_year.setdefault(retire_year, []).append(("본인", "은퇴목표", 0))

    table_rows = []
    df_inc = load_income()   # 루프 밖에서 1회 호출
    for yr in sorted(events_by_year.keys()):
        for name, ev, cost in events_by_year[yr]:
            projected = asset_by_year.get(yr, 0)
            # 월배당 추정 (연간 배당 / 12)
            if not df_inc.empty:
                df_div = df_inc[df_inc["income_type"].isin(INCOME_TYPES)]
                last_year_div = df_div[df_div["date"].dt.year == today.year - 1]["net_amount_krw"].sum()
                grow_years = yr - today.year
                monthly_div_est = (last_year_div * (1.05 ** grow_years)) / 12
            else:
                monthly_div_est = 0

            ok = "✅" if (cost == 0 or projected > cost) else "⚠️"
            table_rows.append({
                "연도": yr,
                "이름": name,
                "이벤트": ev,
                "예상비용": f"₩{cost:,.0f}" if cost else "-",
                "예상자산": f"₩{projected:,.0f}",
                "월배당예상": f"₩{monthly_div_est:,.0f}",
                "여유": ok,
            })

    if table_rows:
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    else:
        st.info("자녀 정보를 추가하면 이벤트 타임라인이 생성됩니다.")

    # ── 자산 성장 시뮬레이션 차트 ─────────────────────────────────
    st.subheader("자산 성장 시뮬레이션")
    sim_years = list(range(today.year, today.year + 25))
    sim_assets = [asset_by_year.get(y, 0) for y in sim_years]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sim_years, y=sim_assets, name="예상 자산",
                             fill="tozeroy", line=dict(color="#4C72B0")))

    # 이벤트 마커
    for yr, evs in events_by_year.items():
        if yr in asset_by_year:
            ev_labels = ", ".join([f"{n} {e}" for n, e, _ in evs])
            fig.add_vline(x=yr, line_dash="dot", line_color="orange",
                          annotation_text=ev_labels, annotation_position="top")

    fig.update_layout(height=320, margin=dict(t=30, b=0),
                      yaxis_title="원", xaxis_title="연도")
    st.plotly_chart(fig, use_container_width=True)
