import streamlit as st
import requests
import urllib.parse
import datetime
import math
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import feedparser
import concurrent.futures
from streamlit_autorefresh import st_autorefresh 

# --- 웹페이지 기본 설정 (PC 와이드 화면에 최적화) ---
st.set_page_config(page_title="뉴스 모니터링 시스템", layout="wide")

# --- 💡 (중요) 검색 상태와 결과값을 기억하는 세션 스토리지 초기화 ---
if 'run_search' not in st.session_state:
    st.session_state.run_search = False
if 'last_fetch_time' not in st.session_state:
    st.session_state.last_fetch_time = None
if 'cached_results' not in st.session_state:
    st.session_state.cached_results = {}
if 'cached_keywords' not in st.session_state:
    st.session_state.cached_keywords = []

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
        padding: 4px 0; /* 간격 축소 유지 */
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
    
    /* 긴급 뉴스 하이라이트 */
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

    def get_google_news_pool(self, keyword, start_date, end_date, limit=200, sort_method='sim'):
        before_date = end_date + datetime.timedelta(days=1)
        query = f"{keyword.replace('&', ' OR ')} after:{start_date.strftime('%Y-%m-%d')} before:{before_date.strftime('%Y-%m-%d')}"
        encoded_query = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        
        feed = feedparser.parse(url)
        results = []

        for entry in feed.entries:
            dt = datetime.datetime.min.replace(tzinfo=self.kst)
            try:
                dt = parsedate_to_datetime(entry.published)
                dt_date = dt.astimezone(self.kst).date()
                if not (start_date <= dt_date <= end_date):
                    continue
            except Exception:
                pass

            title = entry.title
            description = BeautifulSoup(entry.summary, "html.parser").text if hasattr(entry, 'summary') else ""
            results.append({"title": title, "link": entry.link, "description": description, "published": dt})
            if len(results) >= limit: break
            
        if sort_method == 'date':
            results.sort(key=lambda x: x['published'], reverse=True)
            
        return results

    def get_naver_news_pool(self, keyword, start_date, end_date, limit=200, sort_method='sim'):
        if not self.naver_client_id or not self.naver_client_secret:
            return []
        query = keyword.replace('&', ' ')
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": self.naver_client_id,
            "X-Naver-Client-Secret": self.naver_client_secret
        }
        results = []

        for start in range(1, 1001, 100):
            display = min(100, 1001 - start)
            sort_param = "sim" if sort_method == 'sim' else "date"
            params = {"query": query, "display": display, "start": start, "sort": sort_param}
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
                        
                        if sort_method == 'date':
                            if dt_date > end_date:
                                continue
                            elif dt_date < start_date:
                                stop_fetching = True 
                                continue
                        else:
                            if not (start_date <= dt_date <= end_date):
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

    def get_daum_news_pool(self, keyword, start_date, end_date, limit=200, sort_method='sim'):
        query = keyword.replace('&', ' ')
        encoded_query = urllib.parse.quote(query)
        sd = start_date.strftime("%Y%m%d") + "000000"
        ed = end_date.strftime("%Y%m%d") + "235959"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        results = []
        max_pages = math.ceil(limit / 10)
        
        for page in range(1, max_pages + 1):
            sort_param = "accuracy" if sort_method == 'sim' else "recency"
            url = f"https://search.daum.net/search?w=news&q={encoded_query}&sort={sort_param}&DA=STC&period=u&sd={sd}&ed={ed}&p={page}"
            try:
                response = requests.get(url, headers=headers, timeout=5)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                articles = soup.select('.c-item-content') or soup.select('ul.c-list-basic > li') or soup.select('.wrap_cont')
                if not articles: break
                    
                for article in articles:
                    title_elem = article.select_one('.item-title a') or article.select_one('a.tit_main') or article.select_one('.tit-g a') or article.select_one('strong > a')
                    desc_elem = article.select_one('.conts-desc') or article.select_one('.desc') or article.select_one('p.f_eb')
                    
                    if title_elem and title_elem.text.strip():
                        title = title_elem.text.strip()
                        link = title_elem.get('href')
                        description = desc_elem.text.strip() if desc_elem else ""
                        results.append({"title": title, "link": link, "description": description})
                if len(results) >= limit: break
            except Exception:
                break
        return results[:limit]

