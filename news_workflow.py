# news_workflow.py

import requests
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
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
import asyncio
import httpx
from tqdm.asyncio import tqdm

# Load environment variables
load_dotenv()

# 비동기 OpenAI 클라이언트 초기화
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")


### 기능 함수들 (Streamlit에서 호출)


def extract_initial_article_content(url):
    """스크립트 시작 시 기준이 되는 첫 기사를 동기적으로 가져옵니다."""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("h2", class_="media_end_head_headline")
        title = title_tag.get_text(strip=True) if title_tag else "제목 없음"
        content_tag = soup.select_one("article#dic_area, div#newsct_article")
        paragraphs = content_tag.find_all("p") if content_tag else []
        content = " ".join([p.get_text(strip=True) for p in paragraphs])
        return title, content
    except requests.RequestException as e:
        print(f"❌ 초기 기사 추출 실패: {e}")
        raise  # 에러를 다시 발생시켜 상위 호출자(Streamlit)가 처리하도록 함


async def extract_keywords_with_gpt(title, content):
    """GPT를 사용해 비동기적으로 핵심 키워드를 추출합니다."""
    prompt = f"""
다음은 뉴스의 제목과 본문입니다. 이 기사의 핵심 주제를 가장 잘 나타내는 키워드 3개를 한글로 추출해주세요.
- 제목에 등장하는 단어나 표현을 우선 고려해 키워드를 선택해주세요.
- 본문 전체를 참고하되, 주제를 잘 대표하는 단어를 뽑아주세요.
- 각 키워드는 명사 형태로 간결하게 제시해주세요.

제목: {title}
본문: {content}
"""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 핵심 키워드 추출 전문가입니다. 가장 중요한 단어 3개를 정확히 추출하세요.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        keywords_text = response.choices[0].message.content.strip()
        cleaned_keywords = [
            re.sub(r"^\s*[\d\.\-]+\s*", "", kw).strip()
            for kw in keywords_text.split("\n")
        ]
        return [kw for kw in cleaned_keywords if kw][:3]
    except Exception as e:
        print(f"❌ GPT 키워드 추출 중 오류 발생: {e}")
        raise


def search_news_naver(keywords, display=50):
    """네이버 API를 통해 관련 뉴스를 검색합니다."""
    query = " ".join(keywords)
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": "date"}
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()["items"]
    except requests.RequestException as e:
        print(f"⚠️ 네이버 API 요청 실패: {e}")
        raise


def filter_news_by_date(news_items, start_date, end_date):
    """검색된 뉴스를 지정된 날짜 범위로 필터링합니다."""
    filtered_items = []
    for item in news_items:
        pub_date_str = item.get("pubDate")
        if not pub_date_str:
            continue
        try:
            pub_date = datetime.strptime(
                pub_date_str, "%a, %d %b %Y %H:%M:%S %z"
            ).date()
            if start_date <= pub_date <= end_date:
                filtered_items.append(item)
        except ValueError:
            continue
    return filtered_items


# --- 비동기 처리 핵심 로직 ---


async def extract_article_content_async(link, session):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = await session.get(
            link, headers=headers, timeout=15, follow_redirects=True
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        content_area = soup.select_one("article#dic_area, div#newsct_article")
        if content_area:
            title_tag = soup.find("meta", property="og:title")
            title = title_tag["content"].strip() if title_tag else "제목 없음"
            content = " ".join(
                p.get_text(strip=True)
                for p in content_area.find_all("p")
                if p.get_text(strip=True)
            )
            return title, content
        title_tag = soup.find("meta", property="og:title")
        title = title_tag["content"].strip() if title_tag else soup.title.string.strip()
        selectors = [
            "div.article_body",
            "div.article_view",
            "div#article-body",
            "div#news_body_area",
            "div.article_txt",
            "div#article_body",
            "div.article-text",
            "section.article-body",
        ]
        content_area = soup.select_one(", ".join(selectors))
        paragraphs = (
            content_area.find_all("p")
            if content_area
            else soup.find("body").find_all("p")
        )
        content = " ".join(
            [
                p.get_text(strip=True)
                for p in paragraphs
                if len(p.get_text(strip=True)) > 50
            ]
        )
        return title, content
    except Exception:
        return None, None


async def summarize_individual_article_async(title, content):
    prompt = f"""
다음 뉴스 기사의 핵심 내용을 아래 항목에 맞추어 간결하게 요약해줘. 각 항목은 한두 문장으로 작성해줘.
- **사건/주제**: \n- **주요 인물/기관**: \n- **핵심 주장/내용**: \n- **결과/영향**:
---
제목: {title}\n본문: {content}
"""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 뉴스 분석가입니다. 기사의 핵심만 정확하게 추출하여 요약합니다.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


async def process_article_task(item, session, semaphore):
    async with semaphore:
        link = item.get("originallink", item.get("link"))
        title, content = await extract_article_content_async(link, session)
        if not title or not content:
            return {"status": "failed", "reason": "크롤링 실패", "link": link}
        summary = await summarize_individual_article_async(title, content)
        if not summary:
            return {"status": "failed", "reason": "개별 요약 실패", "link": link}
        return {
            "status": "success",
            "title": re.sub("<.*?>", "", item["title"]),
            "link": link,
            "original_item": item,
            "summary": summary,
        }


async def synthesize_final_report(summaries):
    full_summary_text = ""
    for i, summary_data in enumerate(summaries, 1):
        full_summary_text += f"### 뉴스 {i}: {summary_data['title']}\n{summary_data['summary']}\n\n---\n\n"
    prompt = f"""
당신은 정치/경제/산업 분야의 최고 수준의 전문 분석가입니다. 여러 뉴스 기사의 핵심 요약본들을 바탕으로, 회사 CFO나 CEO가 의사결정을 위해 참고할 심층 분석 보고서를 작성합니다.
다음 구조를 반드시 지켜 보고서를 작성해주세요.
1.  **📌 Executive Summary (핵심 요약)**
    *   전체 상황을 1~2 문장으로 요약합니다.
2.  **📰 Key Developments (주요 동향 및 사실 분석)**
    *   어떤 사건/행동이 있었는지 종합적으로 설명합니다.
    *   공통적으로 드러나는 원인과 배경은 무엇입니까?
    *   핵심적인 플레이어(인물, 기업, 기관)는 누구이며, 그들의 입장은 무엇입니까?
3.  **📊 Comparative Analysis (비교 분석 및 이슈 심층 탐구)**
    *   기사들 간의 관점 차이나 상충되는 정보가 있다면 비교 분석합니다.
    *   수치, 데이터, 정책 변화 등 중요한 포인트를 표(Table) 형식으로 정리하여 시각적 이해를 돕습니다. (필요시)
4.  **🧠 Conclusion & Strategic Implications (결론 및 전략적 시사점)**
    *   이러한 흐름이 향후 시장/산업/정책에 미칠 영향은 무엇입니까?
    *   우리 조직이 주의 깊게 관찰해야 할 리스크와 기회 요인은 무엇입니까?
    *   독자가 얻어야 할 최종적인 통찰(Insight)을 제시합니다.
---
{full_summary_text}
"""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "당신은 여러 정보를 종합하여 깊이 있는 인사이트를 도출하는 전문 분석가입니다.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ 최종 보고서 생성 중 오류: {e}")
        raise


