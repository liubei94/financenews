# app.py

import streamlit as st
import os
from datetime import datetime, date
from io import BytesIO
import asyncio

# 최적화된 백엔드 워크플로우 함수들을 import
from news_workflow import (
    extract_initial_article_content,
    extract_keywords_with_gpt,
    search_news_naver,
    filter_news_by_date,
    run_analysis_and_synthesis_async,
    save_summary_to_word,
)

st.set_page_config(
    page_title="AI 뉴스 분석 리포트 생성기", page_icon="📰", layout="wide"
)
st.title("📰 AI 뉴스 분석 Word 리포트 생성기")
st.markdown(
    """
1.  **기준 뉴스 링크**를 입력하고 기간을 설정하세요.
2.  **GPT 키워드 추출** 버튼을 눌러 AI가 핵심 키워드를 찾도록 합니다.
3.  추출된 키워드를 확인하고 **리포트 생성 시작** 버튼을 누르면, AI가 관련 뉴스를 분석하여 심층 리포트를 생성합니다.
"""
)

# --- UI 컴포넌트 ---
with st.form("input_form"):
    link = st.text_input(
        "🔗 분석의 기준이 될 뉴스 링크를 입력하세요",
        placeholder="https://n.news.naver.com/article/...",
    )

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("검색 시작일", date.today())
    with col2:
        end_date = st.date_input("검색 종료일", date.today())

    submitted = st.form_submit_button("1️⃣ GPT 키워드 추출", type="primary")

# --- 세션 상태 초기화 ---
if "step" not in st.session_state:
    st.session_state.step = "initial"
    st.session_state.keywords = []
    st.session_state.final_report = None
    st.session_state.successful_results = []
    st.session_state.failed_results = []

# --- 로직 실행 ---

# 1단계: 키워드 추출
if submitted:
    if not link:
        st.warning("뉴스 링크를 입력해주세요.")
    elif start_date > end_date:
        st.error("종료일은 시작일보다 같거나 이후여야 합니다.")
    else:
        with st.spinner("기준 기사를 분석하고 GPT로 키워드를 추출 중입니다..."):
            try:
                # 동기/비동기 함수 실행
                title, content = extract_initial_article_content(link)
                st.session_state.keywords = asyncio.run(
                    extract_keywords_with_gpt(title, content)
                )
                st.session_state.step = "keywords_ready"
                st.rerun()  # 키워드 표시를 위해 스크립트 재실행
            except Exception as e:
                st.error(f"❌ 키워드 추출 중 오류 발생: {e}")
                st.session_state.step = "initial"

# 2단계: 키워드 확인 및 최종 리포트 생성
if st.session_state.step == "keywords_ready":
    st.markdown("---")
    st.markdown("### 🔑 AI가 추출한 핵심 키워드")
    st.info(f"**추출된 키워드:** {', '.join(st.session_state.keywords)}")

    with st.form("process_form"):
        st.markdown(
            "위 키워드를 바탕으로 관련 뉴스를 검색하고, 전체 내용을 분석하여 리포트를 생성합니다."
        )
        save_filename = st.text_input(
            "💾 저장할 파일 이름 (확장자 제외)", "AI_뉴스분석_리포트"
        )
        process_button = st.form_submit_button("2️⃣ 리포트 생성 시작", type="primary")

    if process_button:
        with st.spinner(
            "관련 뉴스를 수집하고 AI가 분석/요약 중입니다. 이 작업은 몇 분 정도 소요될 수 있습니다..."
        ):
            try:
                # 동기 작업: 뉴스 검색 및 필터링
                news_items = search_news_naver(st.session_state.keywords)
                filtered_items = filter_news_by_date(news_items, start_date, end_date)

                if not filtered_items:
                    st.warning(
                        "❌ 지정된 기간 내에 관련 뉴스를 찾지 못했습니다. 기간을 조정해보세요."
                    )
                    st.stop()

                # 비동기 작업: 병렬 크롤링, 개별 요약, 최종 종합
                final_report, successful_results, failed_results = asyncio.run(
                    run_analysis_and_synthesis_async(filtered_items)
                )

                if not final_report:
                    st.error(
                        "❌ 리포트를 생성하지 못했습니다. 요약 가능한 기사가 없습니다."
                    )
                    st.stop()

                # 결과 저장
                st.session_state.final_report = final_report
                st.session_state.successful_results = successful_results
                st.session_state.failed_results = failed_results
                st.session_state.save_filename = save_filename
                st.session_state.step = "done"
                st.rerun()

            except Exception as e:
                st.error(f"🚫 리포트 생성 중 심각한 오류가 발생했습니다: {e}")
                st.session_state.step = "initial"


# 3단계: 결과 표시 및 다운로드
if st.session_state.step == "done":
    st.markdown("---")
    st.success("✅ AI 뉴스 분석 리포트 생성이 완료되었습니다!")

    # Word 파일 생성 (메모리 내)
    buffer = BytesIO()
    save_summary_to_word(
        st.session_state.final_report, st.session_state.successful_results, buffer
    )
    buffer.seek(0)

    st.download_button(
        label="📥 Word 리포트 다운로드",
        data=buffer,
        file_name=f"{st.session_state.save_filename}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    with st.expander("📄 생성된 리포트 미리보기"):
        st.markdown(st.session_state.final_report)

    if st.session_state.failed_results:
        with st.expander(
            f"⚠️ 처리 실패한 뉴스 목록 ({len(st.session_state.failed_results)}개)"
        ):
            for item in st.session_state.failed_results:
                st.write(f"- **사유:** {item['reason']} / **링크:** {item['link']}")
