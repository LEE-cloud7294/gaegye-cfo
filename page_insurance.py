import streamlit as st
import pandas as pd
from datetime import date
from db import get_client
from utils import load_insurance, load_surrender


def render():
    st.title("보험 관리")

    df_ins = load_insurance()
    today = date.today()

    # ── 보험 목록 ─────────────────────────────────────────────────
    if not df_ins.empty:
        for _, ins in df_ins.iterrows():
            start = pd.to_datetime(ins["start_date"]).date()
            elapsed = max(0, (today - start).days // 365)
            df_s = load_surrender(ins["id"])

            # 현재 해약환급금
            cur_surr = 0
            surr_rate = 0
            if not df_s.empty:
                row = df_s[df_s["year_no"] == elapsed]
                if not row.empty:
                    cur_surr = float(row.iloc[0]["surrender_amount"])
                    surr_rate = row.iloc[0].get("surrender_rate") or 0
                elif elapsed > df_s["year_no"].max():
                    last = df_s.iloc[-1]
                    cur_surr = float(last["surrender_amount"])
                    surr_rate = last.get("surrender_rate") or 0
                else:
                    surr_rate = 0

            paid_total = ins["monthly_premium"] * elapsed * 12

            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.markdown(f"### {ins['company']}  {ins['product_name']}")
                    cc1, cc2, cc3, cc4 = st.columns(4)
                    cc1.metric("월 납입료", f"₩{ins['monthly_premium']:,.0f}")
                    cc2.metric("경과 년수", f"{elapsed}년차")
                    cc3.metric("현재 해약환급금", f"₩{cur_surr:,.0f}")
                    cc4.metric("보장 금리", f"{ins.get('guaranteed_rate') or 0:.1f}%")

                    if ins.get("note"):
                        st.caption(f"비고: {ins['note']}")

                with c2:
                    if st.button("삭제", key=f"del_ins_{ins['id']}", type="secondary"):
                        get_client().table("insurance").delete().eq("id", ins["id"]).execute()
                        st.rerun()

            # 해약환급금 테이블
            if not df_s.empty:
                with st.expander(f"📋 {ins['product_name']} — 연도별 해약환급금"):
                    df_s["누적납입원금"] = ins["monthly_premium"] * df_s["year_no"] * 12
                    show = df_s[["year_no", "surrender_amount", "surrender_rate", "누적납입원금"]].copy()
                    show.columns = ["년차", "해약환급금(원)", "납입원금대비(%)", "누적납입원금(원)"]
                    # 현재 년차 강조
                    def highlight(row):
                        color = "background-color: #d4edda" if row["년차"] == elapsed else ""
                        return [color] * len(row)
                    st.dataframe(show.style.apply(highlight, axis=1),
                                 use_container_width=True, hide_index=True)
        st.divider()
    else:
        st.info("등록된 보험이 없습니다.")

    # ── 보험 추가 폼 ──────────────────────────────────────────────
    with st.expander("➕ 새 보험 추가"):
        with st.form("add_insurance"):
            c1, c2 = st.columns(2)
            company = c1.text_input("보험사명 *")
            product = c2.text_input("상품명 *")
            c3, c4 = st.columns(2)
            premium = c3.number_input("월 납입료 (원) *", min_value=0, step=1000)
            rate = c4.number_input("보장 고정금리 (%)", min_value=0.0, step=0.1)
            c5, c6, c7 = st.columns(3)
            start_d = c5.date_input("가입일 *", value=date.today())
            pay_end = c6.date_input("납입 종료일", value=None)
            cont_end = c7.date_input("계약 만기일", value=None)
            note = st.text_input("비고")

            submitted = st.form_submit_button("저장")
            if submitted:
                if not company or not product or not premium:
                    st.error("보험사명, 상품명, 월납입료는 필수입니다.")
                else:
                    rec = {
                        "company": company,
                        "product_name": product,
                        "monthly_premium": premium,
                        "start_date": str(start_d),
                        "payment_end_date": str(pay_end) if pay_end else None,
                        "contract_end_date": str(cont_end) if cont_end else None,
                        "guaranteed_rate": rate if rate else None,
                        "note": note or None,
                    }
                    result = get_client().table("insurance").insert(rec).execute()
                    st.success(f"'{product}' 저장 완료")
                    st.rerun()

    # ── 해약환급금 입력 ───────────────────────────────────────────
    if not df_ins.empty:
        with st.expander("📥 해약환급금 데이터 입력"):
            ins_options = {f"{r['company']} {r['product_name']}": r["id"] for _, r in df_ins.iterrows()}
            sel = st.selectbox("보험 선택", list(ins_options.keys()))
            ins_id = ins_options[sel]

            st.write("연차별 해약환급금을 입력하세요 (여러 행 추가 가능):")

            df_input = pd.DataFrame({"년차": [1], "해약환급금(원)": [0], "납입원금대비(%)": [0.0]})
            edited = st.data_editor(df_input, num_rows="dynamic", use_container_width=True)

            if st.button("저장", key="save_surrender"):
                records = []
                for _, row in edited.iterrows():
                    if row["해약환급금(원)"] > 0:
                        records.append({
                            "insurance_id": ins_id,
                            "year_no": int(row["년차"]),
                            "surrender_amount": float(row["해약환급금(원)"]),
                            "surrender_rate": float(row["납입원금대비(%)"] or 0) or None,
                        })
                if records:
                    (get_client().table("insurance_surrender")
                     .upsert(records, on_conflict="insurance_id,year_no").execute())
                    st.success(f"{len(records)}건 저장 완료")
                    st.rerun()
