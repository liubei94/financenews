import requests
from bs4 import BeautifulSoup
from openai import OpenAI
import os
from dotenv import load_dotenv
from docx import Document
from docx.shared import Pt
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from urllib.parse import urlparse
from datetime import datetime
import re

# Load environment variables
load_dotenv()
client = OpenAI()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")

### 1단계: 뉴스 제목과 본문 추출
def extract_article_content(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    title_tag = soup.find('h2', class_='media_end_head_headline')
    title = title_tag.get_text(strip=True) if title_tag else '제목 없음'
    content_tag = soup.find('article')
    paragraphs = content_tag.find_all('p') if content_tag else []
    content = ' '.join([p.get_text(strip=True) for p in paragraphs])
    return title, content

### 키워드 추출 (GPT)
def extract_keywords_with_gpt(title, content):
    prompt = f"""
다음은 뉴스의 제목과 본문입니다. 핵심 키워드 3개를 한글로 추출해주세요.
- 제목에 등장하는 단어나 표현을 우선 고려해 키워드를 선택해주세요.
- 본문 전체를 참고하되, 주제를 잘 대표하는 단어를 뽑아주세요.

제목: {title}
본문: {content}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 키워드 추출기입니다. 본문을 가장 잘 나타낼 수 있는 키워드를 추출하세요."},
            {"role": "user", "content": prompt}
        ]
    )
    keywords = response.choices[0].message.content.strip().split('\n')
    cleaned = []
    for kw in keywords:
        kw = re.sub(r'^\d+\.\s*', '', kw).strip()  # 숫자. 제거 (1. 키워드 → 키워드)
        if kw:
            cleaned.append(kw)
    return cleaned[:3]  # 최대 3개 제한

### 2단계: 뉴스 검색 (NAVER API)
def search_news_naver(keywords, start_date, end_date, display=30):
    query = ' '.join([kw.strip("1234567890. ") for kw in keywords if kw.strip()])
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": query,
        "display": display,
        "sort": "date"
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()['items']
    else:
        print("⚠️ 네이버 API 요청 실패:", response.text)
        return []

### ✅ 날짜 필터링 함수 추가
def filter_news_by_date(news_items, start_date, end_date):
    # 문자열이면 파싱, date/datetime이면 그대로 사용
    if isinstance(start_date, str):
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start = start_date

    if isinstance(end_date, str):
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    else:
        end = end_date

    filtered = []
    

    print(f"\n🟡 필터링 전 총 뉴스 개수: {len(news_items)}")

    for i, item in enumerate(news_items, 1):
        title = re.sub('<.*?>', '', item.get("title", "제목 없음"))
        link = item.get("link")
        pub_raw = item.get("pubDate")

        print(f"\n[{i}] 📄 {title}")
        print(f"    🔗 {link}")
        print(f"    📅 원본 pubDate: {pub_raw}")

        if not pub_raw:
            print("    ❌ pubDate 없음, 필터 제외됨")
            continue

        try:
            pub_date = datetime.strptime(pub_raw, "%a, %d %b %Y %H:%M:%S %z").date()
            print(f"    ✅ 파싱된 날짜: {pub_date}")
            if start <= pub_date <= end:
                print("    ✅ ✅ 날짜 범위 ✅ 포함됨")
                filtered.append(item)
            else:
                print("    ⚠️ 날짜 범위 밖 → 제외됨")
        except Exception as e:
            print("    ❌ pubDate 파싱 실패:", e)

    print(f"\n🟢 필터링 후 뉴스 개수: {len(filtered)}")
    return filtered



### ✅ 기사 목록 출력 함수 추가
def display_news_list(news_items):
    print("\n🔍 검색된 뉴스 목록:")
    for i, item in enumerate(news_items, 1):
        title = re.sub('<.*?>', '', item['title'])  # HTML 태그 제거
        link = item['link']
        pubdate = extract_pubdate_from_item(item)
        print(f"[{i}] {title} ({pubdate})")
        print(f"     {link}")


### 3단계: 뉴스 기사 크롤링
def extract_naver_article(link):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://www.naver.com/',
            'Accept-Language': 'ko-KR,ko;q=0.9'
        }
        res = requests.get(link, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        title_tag = soup.find('meta', property='og:title')
        title = title_tag['content'].strip() if title_tag else '제목 없음'

        content_area = soup.find('div', id='dic_area')
        if content_area:
            paragraphs = content_area.find_all(['p', 'span'])
            content = ' '.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            return title, content

        origin_link_tag = soup.find('a', class_='media_end_head_origin_link')
        if origin_link_tag and origin_link_tag.get('href'):
            return extract_generic_article(origin_link_tag['href'])

        raise ValueError("본문을 찾을 수 없고, 기사 원문 링크도 없음.")
    except Exception as e:
        print(f"❌ 네이버 기사 크롤링 실패: {link}\n{e}")
        return None, None

def extract_generic_article(link):
    try:
        res = requests.get(link, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        title_tag = soup.find("meta", property="og:title")
        title = title_tag["content"].strip() if title_tag and title_tag.get("content") else soup.title.string.strip()

        domain = urlparse(link).netloc
        if 'chosun.com' in domain:
            content_area = soup.find('div', id='news_body_area')
        elif 'donga.com' in domain:
            content_area = soup.find('div', class_='article_txt')
        elif 'mk.co.kr' in domain:
            content_area = soup.find('div', class_='art_txt')
        elif 'joongang.co.kr' in domain:
            content_area = soup.find('div', id='article_body')
        elif 'hani.co.kr' in domain:
            content_area = soup.find('div', class_='article-text')
        else:
            content_area = None

        paragraphs = content_area.find_all('p') if content_area else soup.find_all('p')
        content = ' '.join([p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 30])
        return title, content
    except Exception as e:
        print(f"❌ 외부 기사 크롤링 실패: {link}\n{e}")
        return None, None

def extract_article(link):
    return extract_naver_article(link) if 'n.news.naver.com' in link else extract_generic_article(link)

### 4단계: 뉴스 요약 (GPT)
def summarize_news_articles(titles, contents):
    full_text = ""
    for i in range(len(titles)):
        full_text += f"[{i+1}] {titles[i]}\n{contents[i]}\n\n"

    prompt = f"""
당신은 정치/경제/산업 분야의 전문 뉴스 분석가입니다.
회사 CFO나 CEO가 의사결정을 위해 필요한 심층 분석 요약을 작성합니다.

아래는 여러 뉴스 기사들의 제목과 본문입니다.  
이 내용을 **심층 분석 요약** 형식으로 정리해주세요. 요약은 다음 구조를 반드시 따르세요:

---

1. 📌 **핵심 주제 요약** (1~2문장)

2. 📰 **뉴스 요점 정리**
   - 어떤 사건/행동이 있었는가?
   - 원인은 무엇인가?
   - 주요 인물, 기업, 기관은 누구인가?
   - 기술/산업/시장 맥락은 무엇인가?

3. 📊 **비교 또는 이슈 요약 (필요시 표로)**  
   - 기사 간 유사점/차이점 정리
   - 수치/정책 변화 비교 등

4. 🧠 **결론 및 시사점**
   - 향후 주의 깊게 봐야 할 변화나 흐름
   - 독자가 얻을 수 있는 통찰

---

아래는 분석할 뉴스 전체 내용입니다:

{full_text}

⚠️ 누락된 쟁점이나 보완 설명이 필요한 부분이 있다면 마지막에 따로 언급해주세요.
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 정확하고 깊이 있는 뉴스 요약가입니다."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    return response.choices[0].message.content.strip()

### 5단계: Word 파일 저장
def save_summary_to_word(summary_text, titles, links, news_items, keywords, output_stream, failed_links=None):
    from docx import Document
    from docx.shared import Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    import re
    from urllib.parse import urlparse

    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = '맑은 고딕'
    font.size = Pt(10)

    # 섹션 제목 정의 (14pt Bold)
    section_titles = [
        "핵심 주제 요약",
        "뉴스 요점 정리",
        "비교 또는 이슈 요약",
        "결론 및 시사점"
    ]

    lines = summary_text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # 표 처리
        if line.startswith('|') and line.endswith('|'):
            table_data = []
            while i < len(lines) and lines[i].strip().startswith('|') and lines[i].strip().endswith('|'):
                cells = [cell.strip() for cell in lines[i].strip().split('|')[1:-1]]
                table_data.append(cells)
                i += 1
            table = doc.add_table(rows=0, cols=len(table_data[0]))
            for row_data in table_data:
                row = table.add_row().cells
                for idx, cell in enumerate(row_data):
                    row[idx].text = cell
            continue

        # 14pt Bold 제목 처리
        matched = False
        for title in section_titles:
            if title in line:
                p = doc.add_paragraph()
                run = p.add_run(title)
                run.bold = True
                run.font.size = Pt(14)
                matched = True
                break
        if matched:
            i += 1
            continue

        # 일반 줄 처리, 중간에 **텍스트** 있는 부분은 10pt Bold로 처리
        p = doc.add_paragraph()
        parts = re.split(r'(\*\*.*?\*\*)', line)  # '**텍스트**' 기준으로 나눔
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                clean = part[2:-2]  # ** 제거
                run = p.add_run(clean)
                run.bold = True
                run.font.size = Pt(10)
            else:
                run = p.add_run(part)
                run.font.size = Pt(10)
        i += 1

    # 참고 뉴스 목록
    doc.add_page_break()
    doc.add_paragraph("📎 참고 뉴스 목록", style='Heading 1')

    for idx, (title, link, item) in enumerate(zip(titles, links, news_items), 1):
        p = doc.add_paragraph()
        p.add_run(f"{idx}. ")
        add_hyperlink(p, link, title)
        origin = extract_news_source(link)
        pubdate = extract_pubdate_from_item(item)
        info = f" ({origin}" + (f", {pubdate}" if pubdate else "") + ")"
        p.add_run(info)

    doc.save(output_stream)
    print(f"✅ Word 파일이 저장되었습니다: {output_stream}")

def add_hyperlink(paragraph, url, text):
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)

    new_run = OxmlElement('w:r')
    rPr = OxmlElement('w:rPr')

    color = OxmlElement('w:color')
    color.set(qn('w:val'), '0000FF')
    rPr.append(color)

    underline = OxmlElement('w:u')
    underline.set(qn('w:val'), 'single')
    rPr.append(underline)

    new_run.append(rPr)

    text_elem = OxmlElement('w:t')
    text_elem.text = text
    new_run.append(text_elem)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)

