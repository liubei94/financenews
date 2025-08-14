import streamlit as st
import os
from datetime import datetime, date
from io import BytesIO
import asyncio
import re

# 최적화된 백엔드 워크플로우 함수들을 import
from news_workflow import (
    extract_initial_article_content,
    extract_keywords_with_gemini,
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
st.markdown("""
    <style>
        /* 키워드 태그의 기반이 될 컨테이너 스타일 */
        div[data-testid="stContainer"][style*="border"] {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background-color: #0d6efd; /* 파란색 배경 */
            border-radius: 20px !important; /* 둥근 모서리 */
            padding: 3px 5px 3px 15px !important; /* 내부 여백 */
            border: none !important; /* 기본 테두리 제거 */
            color: white !important;
            margin-top: 5px; /* 태그 위쪽 간격 */
        }

        /* 컨테이너 안의 마크다운 텍스트(p 태그) 스타일 */
        div[data-testid="stContainer"][style*="border"] p {
            color: white !important;
            margin: 0 !important;
            padding: 0 !important;
            font-size: 14px;
        }

        /* 컨테이너 안의 버튼 스타일 */
        div[data-testid="stContainer"][style*="border"] button {
            background-color: transparent !important;
            color: white !important;
            border: none !important;
            font-weight: bold;
            font-size: 18px;
            padding: 0 !important;
            margin: 0 !important;
            line-height: 1;
            width: 24px;
            height: 24px;
        }

        /* 버튼에 마우스를 올렸을 때 효과 */
        div[data-testid="stContainer"][style*="border"] button:hover {
            background-color: rgba(255, 255, 255, 0.2) !important;
            border-radius: 50%;
        }

        /* 내부 컬럼 간격 최소화 */
        div[data-testid="stContainer"][style*="border"] div[data-testid="stHorizontalBlock"] {
            gap: 0.5rem !important;
        }
    </style>
""", unsafe_allow_html=True)


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

    # [추가] 키워드 개수 선택 UI
    keyword_count = st.number_input(
        "🤖 AI가 추출할 최대 키워드 개수",
        min_value=3, max_value=10, value=5, step=1,
        help="AI가 뉴스 분석 후 최초로 제안할 키워드의 개수를 설정합니다."
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
        with st.spinner(f"기준 기사를 분석하고 Gemini로 키워드 {keyword_count}개를 추출 중입니다..."):
            try:
                title, content = extract_initial_article_content(link)
                st.session_state.keywords = asyncio.run(
                    extract_keywords_with_gemini(title, content, max_count=keyword_count)
                )
                st.session_state.step = "keywords_ready"
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

    # --- [개선된 부분] 태그 스타일 UI 로직 ---

    # 1. 키워드 추가 콜백 함수 (중복 체크 로직 제거)
    def add_keyword():
        new_kw = st.session_state.new_keyword_input.strip()
        # [수정] 중복 여부와 관계없이 키워드를 추가하도록 변경
        if new_kw:
            st.session_state.final_keywords.append(new_kw)
        st.session_state.new_keyword_input = ""


    # 2. 현재 키워드를 태그 형태로 표시 (삭제 로직 수정)
    st.write("**현재 키워드 목록:**")
    if 'final_keywords' in st.session_state and st.session_state.final_keywords:
        num_columns = 5
        keyword_chunks = [st.session_state.final_keywords[i:i + num_columns] for i in range(0, len(st.session_state.final_keywords), num_columns)]

        # [수정] 각 키워드의 '고유한 순서(인덱스)'를 기준으로 삭제 로직을 처리
        for chunk_index, chunk in enumerate(keyword_chunks):
            cols = st.columns(num_columns)
            for i, keyword in enumerate(chunk):
                with cols[i]:
                    # 청크와 내부 순서를 조합해 실제 전체 리스트에서의 인덱스 계산
                    original_index = chunk_index * num_columns + i

                    with st.container(border=True):
                        sub_cols = st.columns([4, 1], gap="small")
                        with sub_cols[0]:
                            st.markdown(f"{keyword}")
                        with sub_cols[1]:
                            # [수정] 버튼의 key와 삭제 로직 모두 고유 인덱스를 사용
                            if st.button("×", key=f"delete_{original_index}", help=f"'{keyword}' 삭제"):
                                st.session_state.final_keywords.pop(original_index)
                                st.rerun()
    else:
        st.info("분석할 키워드가 없습니다. 아래에서 추가해주세요.")


    # 3. 새 키워드 입력창
    st.text_input(
        "새 키워드 추가",
        key="new_keyword_input",
        on_change=add_keyword,
        placeholder="키워드 입력 후 Enter...",
        label_visibility="collapsed",
    )
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
