import streamlit as st
import requests
import urllib.parse
import datetime
import math
import json
import os
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import feedparser
import concurrent.futures
from streamlit_autorefresh import st_autorefresh 

# --- 웹페이지 기본 설정 ---
st.set_page_config(page_title="뉴스 모니터링 시스템", layout="wide")

# ==========================================
# 💾 상태 저장 및 복원 로직
# ==========================================
STATE_FILE = "app_state.json"

def load_app_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_app_state():
    state = {
        "run_search": st.session_state.get("run_search", False),
        "selected_portals_key": st.session_state.get("selected_portals_key", ["네이버", "구글", "다음"]),
        "selected_regions_key": st.session_state.get("selected_regions_key", ["대전", "충남"]),
        "keywords_str_key": st.session_state.get("keywords_str_key", "국토교통부|국토부, 대전지방국토관리청, 사건, 사고, 화재, 지진"),
        "display_limit_key": st.session_state.get("display_limit_key", 10),
        "sort_combo_key": st.session_state.get("sort_combo_key", "중요도순"),
        "period_combo_key": st.session_state.get("period_combo_key", "오늘"),
        "refresh_combo_key": st.session_state.get("refresh_combo_key", "1시간"),
        "custom_minutes_key": st.session_state.get("custom_minutes_key", 60),
        "auto_tele_check_key": st.session_state.get("auto_tele_check_key", True)
    }
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
    except Exception as e:
        pass

if 'initialized' not in st.session_state:
    saved = load_app_state()
    st.session_state.run_search = saved.get("run_search", False)
    st.session_state.selected_portals_key = saved.get("selected_portals_key", ["네이버", "구글", "다음"])
    st.session_state.selected_regions_key = saved.get("selected_regions_key", ["대전", "충남"])
    st.session_state.keywords_str_key = saved.get("keywords_str_key", "국토교통부|국토부, 대전지방국토관리청, 사건, 사고, 화재, 지진")
    st.session_state.display_limit_key = saved.get("display_limit_key", 10)
    st.session_state.sort_combo_key = saved.get("sort_combo_key", "중요도순")
    st.session_state.period_combo_key = saved.get("period_combo_key", "오늘")
    st.session_state.refresh_combo_key = saved.get("refresh_combo_key", "1시간")
    st.session_state.custom_minutes_key = saved.get("custom_minutes_key", 60)
    st.session_state.auto_tele_check_key = saved.get("auto_tele_check_key", True)
    st.session_state.last_fetch_time = None
    st.session_state.cached_results = {}
    st.session_state.cached_keywords = []
    st.session_state.last_tele_hour = None
    st.session_state.initialized = True

