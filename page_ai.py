import streamlit as st
import json
import pandas as pd
from datetime import date
from utils import load_assets, load_income, load_family, load_insurance, load_surrender, load_memo, get_usd_krw, INCOME_TYPES


def _df_to_records(df: pd.DataFrame) -> list:
    if df.empty:
        return []
    df = df.copy()
    for col in df.select_dtypes(include=["datetime64[ns]", "datetime64[ns, UTC]"]).columns:
        df[col] = df[col].astype(str)
    return df.to_dict(orient="records")


def render():
    st.title("AI 재무 컨설팅")
    st.write("전체 자산 데이터를 JSON으로 생성해 ChatGPT / Claude / Gemini 에 붙여넣어 재무 조언을 받으세요.")

    if st.button("📊 내 재무 데이터 JSON 생성", type="primary"):
        usd_krw = get_usd_krw()
        today = date.today()

        df_assets = load_assets()
        df_income = load_income()
        df_family = load_family()
        df_ins = load_insurance()
        df_memo = load_memo()

        # 자산 요약
        asset_summary = {}
        if not df_assets.empty:
            for acct, grp in df_assets.groupby("account_name"):
                asset_summary[acct] = {
                    "종목수": len(grp),
                    "매입원금_원": float((grp["quantity"] * grp["avg_price"] *
                                        grp["currency"].map(lambda c: usd_krw if c == "USD" else 1)).sum()),
                    "보유종목": grp[["stock_name", "ticker", "quantity", "avg_price", "currency"]].to_dict(orient="records")
                }

        # 배당 요약
        div_summary = {}
        if not df_income.empty:
            df_div = df_income[df_income["income_type"].isin(INCOME_TYPES)]
            for yr, grp in df_div.groupby(df_div["date"].dt.year):
                div_summary[int(yr)] = {
                    "세후배당합계_원": float(grp["net_amount_krw"].sum()),
                    "건수": len(grp)
                }

        # 보험 요약
        ins_list = []
        if not df_ins.empty:
            for _, ins in df_ins.iterrows():
                start = pd.to_datetime(ins["start_date"]).date()
                elapsed = max(0, (today - start).days // 365)
                df_s = load_surrender(ins["id"])
                cur_surr = 0
                if not df_s.empty:
                    row = df_s[df_s["year_no"] == elapsed]
                    if not row.empty:
                        cur_surr = float(row.iloc[0]["surrender_amount"])
                ins_list.append({
                    "보험사": ins["company"],
                    "상품명": ins["product_name"],
                    "월납입": ins["monthly_premium"],
                    "가입일": str(ins["start_date"]),
                    "경과년수": elapsed,
                    "현재해약환급금": cur_surr,
                    "보장금리": ins.get("guaranteed_rate"),
                })

        # 가족 요약
        fam_list = []
        if not df_family.empty:
            for _, r in df_family.iterrows():
                birth = pd.to_datetime(r["birth_date"]).date()
                age = today.year - birth.year
                fam_list.append({"이름": r["name"], "관계": r["relation"], "나이": age})

        # 최근 메모 10개
        memo_list = _df_to_records(df_memo.head(10)) if not df_memo.empty else []

        payload = {
            "생성일": str(today),
            "환율_USD_KRW": usd_krw,
            "가족정보": fam_list,
            "자산현황": asset_summary,
            "연도별_배당이자": div_summary,
            "보험": ins_list,
            "최근메모": memo_list,
        }

        json_str = json.dumps(payload, ensure_ascii=False, indent=2)
        st.session_state["ai_json"] = json_str

    if "ai_json" in st.session_state:
        json_str = st.session_state["ai_json"]
        st.success(f"JSON 생성 완료 ({len(json_str):,} bytes)")

        st.code(json_str, language="json")
        st.download_button("💾 JSON 파일 다운로드", json_str,
                           file_name=f"cfo_data_{date.today()}.json",
                           mime="application/json")

        st.divider()
        st.subheader("추천 질문 예시")
        prompts = [
            "위 데이터를 바탕으로 현재 포트폴리오의 강점과 약점을 분석해줘.",
            "배당 성장 추세를 보고 월 100만원 배당을 달성하려면 몇 년이 걸릴지 예측해줘.",
            "보험 해약환급금을 재투자했을 때와 유지했을 때의 장단점을 비교해줘.",
            "자녀 대학 입학 시 필요한 자금을 마련하기 위한 전략을 제안해줘.",
            "현재 자산 배분이 적절한지 분석하고 리밸런싱 방향을 제안해줘.",
        ]
        for p in prompts:
            st.markdown(f"- {p}")
