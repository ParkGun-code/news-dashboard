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
st.set_page_config(page_title="종합 뉴스 실시간 대시보드", page_icon="🖥️", layout="wide")

# --- 깔끔한 웹사이트 디자인을 위한 커스텀 CSS ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    .news-link {
        text-decoration: none;
        color: #1F2937;
        font-size: 14px;
        display: block;
        padding: 4px 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .news-link:hover {
        color: #2563EB;
        text-decoration: underline;
    }
    .urgent-news {
        color: #DC2626 !important;
        font-weight: bold;
    }
    </style>
""", unsafe_allow_html=True)

class NewsScraper:
    def __init__(self, naver_client_id="", naver_client_secret=""):
        self.naver_client_id = naver_client_id
        self.naver_client_secret = naver_client_secret
        self.kst = datetime.timezone(datetime.timedelta(hours=9))

    def get_google_news_pool(self, keyword, limit=100):
        query = keyword.replace('&', ' OR ') + " when:1d"
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        
        feed = feedparser.parse(url)
        results = []
        today_date = datetime.datetime.now(self.kst).date()

        for entry in feed.entries:
            try:
                dt = parsedate_to_datetime(entry.published)
                dt_kst = dt.astimezone(self.kst)
                if dt_kst.date() != today_date:
                    continue
            except Exception:
                pass

            title = entry.title
            description = BeautifulSoup(entry.summary, "html.parser").text if hasattr(entry, 'summary') else ""
            results.append({"title": title, "link": entry.link, "description": description})
            if len(results) >= limit: break
        return results

    def get_naver_news_pool(self, keyword, limit=100):
        if not self.naver_client_id or not self.naver_client_secret:
            return []
        query = keyword.replace('&', ' ')
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": self.naver_client_id,
            "X-Naver-Client-Secret": self.naver_client_secret
        }
        results = []
        today_date = datetime.datetime.now(self.kst).date()

        for start in range(1, limit + 1, 100):
            display = min(100, limit - start + 1)
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
                        dt_kst = dt.astimezone(self.kst)
                        if dt_kst.date() < today_date:
                            stop_fetching = True 
                            continue
                        elif dt_kst.date() > today_date:
                            continue
                    except Exception:
                        pass

                    title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
                    description = item['description'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
                    results.append({"title": title, "link": item['link'], "description": description})
                
                if stop_fetching: break
            except Exception:
                break
        return results

    def get_daum_news_pool(self, keyword, limit=100):
        query = keyword.replace('&', ' ')
        encoded_query = urllib.parse.quote(query)
        today_str = datetime.datetime.now(self.kst).strftime("%Y%m%d")
        sd = f"{today_str}000000"
        ed = f"{today_str}235959"
        headers = {"User-Agent": "Mozilla/5.0"}
        results = []
        max_pages = math.ceil(limit / 10)
        
        for page in range(1, max_pages + 1):
            url = f"https://search.daum.net/search?w=news&q={encoded_query}&sort=recency&DA=STC&sd={sd}&ed={ed}&p={page}"
            try:
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.text, 'html.parser')
                articles = soup.select('.c-item-content')
                if not articles: break
                    
                for article in articles:
                    title_elem = article.select_one('.item-title .tit-g')
                    desc_elem = article.select_one('.conts-desc')
                    if title_elem:
                        title = title_elem.text.strip()
                        link = title_elem.get('href')
                        description = desc_elem.text.strip() if desc_elem else ""
                        results.append({"title": title, "link": link, "description": description})
                if len(results) >= limit: break
            except Exception:
                break
        return results[:limit]

def fetch_single_keyword(keyword, selected_portals, selected_regions, scraper, limit):
    portal_methods = {
        "네이버": scraper.get_naver_news_pool,
        "구글": scraper.get_google_news_pool,
        "다음": scraper.get_daum_news_pool
    }
    
    combined_news_pool = []
    effective_regions = selected_regions if selected_regions else ["전체"]
    
    for portal_name in selected_portals:
        fetch_func = portal_methods[portal_name]
        news_pool = fetch_func(keyword, limit=100)
        
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
# 메인 헤더 및 상단 컨트롤 패널 (PC 웹사이트 스타일)
# ==========================================
st.title("🖥️ 국토교통부 대전지방국토관리청 실시간 뉴스 모니터링")
st.caption("국토교통부 대전지방국토관리청 건설안전과")

# 검색 설정을 위한 상단 확장 패널
with st.expander("⚙️ 검색 조건 설정 (여기를 클릭해서 열거나 닫으세요)", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        selected_portals = st.multiselect("🌐 검색 포털", ["네이버", "구글", "다음"], default=["네이버", "구글", "다음"])
    with col2:
        all_regions = ["서울", "경기", "인천", "강원", "대전", "충남", "충북", "세종", "부산", "울산", "대구", "경북", "경남", "전남", "전북", "광주", "제주"]
        selected_regions = st.multiselect("📍 검색 지역 (비워두면 전체 기사 검색)", all_regions, default=["대전", "충남"])

    col3, col4, col5, col6 = st.columns([3, 1, 1, 1])
    with col3:
        keywords_str = st.text_input("🔍 검색어 (쉼표 구분)", "사건, 사고, 화재, 붕괴, 지진")
    with col4:
        display_limit = st.number_input("📄 출력 개수", min_value=1, max_value=100, value=15)
    with col5:
        refresh_combo = st.selectbox("⏱ 자동 갱신", ["사용 안함", "1분", "3분", "5분", "10분", "30분", "기타"])
    with col6:
        if refresh_combo == "기타":
            custom_time = st.number_input("기타 시간(분)", min_value=1, value=15)
            refresh_minutes = custom_time
        elif refresh_combo != "사용 안함":
            refresh_minutes = int(refresh_combo.replace("분", ""))
        else:
            refresh_minutes = 0

    do_search = st.button("🚀 뉴스 검색 시작", type="primary", use_container_width=True)

# 자동 갱신 처리 (HTML Meta 태그 삽입 방식)
if refresh_minutes > 0 and do_search:
    st.markdown(f'<meta http-equiv="refresh" content="{refresh_minutes * 60}">', unsafe_allow_html=True)
    st.info(f"⏱ {refresh_minutes}분마다 이 페이지가 자동으로 새로고침 됩니다.")

st.markdown("---")

# ==========================================
# 뉴스 결과 렌더링 영역
# ==========================================
if do_search:
    if not selected_portals:
        st.error("최소 하나 이상의 포털을 선택해주세요.")
        st.stop()
        
    if not keywords_str.strip():
        st.error("검색어를 입력해주세요.")
        st.stop()

    raw_keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    keywords = []
    for k in raw_keywords:
        if k not in keywords: keywords.append(k)

    scraper = NewsScraper(
        naver_client_id="5p3Vuu15J3_qo3MMGOLl", 
        naver_client_secret="3Yx_9guJfU"
    )

    with st.spinner("웹에서 실시간으로 기사를 수집하고 필터링하고 있습니다..."):
        results_dict = {}
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_kw = {executor.submit(fetch_single_keyword, kw, selected_portals, selected_regions, scraper, display_limit): kw for kw in keywords}
            for future in concurrent.futures.as_completed(future_to_kw):
                kw = future_to_kw[future]
                try:
                    results_dict[kw] = future.result()
                except Exception as e:
                    st.error(f"{kw} 검색 중 오류 발생: {e}")

    # PC 모니터 폭에 최적화하여 한 줄에 3개씩 배치되도록 설정
    num_kw = len(keywords)
    columns_per_row = 3
    
    # 3개씩 묶어서 행(Row) 생성
    for i in range(0, num_kw, columns_per_row):
        cols = st.columns(columns_per_row)
        for j in range(columns_per_row):
            if i + j < num_kw:
                kw = keywords[i + j]
                news_list = results_dict.get(kw, [])
                
                with cols[j]:
                    st.markdown(f"#### 📂 [{kw}] 실시간 현황")
                    
                    # 스크롤 가능한 컨테이너 (고정 높이)
                    with st.container(height=500):
                        if not news_list:
                            st.info("수집된 뉴스가 없습니다.")
                        else:
                            for news in news_list:
                                title = news['title']
                                link = news['link']
                                portal = news['portal']
                                region = news['region']
                                
                                prefix = f"[{region}][{portal}]" if selected_regions else f"[{portal}]"
                                is_urgent = any(w in title for w in ["속보", "긴급", "단독"])
                                
                                # HTML title 속성을 이용해 마우스 오버 시 툴팁(말풍선)으로 전체 글자 표시
                                tooltip_text = f"{prefix} {title}".replace("'", "&apos;").replace('"', '&quot;')
                                
                                if is_urgent:
                                    css_class = "news-link urgent-news"
                                    display_text = f"🚨 [긴급] {prefix} {title}"
                                else:
                                    css_class = "news-link"
                                    display_text = f"• {prefix} {title}"
                                    
                                st.markdown(f"<a href='{link}' class='{css_class}' target='_blank' title='{tooltip_text}'>{display_text}</a>", unsafe_allow_html=True)
                                
                    st.markdown("<br>", unsafe_allow_html=True)

    st.success(f"✅ 검색 및 웹 출력 완료! (기준 시간: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
