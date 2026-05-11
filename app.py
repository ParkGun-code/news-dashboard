import streamlit as st
import requests
import urllib.parse
import datetime
import math
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import feedparser
import concurrent.futures

# --- 웹페이지 기본 설정 (PC 와이드 화면에 최적화) ---
st.set_page_config(page_title="뉴스 모니터링 시스템", layout="wide")

# --- 🎨 엔터프라이즈급 모던/세련된 커스텀 CSS ---
st.markdown("""
    <style>
    /* 기본 스트림릿 메뉴 숨김 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* 전체 레이아웃 여백 조정 */
    .block-container {
        padding-top: 2.5rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* 메인 타이틀 및 서브 타이틀 디자인 */
    .main-header {
        font-size: 28px;
        font-weight: 700;
        color: #1e293b;
        letter-spacing: -0.5px;
        margin-bottom: 5px;
    }
    .sub-header {
        font-size: 14px;
        color: #64748b;
        margin-bottom: 30px;
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 15px;
    }

    /* 검색 버튼(Primary)을 세련된 블루톤으로 강제 변경 */
    button[kind="primary"] {
        background-color: #2563eb !important; /* 차분한 블루 */
        color: white !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1rem !important;
        transition: all 0.2s ease !important;
    }
    button[kind="primary"]:hover {
        background-color: #1d4ed8 !important; /* 호버 시 조금 더 짙은 블루 */
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06) !important;
    }

    /* 멀티셀렉트 선택된 태그 색상을 파스텔톤/무채색으로 강제 변경 */
    span[data-baseweb="tag"] {
        background-color: #f1f5f9 !important;
        color: #334155 !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 4px !important;
        font-size: 13px !important;
    }

    /* 뉴스 항목 개별 텍스트 및 링크 스타일 */
    .news-item {
        padding: 4px 0; /* 간격을 기존 8px에서 4px로 절반 감소 */
        border-bottom: 1px dashed #f1f5f9;
    }
    .news-item:last-child {
        border-bottom: none;
    }
    .news-meta {
        font-size: 12px;
        color: #64748b;
        margin-right: 6px;
    }
    .news-link {
        text-decoration: none;
        color: #334155;
        font-size: 14px;
        font-weight: 500;
        display: inline-block;
        width: 100%;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        vertical-align: middle;
        transition: color 0.2s ease;
    }
    .news-link:hover {
        color: #2563eb;
        text-decoration: underline;
    }
    
    /* 긴급 뉴스 하이라이트 (너무 쨍하지 않은 레드) */
    .urgent-tag {
        color: #e11d48;
        font-weight: 700;
        font-size: 12px;
        margin-right: 4px;
    }
    .urgent-link {
        color: #be123c !important;
    }
    
    /* 대시보드 카드 제목 */
    .card-title {
        font-size: 16px;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 12px;
        padding-left: 8px;
        border-left: 4px solid #3b82f6;
    }
    </style>
""", unsafe_allow_html=True)

