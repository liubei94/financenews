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
제목과 본문을 참고해 핵심 키워드 5개를 한글로 추출해줘:
제목: {title}
본문: {content}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 키워드 추출기입니다."},
            {"role": "user", "content": prompt}
        ]
    )
    keywords = response.choices[0].message.content.strip().split('\n')
    cleaned = []
    for kw in keywords:
        kw = re.sub(r'^\d+\.\s*', '', kw).strip()  # 숫자. 제거 (1. 키워드 → 키워드)
        if kw:
            cleaned.append(kw)
    return cleaned[:10]  # 최대 10개 제한

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
당신은 경제/산업 분야의 전문 뉴스 분석가입니다.

아래는 여러 뉴스 기사들의 제목과 본문입니다.  
이 내용을 **심층 분석 요약** 형식으로 정리해주세요. 요약은 다음 구조를 반드시 따르세요:

---

1. 📌 **핵심 주제 요약** (1~2문장)

2. 📰 **뉴스 요점 정리**
   - 어떤 사건/행동이 있었는가?
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
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = '맑은 고딕'
    font.size = Pt(10)

    doc.add_paragraph("🔑 주요 키워드: " + ', '.join(keywords))
    doc.add_paragraph("")

    lines = summary_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("제목:"):
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.bold = True
            run.font.size = Pt(14)
        elif line.startswith("결론:") or line.startswith("결론"):
            doc.add_paragraph("")
            p = doc.add_paragraph()
            run = p.add_run(line)
            run.bold = True
            run.font.size = Pt(10)
        elif line.startswith('|') and line.endswith('|'):
            table_data = []
            while line.startswith('|') and line.endswith('|'):
                cells = [cell.strip() for cell in line.strip().split('|')[1:-1]]
                table_data.append(cells)
                lines = lines[1:]
                if not lines:
                    break
                line = lines[0].strip()
            table = doc.add_table(rows=0, cols=len(table_data[0]))
            for row_data in table_data:
                row = table.add_row().cells
                for idx, cell in enumerate(row_data):
                    row[idx].text = cell
            continue
        else:
            p = doc.add_paragraph(line)
            p.style.font.size = Pt(10)

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
