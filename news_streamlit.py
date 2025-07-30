import streamlit as st
import os
from datetime import datetime
from io import BytesIO

from news import (
    extract_article,
    extract_keywords_with_gpt,
    search_news_naver,
    extract_article,
    summarize_news_articles,
    save_summary_to_word,
    filter_news_by_date  # ✅ 날짜 필터링 함수 추가 import
)

st.set_page_config(page_title="뉴스 요약 리포트 생성기", page_icon="📰")
st.title("📰 뉴스 요약 Word 리포트 생성기")
st.markdown("""
1. 뉴스 링크를 입력하면 키워드를 추출하고  
2. 관련 뉴스를 수집한 뒤  
3. GPT로 요약하여  
4. Word 파일로 정리해드립니다.
""")

link = st.text_input("🔗 분석할 뉴스 링크 입력")
start_date = st.date_input("검색 시작일", datetime.today())
end_date = st.date_input("검색 종료일", datetime.today())
count = st.number_input("검색할 뉴스 건수", min_value=1, max_value=100, value=30)
save_filename = st.text_input("💾 저장할 파일 이름 (확장자 제외)", "요약_뉴스")

# 초기화
if 'step' not in st.session_state:
    st.session_state.step = None

# 단계 1: 키워드 추출 시작
if st.button("🚀 GPT 키워드 추출"):
    if not link:
        st.warning("뉴스 링크를 입력해주세요.")
    elif start_date > end_date:
        st.error("종료일은 시작일보다 같거나 이후여야 합니다.")
    else:
        with st.spinner("GPT로 키워드를 추출 중입니다..."):
            try:
                title, content = extract_article(link)
                default_keywords = extract_keywords_with_gpt(title, content)
                st.session_state.title = title
                st.session_state.content = content
                st.session_state.default_keywords = default_keywords
                st.session_state.step = "keywords_ready"
            except Exception as e:
                st.error(f"❌ 키워드 추출 실패: {e}")
                st.session_state.step = None

# 단계 2: 키워드 확인 및 뉴스 검색
if st.session_state.step == "keywords_ready":
    st.markdown("### 🔑 추출된 키워드 확인 및 수정")
    keywords_input = st.text_input(
        "GPT가 추출한 키워드입니다. 필요시 수정하세요 (최대 10개, 띄어쓰기로 구분):",
        value=', '.join(st.session_state.default_keywords),
        key="keywords_input"
    )

    if st.button("📡 뉴스 검색 및 요약 생성"):
        with st.spinner("뉴스 수집 및 요약 중입니다..."):
            try:
                keywords = [kw.strip() for kw in keywords_input.split() if kw.strip()]
                if len(keywords) > 10:
                    st.warning("⚠️ 키워드는 최대 10개까지만 사용됩니다.")
                    keywords = keywords[:10]

                # ✅ 날짜 포맷 변경 (filter 함수와 일치하도록)
                s_date = start_date.strftime("%Y-%m-%d")
                e_date = end_date.strftime("%Y-%m-%d")

                # 뉴스 검색
                news_items = search_news_naver(keywords, s_date, e_date, count)

                # ✅ 날짜 필터링 적용
                filtered_items = filter_news_by_date(news_items, s_date, e_date)

                if not filtered_items:
                    st.warning("❌ 날짜 조건에 맞는 뉴스가 없습니다.")
                else:
                    # ✅ 링크 추출도 필터링된 뉴스 기준
                    links = [item['link'] for item in filtered_items]

                    titles, contents, failed_links = [], [], []
                    progress = st.progress(0)
                    status = st.empty()
                    for i, news_link in enumerate(links, 1):
                        status.text(f"크롤링 중: [{i}/{len(links)}] {news_link}")
                        title, content = extract_article(news_link)
                        if title and content:
                            titles.append(title)
                            contents.append(content)
                        else:
                            failed_links.append(news_link)
                        progress.progress(i / len(links))

                    summary = summarize_news_articles(titles, contents)
                    st.subheader("📝 요약 미리보기")
                    st.markdown(f"<div style='white-space: pre-wrap'>{summary}</div>", unsafe_allow_html=True)

                    # Word 파일 생성 (BytesIO로 저장)
                    buffer = BytesIO()
                    save_summary_to_word(
                        summary,
                        titles,
                        links,
                        filtered_items,  # ✅ 필터링된 뉴스만 저장
                        keywords,
                        output_stream=buffer,
                        failed_links=failed_links
                    )
                    buffer.seek(0)

                    st.success("✅ Word 파일이 준비되었습니다.")
                    st.info("💡 다운로드 버튼을 클릭하면 파일이 브라우저의 **다운로드 폴더**에 저장됩니다.\n\n📁 저장 위치를 직접 지정하고 싶다면, 브라우저 설정에서 '항상 저장 위치 묻기' 옵션을 켜주세요.")

                    st.download_button(
                        label="📥 요약 Word 파일 다운로드",
                        data=buffer,
                        file_name=save_filename + ".docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )

                    if failed_links:
                        with st.expander("❌ 크롤링 실패한 뉴스 링크 목록"):
                            for fl in failed_links:
                                st.markdown(f"- {fl}")
            except Exception as e:
                st.error(f"🚫 오류가 발생했습니다: {str(e)}")