def fetch_single_keyword(keyword, selected_portals, selected_regions, scraper, limit, start_date, end_date, sort_method):
    portal_methods = {
        "네이버": scraper.get_naver_news_pool,
        "구글": scraper.get_google_news_pool,
        "다음": scraper.get_daum_news_pool
    }
    
    combined_news_pool = []
    effective_regions = selected_regions if selected_regions else ["전체"]
    
    for portal_name in selected_portals:
        fetch_func = portal_methods[portal_name]
        news_pool = fetch_func(keyword, start_date, end_date, limit=200, sort_method=sort_method)
        
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
# 메인 헤더
# ==========================================
st.markdown("<div class='main-header'>실시간 사건·사고 모니터링</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Contact me by email in case of any issues. (gun802000@gmail.com)</div>", unsafe_allow_html=True)

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

    st.write("") 

    col3, col4, col_sort, col5 = st.columns([3, 1, 1, 1.5])
    with col3:
        keywords_str = st.text_input("검색어 (쉼표로 구분하여 여러 개 입력)", "국토교통부|국토부, 대전지방국토관리청, 사건, 사고, 화재, 지진")
    with col4:
        display_limit = st.number_input("출력 기사 수", min_value=1, max_value=100, value=15)
    with col_sort:
        sort_combo = st.selectbox("정렬 기준", ["중요도순", "최신순"])
    with col5:
        period_combo = st.selectbox("검색 기간", ["오늘", "일주일", "한달", "일년", "기간 선택"])

    kst = datetime.timezone(datetime.timedelta(hours=9))
    today_kst = datetime.datetime.now(kst).date()

    col6, col7, col8 = st.columns([3, 1.5, 1.5])
    with col6:
        if period_combo == "기간 선택":
            date_range = st.date_input("날짜 지정 (시작일 - 종료일)", 
                                       value=(today_kst - datetime.timedelta(days=7), today_kst),
                                       max_value=today_kst)
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
            elif isinstance(date_range, tuple) and len(date_range) == 1:
                start_date = end_date = date_range[0]
            else:
                start_date = end_date = today_kst
        else:
            end_date = today_kst
            if period_combo == "오늘":
                start_date = end_date
            elif period_combo == "일주일":
                start_date = end_date - datetime.timedelta(days=7)
            elif period_combo == "한달":
                start_date = end_date - datetime.timedelta(days=30)
            elif period_combo == "일년":
                start_date = end_date - datetime.timedelta(days=365)
            
            st.text_input("적용된 기간 (자동 계산됨)", f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}", disabled=True)

    with col7:
        refresh_combo = st.selectbox("자동 갱신 주기", ["사용 안함", "1분", "3분", "5분", "10분", "30분", "기타"])
    with col8:
        if refresh_combo == "기타":
            refresh_minutes = st.number_input("갱신(분)", min_value=1, value=15)
        elif refresh_combo != "사용 안함":
            refresh_minutes = int(refresh_combo.replace("분", ""))
        else:
            refresh_minutes = 0

    st.write("")
    
    # 💡 뉴스 검색 실행 시 즉시 크롤링을 수행하도록 last_fetch_time을 초기화합니다.
    if st.button("뉴스 검색 실행", type="primary", use_container_width=True):
        st.session_state.run_search = True
        st.session_state.last_fetch_time = None

# ==========================================
# 자동 갱신 및 뉴스 렌더링 영역
# ==========================================

