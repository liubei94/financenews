

import streamlit as st
import os
from datetime import datetime, date
from io import BytesIO
import asyncio
import re

# 최적화된 백엔드 워크플로우 함수들을 import
from news_workflow import (
    extract_initial_article_content,
    extract_keywords_with_gpt,
    search_news_naver,
    filter_news_by_date,
    run_analysis_and_synthesis_async,
    save_summary_to_word,
)

# 1. st.set_page_config()를 가장 먼저 호출
st.set_page_config(
    page_title="AI 뉴스 분석 리포트 생성기", page_icon="📰", layout="wide"
)

# 2. 그 다음에 다른 st 명령어들을 배치
# --- [개선된 부분] 태그 스타일 UI를 위한 커스텀 CSS ---
st.markdown(
    """
    <style>
        /* 태그들을 담는 컨테이너 */
        .tags-container {
            display: flex;
            flex-wrap: wrap;
            gap: 8px; /* 태그 사이의 간격 */
            margin-bottom: 1rem;
        }
        /* 개별 태그 스타일 */
        .tag-item {
            display: inline-flex;
            align-items: center;
            background-color: #F0F2F6; /* 스트림릿과 유사한 연한 회색 */
            color: #31333F; /* 기본 텍스트 색상 */
            padding: 6px 12px;
            border-radius: 16px; /* 둥근 모서리 */
            font-size: 14px;
            font-weight: 400;
            border: 1px solid #DCDCDC; /* 연한 테두리 */
        }
        /* 태그 안의 삭제 버튼 (st.button은 직접 스타일링이 어려워 이 방식은 사용하지 않음) */
    </style>
""",
    unsafe_allow_html=True,
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
    st.session_state.final_keywords = []
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
                title, content = extract_initial_article_content(link)
                st.session_state.keywords = asyncio.run(
                    extract_keywords_with_gpt(title, content)
                )
                st.session_state.step = "keywords_ready"
                # 다음 단계를 위해 'final_keywords'를 초기화
                st.session_state.final_keywords = st.session_state.keywords[:]
                st.rerun()
            except Exception as e:
                st.error(f"❌ 키워드 추출 중 오류 발생: {e}")
                st.session_state.step = "initial"


# 2단계: 키워드 확인 및 최종 리포트 생성
if st.session_state.step == "keywords_ready":
    st.markdown("---")

    st.markdown("### 🔑 AI가 제안하는 핵심 키워드")
    st.info(f"**추천 키워드:** {', '.join(st.session_state.keywords)}")

    st.markdown("### ✍️ 분석에 사용할 최종 키워드 편집")
    st.write(
        "키워드를 직접 추가하거나, 각 키워드 옆의 `x` 버튼을 눌러 삭제할 수 있습니다."
    )

    # --- [개선된 부분] 태그 스타일 UI 로직 ---

    # 1. 키워드 추가 콜백 함수
    def add_keyword():
        new_kw = st.session_state.new_keyword_input.strip()
        if new_kw and new_kw not in st.session_state.final_keywords:
            st.session_state.final_keywords.append(new_kw)
            st.session_state.new_keyword_input = ""  # 입력창 비우기

    # 2. 키워드 삭제 콜백 함수
    def delete_keyword(keyword_to_delete):
        if keyword_to_delete in st.session_state.final_keywords:
            st.session_state.final_keywords.remove(keyword_to_delete)

    # 3. 새 키워드 입력창
    st.text_input(
        "새 키워드 추가 후 Enter",
        key="new_keyword_input",
        on_change=add_keyword,
        placeholder="키워드를 입력하고 Enter를 누르세요",
    )

    # 4. 현재 키워드들을 태그 형태로 표시
    if "final_keywords" in st.session_state and st.session_state.final_keywords:
        cols = st.columns(6)  # 한 줄에 최대 6개의 태그를 표시
        col_idx = 0
        for keyword in st.session_state.final_keywords:
            with cols[col_idx]:
                # 각 키워드와 삭제 버튼을 한 쌍으로 묶음
                sub_cols = st.columns([0.8, 0.2])
                with sub_cols[0]:
                    st.markdown(
                        f'<div class="tag-item">{keyword}</div>', unsafe_allow_html=True
                    )
                with sub_cols[1]:
                    st.button(
                        "x",
                        key=f"delete_{keyword}",
                        on_click=delete_keyword,
                        args=(keyword,),
                        help=f"'{keyword}' 삭제",
                    )

            col_idx = (col_idx + 1) % 6
    else:
        st.warning("분석할 키워드가 없습니다. 위에서 추가해주세요.")
    # --- 개선된 부분 끝 ---

    st.markdown("---")

    # --- 3. 최종 설정 및 제출 폼 ---
    with st.form("process_form"):
        st.markdown("### ⚙️ 리포트 생성 설정")

        num_to_process = st.number_input(
            "🔎 검색할 최대 뉴스 기사 수", min_value=1, max_value=100, value=30, step=1
        )
        save_filename = st.text_input(
            "💾 저장할 파일 이름 (확장자 제외)", "AI_뉴스분석_리포트"
        )

        process_button = st.form_submit_button(
            "2️⃣ 리포트 생성 시작", type="primary", use_container_width=True
        )

        if process_button:
            final_keywords = st.session_state.final_keywords
            if not final_keywords:
                st.error("⚠️ 분석을 진행할 키워드를 하나 이상 추가해주세요.")
                st.stop()

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
                news_items = search_news_naver(final_keywords, display=num_to_process)
                filtered_items = filter_news_by_date(news_items, start_date, end_date)

                if not filtered_items:
                    st.warning(
                        "❌ 지정된 기간 내에 관련 뉴스를 찾지 못했습니다. 기간이나 키워드를 조정해보세요."
                    )
                    st.stop()

                final_report, successful_results, failed_results = asyncio.run(
                    run_analysis_and_synthesis_async(
                        filtered_items, progress_callback=update_progress
                    )
                )

                if not final_report:
                    st.error(
                        "❌ 리포트를 생성하지 못했습니다. 요약 가능한 기사가 없습니다."
                    )
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
