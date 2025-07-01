# 📄 뉴스 요약 Word 리포트 생성기

Streamlit을 이용해 뉴스 링크로부터 키워드를 추출하고, 관련 기사를 수집한 후
GPT를 통해 요약 정리하여 Word 파일로 다운로드할 수 있는 앱입니다.

## 기능
- 네이버 뉴스 링크 입력
- GPT 기반 키워드 추출
- 관련 뉴스 검색 (NAVER OpenAPI)
- 기사 본문 크롤링
- A4 1장 요약 + 결론
- Word 파일 자동 생성 및 다운로드

## 실행 방법
```bash
streamlit run news_streamlit.py
