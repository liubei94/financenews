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
다음은 뉴스 제목과 본문입니다. 핵심 키워드 5개를 한글로만 추출해줘. 
중요한 주제, 인물, 기관, 숫자 기반 키워드도 포함시켜줘.

제목: {title}
본문: {content}
"""
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {'role': 'system', 'content': '당신은 핵심 키워드 추출 도우미입니다.'},
            {'role': 'user', 'content': prompt}
        ]
    )
    return response.choices[0].message.content.strip().split('\n')

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
다음은 여러 뉴스 기사들의 제목과 본문 내용입니다. 이를 종합해서 다음과 같은 형식으로 요약해줘:

1. 제목: 한 줄
2. 본문: A4 1장 분량 요약 (중요 내용은 비교 표로 정리해도 좋음)
3. 결론: 2~3줄 요약

뉴스 기사 전체 내용:
{full_text}
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 전문적인 뉴스 분석 요약 도우미입니다."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

### 5단계: Word 파일 저장
def save_summary_to_word(summary_text, titles, links, news_items, keywords, save_path):
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

    doc.save(save_path)
    print(f"✅ Word 파일이 저장되었습니다: {save_path}")

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
