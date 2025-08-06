# news_streamlit.py

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

# --- [추가된 부분] 커스텀 CSS ---
# st.multiselect의 태그 내부 텍스트가 잘리지 않고 줄바꿈되도록 설정
st.markdown("""
    <style>
        /* 선택된 키워드 태그의 높이를 자동으로 조절 */
        .stMultiSelect [data-baseweb="tag"] {
            height: auto !important;
            padding-top: 6px;
            padding-bottom: 6px;
        }
        /* 키워드 텍스트가 줄바꿈되도록 설정 */
        .stMultiSelect [data-baseweb="tag"] span[title] {
            white-space: normal !important; 
            max-width: 100%;
            display: inline-block;
        }
    </style>
""", unsafe_allow_html=True)
# --------------------------------

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
    st.markdown("### 🔑 AI가 추출한 핵심 키워드 (수정 가능)")

    # --- 키워드 편집 UI (폼 바깥) ---
    # 이 부분은 즉각적인 상호작용이 필요하므로 폼 외부에 위치합니다.
    temp_keywords = st.session_state.keywords[:]
    for i, keyword in enumerate(temp_keywords):
        col1, col2 = st.columns([0.85, 0.15])
        with col1:
            # 각 키워드를 고유한 key를 가진 text_input으로 만듦
            edited_keyword = st.text_input(
                label=f"keyword_{i}",
                value=keyword,
                key=f"keyword_input_{i}",
                label_visibility="collapsed"
            )
            # 입력값이 변경되면 세션 상태에 즉시 반영
            if edited_keyword != st.session_state.keywords[i]:
                st.session_state.keywords[i] = edited_keyword
                st.rerun()

        with col2:
            # 삭제 버튼 (st.button은 form 바깥에서 사용)
            if st.button("삭제", key=f"delete_keyword_{i}"):
                st.session_state.keywords.pop(i)
                st.rerun()

    # 새 키워드 추가 기능
    new_keyword = st.text_input("✨ 새 키워드 추가 (입력 후 Enter)")
    if new_keyword:
        st.session_state.keywords.append(new_keyword)
        st.rerun()
    # --- 키워드 편집 UI 끝 ---
    
    st.markdown("---")

    # --- 최종 제출 폼 ---
    # 이 부분은 여러 입력을 모아 한 번에 제출하기 위해 폼 내부에 위치합니다.
    with st.form("process_form"):
        st.markdown("**최종 분석에 사용할 키워드:**")
        # 편집이 완료된 키워드를 확인용으로 보여줌
        if st.session_state.keywords:
            st.info(", ".join(st.session_state.keywords))
        else:
            st.warning("분석할 키워드가 없습니다. 위에서 키워드를 추가해주세요.")

        num_to_search = st.number_input(
            "🔎 검색할 최대 뉴스 기사 수",
            min_value=1,
            max_value=100,
            value=30,
            step=1,
            help="분석할 뉴스의 최대 개수를 선택합니다. 직접 숫자를 입력할 수도 있습니다."
        )

        save_filename = st.text_input(
            "💾 저장할 파일 이름 (확장자 제외)", "AI_뉴스분석_리포트"
        )
        
        # 폼 제출 버튼
        process_button = st.form_submit_button("2️⃣ 리포트 생성 시작", type="primary")

        # 폼 제출 시 실행될 로직
        if process_button:
            final_keywords = st.session_state.keywords
            if not final_keywords:
                st.error("⚠️ 분석을 진행할 키워드를 하나 이상 입력하거나 추가해주세요.")
                st.stop()

            # (이하 프로그레스 바 및 비동기 처리 로직은 동일)
            status_text = st.empty()
            progress_bar = st.progress(0)
            
            def update_progress(current, total, message=None):
                progress_percentage = current / total
                if message is None:
                    message = f"📰 기사 처리 중... ({current}/{total})"
                status_text.text(message)
                progress_bar.progress(progress_percentage)
            
            try:
                status_text.text("네이버에서 관련 뉴스를 검색 중입니다...")
                news_items = search_news_naver(final_keywords, display=num_to_search)
                filtered_items = filter_news_by_date(news_items, start_date, end_date)

                if not filtered_items:
                    st.warning("❌ 지정된 기간 내에 관련 뉴스를 찾지 못했습니다. 기간이나 키워드를 조정해보세요.")
                    st.stop()
                    
                final_report, successful_results, failed_results = asyncio.run(
                    run_analysis_and_synthesis_async(filtered_items, progress_callback=update_progress)
                )

                if not final_report:
                    st.error("❌ 리포트를 생성하지 못했습니다. 요약 가능한 기사가 없습니다.")
                    st.stop()

                status_text.text("🎉 모든 작업 완료! 리포트를 확인하세요.")
                progress_bar.empty()

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