async def run_analysis_and_synthesis_async(filtered_items):
    """Streamlit에서 호출할 메인 비동기 처리 함수"""
    semaphore = asyncio.Semaphore(10)
    async with httpx.AsyncClient() as session:
        tasks = [
            process_article_task(item, session, semaphore) for item in filtered_items
        ]
        # Streamlit 환경에서는 tqdm이 콘솔에만 출력되므로 UI에는 직접 보이지 않음
        results = await asyncio.gather(*tasks)

    successful_results = [r for r in results if r and r["status"] == "success"]
    failed_results = [r for r in results if not r or r["status"] == "failed"]

    if not successful_results:
        return None, [], []

    final_report = await synthesize_final_report(successful_results)
    return final_report, successful_results, failed_results


# --- Word 저장 로직 ---
def save_summary_to_word(summary_text, successful_results, output_stream):
    doc = Document()
    style = doc.styles["Normal"]
    font = style.font
    font.name = "맑은 고딕"
    style.paragraph_format.line_spacing = 1.5
    style.paragraph_format.space_after = Pt(5)

    lines = summary_text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("### "):
            p = doc.add_paragraph()
            run = p.add_run(line.replace("### ", ""))
            run.bold = True
            run.font.size = Pt(12)
        elif line.startswith("## "):
            p = doc.add_paragraph()
            run = p.add_run(line.replace("## ", ""))
            run.bold = True
            run.font.size = Pt(14)
        elif line.startswith("# "):
            p = doc.add_paragraph()
            run = p.add_run(line.replace("# ", ""))
            run.bold = True
            run.font.size = Pt(16)
        elif line.startswith("* "):
            p = doc.add_paragraph(style="List Bullet")
            parts = re.split(r"(\*\*.*?\*\*)", line.replace("* ", ""))
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)
        else:
            p = doc.add_paragraph()
            parts = re.split(r"(\*\*.*?\*\*)", line)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)

    doc.add_page_break()
    p = doc.add_paragraph()
    run = p.add_run("📎 참고 뉴스 목록")
    run.bold = True
    run.font.size = Pt(16)

    for idx, result in enumerate(successful_results, 1):
        p = doc.add_paragraph()
        p.add_run(f"{idx}. ")
        add_hyperlink(p, result["link"], result["title"])
        origin = extract_news_source(result["link"])
        pubdate = extract_pubdate_from_item(result["original_item"])
        info = f" ({origin}" + (f", {pubdate}" if pubdate else "") + ")"
        p.add_run(info)

    doc.save(output_stream)


def add_hyperlink(paragraph, url, text):
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0000FF")
    rPr.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rPr.append(underline)
    new_run.append(rPr)
    text_elem = OxmlElement("w:t")
    text_elem.text = text
    new_run.append(text_elem)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


def extract_news_source(link):
    try:
        netloc = urlparse(link).netloc
        parts = netloc.replace("www.", "").split(".")
        domain = parts[-2] if len(parts) > 1 else parts[0]
        source_map = {
            "chosun": "조선일보",
            "donga": "동아일보",
            "mk": "매일경제",
            "joongang": "중앙일보",
            "hani": "한겨레",
            "yna": "연합뉴스",
            "inews24": "아이뉴스24",
            "fnnews": "파이낸셜뉴스",
            "naver": "네이버뉴스",
        }
        return source_map.get(domain, domain)
    except:
        return "알 수 없는 출처"


def extract_pubdate_from_item(item):
    if "pubDate" in item:
        try:
            dt = datetime.strptime(item["pubDate"], "%a, %d %b %Y %H:%M:%S %z")
            return dt.strftime("%Y-%m-%d")
        except:
            return None
    return None
