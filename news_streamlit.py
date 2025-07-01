import streamlit as st
import os
from datetime import datetime
from tempfile import NamedTemporaryFile

from news import (
    extract_article_content,
    extract_keywords_with_gpt,
    search_news_naver,
    extract_article,
    summarize_news_articles,
    save_summary_to_word
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
save_dir = st.text_input("📁 저장 경로 (없으면 현재 폴더)", "")

if st.button("🚀 요약 리포트 생성하기"):
    if not link:
        st.warning("뉴스 링크를 입력해주세요.")
    elif start_date > end_date:
        st.error("종료일은 시작일보다 같거나 이후여야 합니다.")
    else:
        with st.spinner("GPT 요약 리포트를 생성 중입니다..."):
            try:
                title, content = extract_article_content(link)
                keywords = extract_keywords_with_gpt(title, content)
                st.markdown(f"🔑 **추출된 키워드:** {' | '.join(keywords)}")

                s_date = start_date.strftime("%Y%m%d")
                e_date = end_date.strftime("%Y%m%d")
                news_items = search_news_naver(keywords, s_date, e_date, count)
                links = [item['link'] for item in news_items]

                titles, contents = [], []
                progress = st.progress(0)
                status = st.empty()
                for i, link in enumerate(links, 1):
                    status.text(f"크롤링 중: [{i}/{len(links)}] {link}")
                    title, content = extract_article(link)
                    if title and content:
                        titles.append(title)
                        contents.append(content)
                    else:
                        st.warning(f"⚠️ 크롤링 실패: {link}")
                    progress.progress(i / len(links))

                summary = summarize_news_articles(titles, contents)
                st.subheader("📝 요약 미리보기")
                st.markdown(f"<div style='white-space: pre-wrap'>{summary}</div>", unsafe_allow_html=True)

                filename = save_filename + ".docx"
                save_path = os.path.join(save_dir if save_dir else os.getcwd(), filename)
                save_summary_to_word(summary, titles, links, news_items, keywords, save_path)

                with open(save_path, "rb") as f:
                    st.success("요약 Word 리포트가 완성되었습니다!")
                    st.download_button(
                        label="📥 요약 Word 파일 다운로드",
                        data=f,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )

            except Exception as e:
                st.error(f"🚫 오류가 발생했습니다: {str(e)}")
