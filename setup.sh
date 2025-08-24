#!/bin/bash

# Streamlit 앱 실행 전에 Playwright의 브라우저를 설치합니다.
# -y 옵션은 설치 중 묻는 모든 질문에 자동으로 'yes'로 답합니다.
playwright install --with-deps chromium