def extract_news_source(link):
    netloc = urlparse(link).netloc
    domain = netloc.replace("www.", "").split(".")[0]
    source_map = {
        "n": "네이버",
        "chosun": "조선일보",
        "donga": "동아일보",
        "mk": "매일경제",
        "joongang": "중앙일보",
        "hani": "한겨레",
        "yna": "연합뉴스",
        "inews24": "아이뉴스24"
    }
    return source_map.get(domain, domain)

def extract_pubdate_from_item(item):
    if "pubDate" in item:
        try:
            dt = datetime.strptime(item["pubDate"], "%a, %d %b %Y %H:%M:%S %z")
            return dt.strftime("%Y-%m-%d")
        except:
            return None
    return None

## 전체 워크플로우 실행 함수
def run_news_summary_workflow(initial_url, start_date, end_date):
    print("▶️ 기사 원문 수집 중...")
    title, content = extract_article_content(initial_url)

    print("▶️ GPT 키워드 추출 중...")
    keywords = extract_keywords_with_gpt(title, content)
    print("🔑 추출된 키워드:", keywords)

    print("▶️ 네이버 뉴스 검색 중...")
    news_items = search_news_naver(keywords, start_date, end_date)

    print("▶️ 날짜 필터링 적용 중...")
    filtered_items = filter_news_by_date(news_items, start_date, end_date)

    if not filtered_items:
        print("❌ 날짜 조건에 맞는 뉴스가 없습니다.")
    else:
        display_news_list(filtered_items)


    print(f"🔍 필터링 후 뉴스 개수: {len(filtered_items)}")
    if not filtered_items:
        print("❌ 필터링된 뉴스가 없습니다. 날짜 범위를 확인해주세요.")
        return  

    display_news_list(filtered_items)

if __name__ == "__main__":
    test_url = "https://n.news.naver.com/article/014/0005371160?cds=news_media_pc"  # 테스트 기사 URL
    start_date = "2025-07-01"
    end_date = "2025-07-02"

    run_news_summary_workflow(test_url, start_date, end_date)
