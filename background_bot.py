import requests
import urllib.parse
import datetime
import math
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import feedparser

# ==========================================
# ⚙️ 텔레그램 및 검색 설정 (이 부분을 수정하세요)
# ==========================================
TELEGRAM_TOKEN = "8921848994:AAHSDoeMSiAMPQYEMyIaYkNI110gzADesYM"
CHAT_ID = "-1003880927818"

# 검색할 키워드 목록
KEYWORDS = ["국토교통부", "대전지방국토관리청", "사건", "사고", "화재", "지진"]

# 전송할 기사 개수
DISPLAY_LIMIT = 10

# ==========================================

class NewsScraper:
    def __init__(self):
        self.kst = datetime.timezone(datetime.timedelta(hours=9))

    def get_google_news_pool(self, keyword, limit=100):
        query = keyword.replace('&', ' OR ') + " when:1d"
        encoded_query = urllib.parse.quote(query)
        url = f"[https://news.google.com/rss/search?q=](https://news.google.com/rss/search?q=){encoded_query}&hl=ko&gl=KR&ceid=KR:ko"
        feed = feedparser.parse(url)
        results = []
        for entry in feed.entries:
            title = entry.title
            results.append({"title": title, "link": entry.link, "portal": "구글"})
            if len(results) >= limit: break
        return results

    def get_naver_news_pool(self, keyword, limit=100):
        # 네이버 API 키 (기존 키 사용)
        client_id = "5p3Vuu15J3_qo3MMGOLl"
        client_secret = "3Yx_9guJfU"
        query = keyword.replace('&', ' ')
        url = "[https://openapi.naver.com/v1/search/news.json](https://openapi.naver.com/v1/search/news.json)"
        headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
        params = {"query": query, "display": limit, "start": 1, "sort": "date"} # 최신순
        
        results = []
        try:
            response = requests.get(url, headers=headers, params=params)
            items = response.json().get('items', [])
            for item in items:
                title = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
                results.append({"title": title, "link": item['link'], "portal": "네이버"})
        except Exception:
            pass
        return results

    def get_daum_news_pool(self, keyword, limit=100):
        query = keyword.replace('&', ' ')
        encoded_query = urllib.parse.quote(query)
        headers = {"User-Agent": "Mozilla/5.0"}
        url = f"[https://search.daum.net/search?w=news&q=](https://search.daum.net/search?w=news&q=){encoded_query}&sort=recency&DA=STC"
        results = []
        try:
            response = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.select('.c-item-content') or soup.select('ul.c-list-basic > li')
            for article in articles:
                title_elem = article.select_one('.item-title a') or article.select_one('a.tit_main')
                if title_elem and title_elem.text.strip():
                    results.append({"title": title_elem.text.strip(), "link": title_elem.get('href'), "portal": "다음"})
                if len(results) >= limit: break
        except Exception:
            pass
        return results

def send_telegram_message(token, chat_id, text):
    url = f"[https://api.telegram.org/bot](https://api.telegram.org/bot){token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    requests.post(url, json=payload)

def main():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    now_time = datetime.datetime.now(kst)
    
    # 아침 8시 ~ 저녁 6시 사이에만 작동하도록 설정
    if not (8 <= now_time.hour <= 18):
        print("현재는 알림 발송 시간이 아닙니다.")
        return

    scraper = NewsScraper()
    msg_body = f"📰 <b>[정각 알림] 실시간 뉴스 모니터링</b> ({now_time.strftime('%Y-%m-%d %H:%M:%S')})\n\n"
    
    for kw in KEYWORDS:
        # 네이버, 구글, 다음 뉴스 수집 및 합치기
        naver_news = scraper.get_naver_news_pool(kw, limit=DISPLAY_LIMIT)
        google_news = scraper.get_google_news_pool(kw, limit=DISPLAY_LIMIT)
        daum_news = scraper.get_daum_news_pool(kw, limit=DISPLAY_LIMIT)
        
        combined_news = (naver_news + google_news + daum_news)
        
        msg_body += f"📂 <b>[{kw}]</b>\n"
        if not combined_news:
            msg_body += "관련 기사 없음\n\n"
            continue
            
        # 중복 제거 및 긴급 태그 처리
        seen_links = set()
        final_list = []
        for news in combined_news:
            if news['link'] not in seen_links:
                final_list.append(news)
                seen_links.add(news['link'])
                
        for news in final_list[:DISPLAY_LIMIT]:
            urgent = "🚨" if any(w in news['title'] for w in ["속보", "긴급", "단독"]) else "•"
            safe_title = news['title'].replace('<', '&lt;').replace('>', '&gt;')
            msg_body += f"{urgent} [{news['portal']}] <a href='{news['link']}'>{safe_title}</a>\n"
        msg_body += "\n"
        
    # 텔레그램 전송
    send_telegram_message(TELEGRAM_TOKEN, CHAT_ID, msg_body)
    print("텔레그램 발송 완료!")

if __name__ == "__main__":
    main()
