import streamlit as st
import pandas as pd
from db import get_client
from utils import _fetch_all, get_usd_krw
from parser_income import parse_income_a, parse_income_b
from parser_assets import parse_assets_domestic, parse_assets_overseas, parse_assets_irp

st.set_page_config(
    page_title="가족 자산 관리 시스템",
    page_icon="💼",
    layout="wide",
)

# ── 비밀번호 인증 ─────────────────────────────────────────────
_APP_PW = st.secrets.get("app", {}).get("password", "")
if _APP_PW:
    if not st.session_state.get("authenticated"):
        st.title("💼 가족 CFO")
        pw = st.text_input("비밀번호", type="password", key="login_pw")
        if st.button("입력"):
            if pw == _APP_PW:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        st.stop()

PAGES = [
    "대시보드",
    "자산 현황",
    "배당 / 이자",
    "타임스톤",
    "보험 관리",
    "투자 메모",
    "데이터 관리",
    "AI 재무 컨설팅",
]

with st.sidebar:
    st.title("💼 가족 CFO")
    page = st.radio("메뉴", PAGES, label_visibility="collapsed")

try:
    supabase = get_client()
except Exception as e:
    st.error(f"Supabase 연결 실패: {e}")
    st.stop()

# ── 라우팅 ───────────────────────────────────────────────────────
if page == "대시보드":
    from page_dashboard import render; render()

elif page == "자산 현황":
    from page_assets import render; render()

elif page == "배당 / 이자":
    from page_income import render; render()

elif page == "타임스톤":
    from page_timestore import render; render()

elif page == "보험 관리":
    from page_insurance import render; render()

elif page == "투자 메모":
    from page_memo import render; render()

elif page == "AI 재무 컨설팅":
    from page_ai import render; render()

