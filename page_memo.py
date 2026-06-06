import streamlit as st
import pandas as pd
from datetime import date
from db import get_client
from utils import load_memo

CATEGORIES = ["종목분석", "시장동향", "포트폴리오", "기타"]


def render():
    st.title("투자 메모")

    # ── 작성 폼 ───────────────────────────────────────────────────
    with st.expander("✏️ 새 메모 작성", expanded=False):
        with st.form("add_memo"):
            c1, c2, c3 = st.columns([1, 1, 2])
            memo_date = c1.date_input("날짜", value=date.today())
            category = c2.selectbox("카테고리", CATEGORIES)
            ticker = c3.text_input("관련 티커 (선택)", placeholder="AAPL, 005930.KS")
            title = st.text_input("제목 *")
            content = st.text_area("내용 *", height=150)
            tags = st.text_input("태그 (쉼표 구분)", placeholder="배당, ETF, 리밸런싱")

            submitted = st.form_submit_button("저장")
            if submitted:
                if not title or not content:
                    st.error("제목과 내용은 필수입니다.")
                else:
                    get_client().table("memo").insert({
                        "date": str(memo_date),
                        "category": category,
                        "title": title,
                        "content": content,
                        "related_ticker": ticker or None,
                        "tags": tags or None,
                    }).execute()
                    st.success("메모 저장 완료")
                    st.rerun()

    st.divider()

    df = load_memo()
    if df.empty:
        st.info("작성된 메모가 없습니다.")
        return

    # ── 필터 ─────────────────────────────────────────────────────
    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    sel_cat = col_f1.selectbox("카테고리", ["전체"] + CATEGORIES, key="m_cat")
    years = sorted(pd.to_datetime(df["date"]).dt.year.unique(), reverse=True)
    sel_year = col_f2.selectbox("연도", ["전체"] + [str(y) for y in years], key="m_year")
    search = col_f3.text_input("검색 (제목/내용/태그)", key="m_search")

    filt = df.copy()
    filt["date"] = pd.to_datetime(filt["date"])
    if sel_cat != "전체":
        filt = filt[filt["category"] == sel_cat]
    if sel_year != "전체":
        filt = filt[filt["date"].dt.year == int(sel_year)]
    if search:
        mask = (filt["title"].str.contains(search, case=False, na=False) |
                filt["content"].str.contains(search, case=False, na=False) |
                filt["tags"].fillna("").str.contains(search, case=False))
        filt = filt[mask]

    st.write(f"총 **{len(filt)}건**")

    # ── 메모 목록 ─────────────────────────────────────────────────
    for _, row in filt.iterrows():
        with st.container(border=True):
            h1, h2 = st.columns([5, 1])
            with h1:
                cat_color = {"종목분석": "🔵", "시장동향": "🟢", "포트폴리오": "🟡", "기타": "⚪"}.get(row["category"], "⚪")
                st.markdown(f"{cat_color} **{row['title']}**  "
                            f"<small style='color:gray'>{pd.to_datetime(row['date']).strftime('%Y-%m-%d')}  "
                            f"{row['category']}"
                            f"{' | ' + row['related_ticker'] if row.get('related_ticker') else ''}"
                            f"</small>", unsafe_allow_html=True)
                if row.get("tags"):
                    tags_html = " ".join([f"`{t.strip()}`" for t in str(row["tags"]).split(",")])
                    st.markdown(tags_html)

            with h2:
                if st.button("삭제", key=f"del_memo_{row['id']}", type="secondary"):
                    get_client().table("memo").delete().eq("id", row["id"]).execute()
                    st.rerun()

            with st.expander("내용 보기"):
                st.write(row["content"])
                if row.get("updated_at"):
                    st.caption(f"수정: {row['updated_at'][:10]}")