class NewsScraper:
    def __init__(self, naver_client_id="", naver_client_secret=""):
        self.naver_client_id = naver_client_id
        self.naver_client_secret = naver_client_secret
        self.kst = datetime.timezone(datetime.timedelta(hours=9))

    def get_google_news_pool(self, keyword, start_date, end_date, limit=200):
        # 구글 RSS의 날짜 검색 기능 (after: / before: 문법 사용)
        before_date = end_date + datetime.timedelta(days=1)
        query = f"{keyword.replace('&', ' OR ')} after:{start_date.strftime('%Y-%m-%d')} before:{before_date.strftime('%Y-%m-%d')}"
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        
        feed = feedparser.parse(url)
        results = []

        for entry in feed.entries:
            try:
                dt = parsedate_to_datetime(entry.published)
                dt_date = dt.astimezone(self.kst).date()
                if not (start_date <= dt_date <= end_date):
                    continue
            except Exception:
                pass

            title = entry.title
            description = BeautifulSoup(entry.summary, "html.parser").text if hasattr(entry, 'summary') else ""
            results.append({"title": title, "link": entry.link, "description": description})
            if len(results) >= limit: break
        return results

    def get_naver_news_pool(self, keyword, start_date, end_date, limit=200):
        if not self.naver_client_id or not self.naver_client_secret:
            return []
        query = keyword.replace('&', ' ')
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": self.naver_client_id,
            "X-Naver-Client-Secret": self.naver_client_secret
        }
        results = []

        # 네이버 API는 최대 1000개까지 제공하므로, 최대한 깊이 탐색하여 과거 기사를 획득합니다.
        for start in range(1, 1001, 100):
            display = min(100, 1001 - start)
            params = {"query": query, "display": display, "start": start, "sort": "date"}
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                items = response.json().get('items', [])
                if not items: break
                    
                stop_fetching = False
                for item in items:
                    try:
                        dt = parsedate_to_datetime(item['pubDate'])
                        dt_date = dt.astimezone(self.kst).date()
                        # 지정된 종료일보다 최신 기사면 무시하고 다음 기사로 패스
                        if dt_date > end_date:
                            continue
                        # 지정된 시작일보다 더 옛날 기사가 나오면 탐색을 완전히 종료
                        elif dt_date < start_date:
                            stop_fetching = True 
                            continue
                    except Exception:
                        pass

                    title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
                    description = item['description'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
                    results.append({"title": title, "link": item['link'], "description": description})
                
                if stop_fetching or len(results) >= limit: break
            except Exception:
                break
        return results[:limit]

    def get_daum_news_pool(self, keyword, start_date, end_date, limit=200):
        query = keyword.replace('&', ' ')
        encoded_query = urllib.parse.quote(query)
        sd = start_date.strftime("%Y%m%d") + "000000"
        ed = end_date.strftime("%Y%m%d") + "235959"
        
        # 1. 봇 차단을 우회하기 위한 강력한 브라우저 위장 헤더
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        results = []
        max_pages = math.ceil(limit / 10)
        
        for page in range(1, max_pages + 1):
            # 2. period=u (기간 사용자 지정 파라미터) 필수 추가
            url = f"https://search.daum.net/search?w=news&q={encoded_query}&sort=recency&DA=STC&period=u&sd={sd}&ed={ed}&p={page}"
            try:
                response = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 3. 다음 뉴스 웹페이지 구조 변화에 대응하기 위한 다중 태그 탐색
                articles = soup.select('ul.c-list-basic > li') or soup.select('.c-item-content') or soup.select('div.cont_inner')
                if not articles: break
                    
                for article in articles:
                    title_elem = article.select_one('.item-title a') or article.select_one('a.tit_main') or article.select_one('.wrap_tit a')
                    if not title_elem:
                        continue
                        
                    desc_elem = article.select_one('.conts-desc') or article.select_one('p.desc') or article.select_one('.f_eb.desc')
                    
                    title = title_elem.text.strip()
                    link = title_elem.get('href')
                    description = desc_elem.text.strip() if desc_elem else ""
                    
                    if title:
                        results.append({"title": title, "link": link, "description": description})
                        
                if len(results) >= limit: break
            except Exception:
                break
        return results[:limit]

def fetch_single_keyword(keyword, selected_portals, selected_regions, scraper, limit, start_date, end_date):
    portal_methods = {
        "네이버": scraper.get_naver_news_pool,
        "구글": scraper.get_google_news_pool,
        "다음": scraper.get_daum_news_pool
    }
    
    combined_news_pool = []
    effective_regions = selected_regions if selected_regions else ["전체"]
    
    for portal_name in selected_portals:
        fetch_func = portal_methods[portal_name]
        # 기간에 맞춰 여유롭게 탐색 후 필터링 진행
        news_pool = fetch_func(keyword, start_date, end_date, limit=200)
        
        seen_links = set()
        for news in news_pool:
            matched_region = None
            if not selected_regions:
                matched_region = "전체" 
            else:
                for region in selected_regions:
                    if region in news['title'] or region in news['description']:
                        matched_region = region
                        break 
            
            if matched_region and news['link'] not in seen_links:
                news_copy = news.copy()
                news_copy['region'] = matched_region
                news_copy['portal'] = portal_name
                combined_news_pool.append(news_copy)
                seen_links.add(news['link'])
    
    urgent_news = []
    normal_news_by_portal = {p: [] for p in selected_portals}
    
    for news in combined_news_pool:
        if any(w in news['title'] for w in ["속보", "긴급", "단독"]):
            urgent_news.append(news)
        else:
            normal_news_by_portal[news['portal']].append(news)
    
    balanced_normal_by_portal = {}
    for p in selected_portals:
        region_dict = {r: [] for r in effective_regions}
        for n in normal_news_by_portal[p]:
            if n['region'] in region_dict:
                region_dict[n['region']].append(n)
                
        p_mixed = []
        max_len = max((len(v) for v in region_dict.values()), default=0)
        for i in range(max_len):
            for r in effective_regions:
                if i < len(region_dict[r]):
                    p_mixed.append(region_dict[r][i])
        balanced_normal_by_portal[p] = p_mixed
    
    mixed_normal = []
    max_p_len = max((len(v) for v in balanced_normal_by_portal.values()), default=0)
    for i in range(max_p_len):
        for p in selected_portals:
            if i < len(balanced_normal_by_portal[p]):
                mixed_normal.append(balanced_normal_by_portal[p][i])
    
    return (urgent_news + mixed_normal)[:limit]

# ==========================================
# 메인 헤더 (모던 텍스트 기반)
# ==========================================
st.markdown("<div class='main-header'>실시간 사건·사고 모니터링</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Contact me by email in case of any issues.(gun802000@gmail.com)</div>", unsafe_allow_html=True)

# ==========================================
# 상단 컨트롤 패널 (검색 조건 설정)
# ==========================================
with st.expander("⚙️ 검색 조건 설정 (여기를 클릭해서 열거나 닫으세요)", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        selected_portals = st.multiselect("검색 포털", ["네이버", "구글", "다음"], default=["네이버", "구글", "다음"])
    with col2:
        all_regions = ["서울", "경기", "인천", "강원", "대전", "충남", "충북", "세종", "부산", "울산", "대구", "경북", "경남", "전남", "전북", "광주", "제주"]
        selected_regions = st.multiselect("검색 지역 (비워두면 전체 지역 검색)", all_regions, default=["대전", "충남"])

    st.write("") # 간격 띄우기

    col3, col4, col5 = st.columns([3, 1, 2])
    with col3:
        keywords_str = st.text_input("검색어 (쉼표로 구분하여 여러 개 입력)", "국토교통부|국토부, 대전지방국토관리청, 사건, 사고, 화재, 지진")
    with col4:
        display_limit = st.number_input("출력 기사 수", min_value=1, max_value=100, value=15)
    with col5:
        period_