# --- CSS ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container {padding-top: 2.5rem; padding-bottom: 2rem; max-width: 1400px;}
    .main-header {font-size: 28px; font-weight: 700; color: #1e293b; margin-bottom: 5px;}
    .sub-header {font-size: 14px; color: #64748b; margin-bottom: 30px; border-bottom: 1px solid #e2e8f0; padding-bottom: 15px;}
    .news-item {padding: 4px 0; border-bottom: 1px dashed #f1f5f9;}
    .news-meta {font-size: 12px; color: #64748b; margin-right: 6px;}
    .news-link {text-decoration: none; color: #334155; font-size: 14px; font-weight: 500;}
    .news-link:hover {color: #2563eb; text-decoration: underline;}
    .urgent-tag {color: #e11d48; font-weight: 700; font-size: 12px; margin-right: 4px;}
    .urgent-link {color: #be123c !important;}
    .card-title {font-size: 16px; font-weight: 700; color: #0f172a; margin-bottom: 12px; padding-left: 8px; border-left: 4px solid #3b82f6;}
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
            try:
                dt = parsedate_to_datetime(entry.published)
                dt_date = dt.astimezone(self.kst).date()
                if not (start_date <= dt_date <= end_date): continue
            except: continue
            results.append({"title": entry.title, "link": entry.link, "description": "", "published": dt})
            if len(results) >= limit: break
        if sort_method == 'date': results.sort(key=lambda x: x['published'], reverse=True)
        return results

    def get_naver_news_pool(self, keyword, start_date, end_date, limit=200, sort_method='sim'):
        if not self.naver_client_id or not self.naver_client_secret: return []
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {"X-Naver-Client-Id": self.naver_client_id, "X-Naver-Client-Secret": self.naver_client_secret}
        results = []
        for start in range(1, 1001, 100):
            params = {"query": keyword, "display": 100, "start": start, "sort": "sim" if sort_method == 'sim' else "date"}
            try:
                response = requests.get(url, headers=headers, params=params).json().get('items', [])
                for item in response:
                    title = item['title'].replace('<b>', '').replace('</b>', '')
                    results.append({"title": title, "link": item['link'], "description": ""})
            except: break
            if len(results) >= limit: break
        return results[:limit]

    def get_daum_news_pool(self, keyword, start_date, end_date, limit=200, sort_method='sim'):
        encoded_query = urllib.parse.quote(keyword)
        sd = start_date.strftime("%Y%m%d") + "000000"
        ed = end_date.strftime("%Y%m%d") + "235959"
        results = []
        url = f"https://search.daum.net/search?w=news&q={encoded_query}&sort={'accuracy' if sort_method=='sim' else 'recency'}&period=u&sd={sd}&ed={ed}"
        try:
            soup = BeautifulSoup(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text, 'html.parser')
            for item in soup.select('.item-title a'):
                results.append({"title": item.text.strip(), "link": item.get('href'), "description": ""})
        except: pass
        return results[:limit]

def fetch_single_keyword(keyword, selected_portals, selected_regions, scraper, limit, start_date, end_date, sort_method):
    portal_methods = {"네이버": scraper.get_naver_news_pool, "구글": scraper.get_google_news_pool, "다음": scraper.get_daum_news_pool}
    combined = []
    for p in selected_portals:
        news_pool = portal_methods[p](keyword, start_date, end_date, limit=200, sort_method=sort_method)
        for news in news_pool:
            news['portal'] = p
            news['region'] = next((r for r in selected_regions if r in news['title']), "전체")
            combined.append(news)
    return combined[:limit]

def send_telegram_message(token, chat_id, text):
    if not token: return
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

# --- UI ---
st.markdown("<div class='main-header'>실시간 사건·사고 모니터링</div>", unsafe_allow_html=True)

with st.expander("⚙️ 검색 조건 설정", expanded=True):
    col1, col2 = st.columns(2)
    selected_portals = st.multiselect("검색 포털", ["네이버", "구글", "다음"], key="selected_portals_key")
    selected_regions = st.multiselect("검색 지역", ["서울", "경기", "인천", "대전", "충남", "세종"], key="selected_regions_key")
    keywords_str = st.text_input("검색어 (쉼표로 구분)", key="keywords_str_key")
    display_limit = st.number_input("출력 수", value=10, key="display_limit_key")
    sort_combo = st.selectbox("정렬", ["중요도순", "최신순"], key="sort_combo_key")
    
    col_btn1, col_btn2 = st.columns(2)
    if st.button("🚀 검색 실행"):
        st.session_state.run_search = True
        save_app_state()
        st.rerun()
    if st.button("🛑 중지"):
        st.session_state.run_search = False
        st.rerun()

# --- 결과 출력 ---
if st.session_state.run_search:
    st.spinner("수집 중...")
    scraper = NewsScraper(naver_client_id="5p3Vuu15J3_qo3MMGOLl", naver_client_secret="3Yx_9guJfU")
    keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
    
    for kw in keywords:
        results = fetch_single_keyword(kw, selected_portals, selected_regions, scraper, display_limit, datetime.date.today(), datetime.date.today(), 'sim')
        with st.container(height=480, border=True):
            st.markdown(f"<div class='card-title'>{kw} 모니터링 현황</div>", unsafe_allow_html=True)
            for news in results:
                is_urgent = any(w in news['title'] for w in ["속보", "긴급", "단독"])
                urgent_tag = "<span class='urgent-tag'>[긴급]</span>" if is_urgent else ""
                link_class = "news-link urgent-link" if is_urgent else "news-link"
                st.markdown(f"""
                <div class='news-item'>
                    {urgent_tag}
                    <span class='news-meta'>[{news['region']}][{news['portal']}]</span>
                    <a href='{news['link']}' class='{link_class}' target='_blank'>{news['title']}</a>
                </div>
                """, unsafe_allow_html=True)
