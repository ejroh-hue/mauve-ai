"""네이버 금융 뉴스 크롤링 + DART 공시 데이터"""

import os
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup, Tag

from src.models import NewsItem

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_naver_search_news(stock_name: str, max_items: int = 5) -> list[NewsItem]:
    """네이버 뉴스 검색으로 종목 관련 뉴스를 가져옵니다."""
    try:
        resp = requests.get(
            "https://search.naver.com/search.naver",
            params={"where": "news", "query": stock_name, "sort": "1"},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")

        # n.news.naver.com/mnews/article 링크 = "네이버뉴스" 연결 링크 → 5단계 위가 article container
        all_a = soup.find_all("a", href=True)
        article_anchors = [
            a for a in all_a
            if "n.news.naver.com/mnews/article" in a.get("href", "")
        ]

        news_items = []
        seen_titles: set[str] = set()

        for a_tag in article_anchors:
            if len(news_items) >= max_items:
                break

            # 5단계 위 = article container
            node = a_tag
            for _ in range(5):
                if node.parent:
                    node = node.parent
            if not isinstance(node, Tag):
                continue

            children = [c for c in node.children if isinstance(c, Tag)]
            if len(children) < 2:
                continue

            # 출처/날짜: profile div (children[0])
            profile_div = children[0]
            spans = profile_div.find_all("span", recursive=True)
            source = spans[0].get_text(strip=True) if spans else ""
            time_spans = [
                s for s in spans
                if any(k in s.get_text() for k in ["전", "시간", "일", ":"])
            ]
            pub_time = time_spans[0].get_text(strip=True) if time_spans else datetime.now().strftime("%Y-%m-%d")

            # 제목: title div (children[1]) 내 vertical layout의 첫 번째 a 태그
            title_div = children[1]
            vert_layout = title_div.find("div", class_=lambda c: c and "sds-comps-vertical-layout" in c)
            if not vert_layout:
                continue
            title_a = vert_layout.find("a")
            if not title_a:
                continue
            title = title_a.get_text(strip=True)

            # 요약: 두 번째 a 태그
            all_a_in_vert = vert_layout.find_all("a")
            summary = all_a_in_vert[1].get_text(strip=True) if len(all_a_in_vert) > 1 else ""

            if not title or len(title) < 5 or title in seen_titles:
                continue
            seen_titles.add(title)

            news_items.append(NewsItem(
                title=title,
                summary=summary[:200],
                date=pub_time,
                source=source,
            ))

        return news_items

    except Exception as e:
        print(f"    [뉴스] 네이버 검색 크롤링 실패: {e}")
        return []


def fetch_dart_disclosures(ticker: str, max_items: int = 3) -> list[NewsItem]:
    """DART 전자공시에서 종목 관련 공시를 가져옵니다.
    DART_API_KEY 환경변수가 필요합니다 (opendart.fss.or.kr에서 무료 발급).
    """
    api_key = os.environ.get("DART_API_KEY", "")
    if not api_key:
        return []

    url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "crtfc_key": api_key,
        "corp_code": "",   # 종목코드로 corp_code 조회 필요
        "bgn_de": (datetime.now().strftime("%Y%m%d")[:6] + "01"),  # 이번 달 1일부터
        "end_de": datetime.now().strftime("%Y%m%d"),
        "last_reprt_at": "N",
        "pblntf_ty": "A",  # 정기공시
        "page_count": max_items,
    }

    # 1단계: 종목코드 → corp_code 변환
    corp_code = _get_dart_corp_code(ticker, api_key)
    if not corp_code:
        return []

    params["corp_code"] = corp_code

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "000":
            return []

        items = []
        for item in data.get("list", [])[:max_items]:
            title = item.get("report_nm", "")
            date = item.get("rcept_dt", "")
            source = f"DART/{item.get('pblntf_detail_ty', '')}"

            if date:
                date = f"{date[:4]}-{date[4:6]}-{date[6:]}"

            if title:
                items.append(NewsItem(
                    title=f"[공시] {title}",
                    summary="",
                    date=date,
                    source=source,
                ))
        return items

    except Exception as e:
        print(f"    [DART] 공시 조회 실패: {e}")
        return []


def _get_dart_corp_code(ticker: str, api_key: str) -> str:
    """종목코드(6자리) → DART corp_code 변환."""
    # corp_code는 DART 고유 식별자 (8자리)
    # 전체 목록에서 종목코드로 검색
    url = "https://opendart.fss.or.kr/api/company.json"
    params = {
        "crtfc_key": api_key,
        "stock_code": ticker,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "000":
            return data.get("corp_code", "")
    except Exception:
        pass
    return ""


def get_news(ticker: str, stock_name: str, max_items: int = 5) -> list[NewsItem]:
    """종목 뉴스를 가져옵니다 (네이버 검색 + DART 공시 병합)."""
    items: list[NewsItem] = []

    # 1차: 네이버 뉴스 검색
    search_items = fetch_naver_search_news(stock_name, max_items)
    items.extend(search_items)

    # 2차: DART 공시 (API 키 있을 때만)
    if os.environ.get("DART_API_KEY"):
        dart_items = fetch_dart_disclosures(ticker, max_items=2)
        existing_titles = {i.title for i in items}
        for di in dart_items:
            if di.title not in existing_titles:
                items.append(di)

    return items[:max_items]


def format_news_for_prompt(items: list[NewsItem], max_chars: int = 2000) -> str:
    """뉴스 목록을 LLM 프롬프트용 텍스트로 변환합니다."""
    if not items:
        return "최근 관련 뉴스가 없습니다."

    lines = []
    total_len = 0
    for i, item in enumerate(items, 1):
        line = f"{i}. [{item.source}] {item.title}"
        if item.summary:
            line += f"\n   {item.summary}"
        if item.date:
            line += f" ({item.date})"

        if total_len + len(line) > max_chars:
            break
        lines.append(line)
        total_len += len(line)

    return "\n".join(lines)