elif page == "데이터 관리":
    st.title("데이터 관리 (업로드)")
    tab1, tab2 = st.tabs(["자산현황 업로드", "거래내역 업로드"])

    # ── 탭1: 자산현황 ─────────────────────────────────────────────
    with tab1:
        st.subheader("자산현황 파일 업로드")

        # 최근 업로드 현황
        with st.container(border=True):
            st.caption("📋 계좌별 최근 업로드 현황")
            rows = _fetch_all("assets_snapshot")
            if rows:
                df_up = pd.DataFrame(rows)
                df_up["uploaded_at"] = pd.to_datetime(df_up["uploaded_at"])
                latest = (df_up.groupby("account_name")["uploaded_at"]
                          .max().reset_index()
                          .rename(columns={"uploaded_at": "최근 업로드", "account_name": "계좌"}))
                latest["최근 업로드"] = latest["최근 업로드"].dt.strftime("%Y-%m-%d %H:%M")
                st.dataframe(latest, use_container_width=True, hide_index=True)
            else:
                st.write("업로드 이력 없음")

        asset_account = st.selectbox(
            "계좌 선택",
            ["일반주식_국내", "일반주식_해외", "ISA", "IRP", "연금저축"],
            key="asset_acct",
        )
        asset_file = st.file_uploader("xlsx 파일 선택", type=["xlsx", "xls"], key="asset_file")

        if asset_file:
            if st.button("파일 파싱", key="parse_asset"):
                try:
                    if asset_account == "일반주식_해외":
                        records = parse_assets_overseas(asset_file, account_name="일반주식_해외")
                    elif asset_account == "IRP":
                        records = parse_assets_irp(asset_file, account_name="IRP")
                    else:
                        records = parse_assets_domestic(asset_file, account_name=asset_account)
                    st.session_state["asset_records"] = records
                    st.session_state["asset_account_sel"] = asset_account
                except Exception as e:
                    st.error(f"파싱 오류: {e}")

        if st.session_state.get("asset_records"):
            records = st.session_state["asset_records"]
            st.write(f"**{len(records)}개 종목** 파싱 완료")
            st.dataframe(pd.DataFrame(records), use_container_width=True)

            if st.button("✅ DB 저장 (기존 데이터 덮어쓰기)", key="save_asset"):
                acct = st.session_state["asset_account_sel"]
                try:
                    supabase.table("assets_snapshot").delete().eq("account_name", acct).execute()
                    supabase.table("assets_snapshot").insert(records).execute()

                    # asset_history 자동 저장 (매입가 기준 합산)
                    from datetime import date as _date
                    usd_krw = get_usd_krw()
                    total_buy = 0.0
                    for r in records:
                        val = float(r["quantity"]) * float(r["avg_price"])
                        if r.get("currency") == "USD":
                            val *= usd_krw
                        total_buy += val
                    history_row = {
                        "snapshot_date": str(_date.today()),
                        "account_name": acct,
                        "total_buy_krw": round(total_buy),
                        "total_eval_krw": round(total_buy),
                    }
                    supabase.table("asset_history").upsert(
                        history_row, on_conflict="snapshot_date,account_name"
                    ).execute()

                    st.success(f"{acct} — {len(records)}개 종목 저장 완료")
                    del st.session_state["asset_records"]
                    st.rerun()
                except Exception as e:
                    st.error(f"저장 오류: {e}")

    # ── 탭2: 거래내역 ─────────────────────────────────────────────
    with tab2:
        st.subheader("거래내역 파일 업로드")

        # 최근 업로드 현황 (계좌별 최신 거래일)
        with st.container(border=True):
            st.caption("📋 계좌별 최근 거래 데이터 현황")
            rows2 = _fetch_all("income_history")
            if rows2:
                df_inc_up = pd.DataFrame(rows2)
                df_inc_up["date"] = pd.to_datetime(df_inc_up["date"])
                latest2 = (df_inc_up.groupby("account_name")["date"]
                           .agg(["min", "max", "count"]).reset_index())
                latest2.columns = ["계좌", "첫 데이터", "최근 데이터", "건수"]
                latest2["첫 데이터"] = pd.to_datetime(latest2["첫 데이터"]).dt.strftime("%Y-%m-%d")
                latest2["최근 데이터"] = pd.to_datetime(latest2["최근 데이터"]).dt.strftime("%Y-%m-%d")
                st.dataframe(latest2, use_container_width=True, hide_index=True)
            else:
                st.write("업로드 이력 없음")

        income_account = st.selectbox(
            "계좌 선택",
            ["일반주식(국내+해외)", "ISA", "IRP", "연금저축"],
            key="income_acct",
        )
        income_file = st.file_uploader("xlsx 파일 선택", type=["xlsx", "xls"], key="income_file")

        if income_file:
            if st.button("파일 파싱", key="parse_income"):
                try:
                    if income_account == "IRP":
                        records = parse_income_b(income_file, account_name="IRP")
                    else:
                        key_map = {"일반주식(국내+해외)": "일반주식", "ISA": "ISA", "연금저축": "연금저축"}
                        records = parse_income_a(income_file, account_name=key_map[income_account])

                    # 중복 판별 키 — DB unique index와 동일하게 금액까지 포함
                    # (같은 날짜+계좌+종목+유형이라도 금액이 다르면 별개 거래로 취급)
                    def _akey(r):
                        v = r.get("amount_krw")
                        if v in (None, 0):
                            v = r.get("amount_usd")
                        return round(float(v), 2) if v not in (None, 0) else None

                    def _dkey(r):
                        return (str(r["date"]), r["account_name"], r["stock_name"] or "",
                                r["income_type"], _akey(r))

                    # 1) DB에 이미 있는 것 제거 (1,000행 제한 우회 위해 _fetch_all 사용)
                    existing = _fetch_all("income_history")
                    existing_keys = {_dkey(r) for r in existing}
                    after_db = [r for r in records if _dkey(r) not in existing_keys]

                    # 2) 파일 내 중복 제거 (같은 키가 여러 번 나올 경우 첫 번째만 유지)
                    seen = set()
                    new_records = []
                    for r in after_db:
                        k = _dkey(r)
                        if k not in seen:
                            seen.add(k)
                            new_records.append(r)

                    st.session_state["income_records_all"] = records
                    st.session_state["income_records_new"] = new_records
                except Exception as e:
                    st.error(f"파싱 오류: {e}")

        if "income_records_all" in st.session_state:
            all_r = st.session_state["income_records_all"]
            new_r = st.session_state["income_records_new"]
            dup_count = len(all_r) - len(new_r)

            c1, c2, c3 = st.columns(3)
            c1.metric("전체 파싱", f"{len(all_r)}건")
            c2.metric("신규 저장 예정", f"{len(new_r)}건")
            c3.metric("중복 건너뜀", f"{dup_count}건")

            if new_r:
                st.dataframe(pd.DataFrame(new_r), use_container_width=True)
                if st.button("✅ DB 저장 (신규만 추가)", key="save_income"):
                    try:
                        supabase.table("income_history").upsert(new_r, ignore_duplicates=True).execute()
                        st.success(f"{len(new_r)}건 저장 완료 (중복 {dup_count}건 건너뜀)")
                        del st.session_state["income_records_all"]
                        del st.session_state["income_records_new"]
                        st.rerun()
                    except Exception as e:
                        st.error(f"저장 오류: {e}")
            else:
                st.info("저장할 신규 데이터가 없습니다 (전부 중복).")

# ── 사이드바 하단 ──────────────────────────────────────────────────
with st.sidebar:
    st.divider()
    try:
        supabase.table("assets_snapshot").select("id").limit(1).execute()
        st.success("DB 연결됨")
    except Exception:
        st.error("DB 연결 오류")
