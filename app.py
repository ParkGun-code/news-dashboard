import streamlit as st
import requests
import urllib.parse
import datetime
import math
import json
import os
import html
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import feedparser
import concurrent.futures
from streamlit_autorefresh import st_autorefresh

# --- 웹페이지 기본 설정 ---
st.set_page_config(page_title="뉴스 모니터링 시스템", layout="wide")

# --- 상태 관리 ---
STATE_FILE = "app_state.json"

def load_app_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
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
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=4)

if 'initialized' not in st.session_state:
    saved = load_app_state()
    for k, v in saved.items(): st.session_state[k] = v
    st.session_state.update({"last_fetch_time": None, "cached_results": {}, "cached_keywords": [], "last_tele_hour": None, "initialized": True})

# --- 클래스 정의 및 로직 생략(NewsScraper 클래스 유지) ---
# [이전 제공된 NewsScraper, fetch_single_keyword, send_telegram_message 함수들을 여기에 그대로 사용하세요]

# --- UI 및 렌더링 ---
st.markdown("## 실시간 뉴스 모니터링")

with st.expander("⚙️ 검색 조건 설정", expanded=True):
    # (컨트롤 패널 설정은 이전과 동일하게 유지)
    pass

if st.session_state.run_search:
    # (크롤링 로직 유지)
    # --- 수정된 렌더링 루프 ---
    cached_keywords = st.session_state.get('cached_keywords', [])
    cached_results = st.session_state.get('cached_results', {})
    
    for i in range(0, len(cached_keywords), 3):
        cols = st.columns(3)
        for j in range(3):
            if i + j < len(cached_keywords):
                kw = cached_keywords[i + j]
                news_list = cached_results.get(kw, [])
                with cols[j].container(height=480, border=True):
                    st.markdown(f"**{kw} 모니터링 현황**")
                    if not news_list:
                        st.write("수집된 데이터 없음")
                    else:
                        for news in news_list:
                            is_urgent = any(w in news['title'] for w in ["속보", "긴급", "단독"])
                            urgent_prefix = "🚨" if is_urgent else "•"
                            
                            st.markdown(
                                f"{urgent_prefix} [{html.escape(news['region'])}] [{html.escape(news['portal'])}] "
                                f"[{html.escape(news['title'])}]({news['link']})",
                                unsafe_allow_html=True
                            )