if st.session_state.run_search:
    kst = datetime.timezone(datetime.timedelta(hours=9))
    now_time = datetime.datetime.now(kst)
    
    # --- 스마트 폴링 (Smart Polling) 로직 ---
    # 브라우저는 지연 현상을 막기 위해 30초(30000ms)마다 파이썬을 가볍게 찔러 동기화만 시킵니다.
    if refresh_minutes > 0:
        st_autorefresh(interval=30 * 1000, key="news_autorefresh")
        
    # 파이썬 내부에서 '현재 시간 - 마지막 갱신 시간'의 절대적 차이를 계산하여 정확한 주기에만 크롤링을 수행합니다.
    do_crawl = False
    if st.session_state.last_fetch_time is None:
        do_crawl = True
    elif refresh_minutes > 0:
        diff_seconds = (now_time - st.session_state.last_fetch_time).total_seconds()
        # 설정한 주기에서 5초 정도의 여유를 두어 밀림 없이 갱신되도록 보장합니다.
        if diff_seconds >= (refresh_minutes * 60 - 5):
            do_crawl = True

    # 갱신 주기가 도래했을 때만 무거운 크롤링 로직을 실행합니다.
    if do_crawl:
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
        
        sort_method_val = 'sim' if sort_combo == "중요도순" else 'date'

        with st.spinner(f"[{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}] 구간의 기사를 수집하고 있습니다..."):
            results_dict = {}
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_to_kw = {executor.submit(fetch_single_keyword, kw, selected_portals, selected_regions, scraper, display_limit, start_date, end_date, sort_method_val): kw for kw in keywords}
                for future in concurrent.futures.as_completed(future_to_kw):
                    kw = future_to_kw[future]
                    try:
                        results_dict[kw] = future.result()
                    except Exception as e:
                        st.error(f"{kw} 검색 중 오류 발생: {e}")
        
        # 💡 성공적으로 수집이 완료되면 세션 저장소에 결과를 갱신합니다.
        st.session_state.cached_results = results_dict
        st.session_state.last_fetch_time = now_time
        st.session_state.cached_keywords = keywords
        
    st.markdown("<br>", unsafe_allow_html=True)

    # 항상 세션 저장소에 캐싱된 데이터(최신 결과)를 기반으로 화면에 그립니다.
    cached_keywords = st.session_state.get('cached_keywords', [])
    cached_results = st.session_state.get('cached_results', {})
    last_fetch_time = st.session_state.get('last_fetch_time')
    
    current_time_str = last_fetch_time.strftime('%Y-%m-%d %H:%M:%S') if last_fetch_time else "방금"
    
    if refresh_minutes > 0:
        st.caption(f"⏱ 안내: 설정된 {refresh_minutes}분 주기로 데이터를 자동 수집합니다. (최근 수집 완료 시간: {current_time_str})")
    else:
        st.caption(f"✅ 최근 수집 완료 시간: {current_time_str}")

    num_kw = len(cached_keywords)
    columns_per_row = 3
    
    for i in range(0, num_kw, columns_per_row):
        cols = st.columns(columns_per_row)
        for j in range(columns_per_row):
            if i + j < num_kw:
                kw = cached_keywords[i + j]
                news_list = cached_results.get(kw, [])
                
                with cols[j]:
                    with st.container(height=480, border=True):
                        st.markdown(f"<div class='card-title'>{kw} 모니터링 현황</div>", unsafe_allow_html=True)
                        
                        if not news_list:
                            st.markdown("<div style='color:#94a3b8; font-size:14px; margin-top:20px;'>해당 기간에 수집된 데이터가 없습니다.</div>", unsafe_allow_html=True)
                        else:
                            html_content = ""
                            for news in news_list:
                                title = news['title']
                                link = news['link']
                                portal = news['portal']
                                region = news['region']
                                
                                prefix = f"[{region}][{portal}]" if selected_regions else f"[{portal}]"
                                is_urgent = any(w in title for w in ["속보", "긴급", "단독"])
                                tooltip_text = f"{prefix} {title}".replace("'", "&apos;").replace('"', '&quot;')
                                
                                if is_urgent:
                                    html_content += f"""
                                    <div class='news-item'>
                                        <span class='urgent-tag'>[긴급]</span>
                                        <span class='news-meta'>{prefix}</span>
                                        <a href='{link}' class='news-link urgent-link' target='_blank' title='{tooltip_text}'>{title}</a>
                                    </div>
                                    """
                                else:
                                    html_content += f"""
                                    <div class='news-item'>
                                        <span class='news-meta'>{prefix}</span>
                                        <a href='{link}' class='news-link' target='_blank' title='{tooltip_text}'>{title}</a>
                                    </div>
                                    """
                            
                            st.markdown(html_content, unsafe_allow_html=True)
