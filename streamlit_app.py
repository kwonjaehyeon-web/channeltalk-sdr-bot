"""
채널톡 SDR 고객 분석기 — Streamlit UI
"""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from app.services.serper import SerperService
from app.services.llm import LLMService
from app.services.notion import NotionService

# ── 서비스 초기화 (세션당 1번) ────────────────────────────────────────────────
@st.cache_resource
def get_services():
    return SerperService(), LLMService(), NotionService()

serper, llm, notion = get_services()

# ── 페이지 설정 ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="채널톡 SDR 분석기",
    page_icon="💬",
    layout="centered",
)

# ── 헤더 ─────────────────────────────────────────────────────────────────────
st.title("💬 채널톡 SDR 고객 분석기")
st.caption("기업명을 입력하면 ICP 분석 → 페인포인트 도출 → 채널톡 솔루션 매칭까지 자동으로 분석합니다.")
st.divider()

# ── 입력 ─────────────────────────────────────────────────────────────────────
col1, col2 = st.columns([4, 1])
with col1:
    company_name = st.text_input(
        "기업명",
        placeholder="예) 무신사, 토스, 쏘카",
        label_visibility="collapsed",
    )
with col2:
    analyze_btn = st.button("분석 시작", type="primary", use_container_width=True)

# ── 분석 실행 ─────────────────────────────────────────────────────────────────
if analyze_btn and company_name:
    with st.spinner(f"**{company_name}** 분석 중..."):
        ct_context  = notion.fetch_channeltalk_context()
        guidelines  = notion.fetch_analysis_guidelines()
        search_data = serper.fetch_all(company_name)
        result      = llm.analyze(company_name, search_data, ct_context, guidelines)

    # ── 리포트 출력 ──────────────────────────────────────────────────────────
    st.divider()

    # 기업 요약
    st.subheader(f"📋 {company_name} 분석 리포트")
    st.info(result.get("company_summary", ""))

    # ICP 섹션
    st.markdown("### 🎯 ICP 분석")
    icp_fit = result.get("icp_fit", "Medium")
    fit_color = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(icp_fit, "🟡")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("산업군", result.get("icp_industry", "-"))
    with col2:
        st.metric("규모 / 매출", result.get("icp_scale", "-"))
    with col3:
        st.metric("ICP 적합도", f"{fit_color} {icp_fit}")

    with st.expander("ICP 판단 근거"):
        st.write(result.get("icp_fit_reason", "-"))

    st.divider()

    # Problem 섹션
    st.markdown("### 🔥 페인포인트 (Problem)")
    st.write(result.get("problem", "-"))
    with st.expander("근거 (채용공고 / 뉴스)"):
        st.write(result.get("problem_evidence", "-"))

    st.divider()

    # 솔루션 섹션
    st.markdown("### 💡 채널톡 솔루션 매칭")
    st.success(result.get("channeltalk_solution", "-"))

    st.divider()

    # 의사결정자 섹션
    st.markdown("### 👤 의사결정자 추론")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("추정 직함", result.get("decision_maker", "-"))
    with col2:
        st.write(result.get("decision_maker_reason", "-"))

    linkedin_results = search_data.get("linkedin", [])
    if linkedin_results:
        with st.expander(f"LinkedIn 검색 결과 ({len(linkedin_results)}건)"):
            for item in linkedin_results:
                st.markdown(f"**[{item['title']}]({item['link']})**")
                st.caption(item.get("snippet", ""))
                st.divider()

    st.divider()

    # Notion 저장
    with st.spinner("Notion에 저장 중..."):
        notion_url = notion.save(company_name, result)

    if notion_url:
        st.success(f"✅ Notion에 저장 완료 → [리포트 보기]({notion_url})")
    else:
        st.warning("Notion 저장 실패 (토큰 또는 DB ID 확인 필요)")

elif analyze_btn and not company_name:
    st.warning("기업명을 입력해주세요.")
