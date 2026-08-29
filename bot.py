import requests
import urllib.parse
import urllib3
import datetime
import json
import os
from bs4 import BeautifulSoup
import feedparser
import concurrent.futures

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# ⚙️ 기본 설정 및 토큰
# ==========================================
TELE_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8921848994:AAEb5pK_IP_fvU98nRtQCZOxgMO8iOQuj_c")
TELE_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003880927818")
KMA_KEY = "puRzQKI109F0LCwpZkpBdACQeAMzrJduCAC1iqHFbxHoxKkyrgNW3py20KEDRXSFZ6Qq9kYDBjeXvzLekT%2FPEg%3D%3D"
NAVER_ID = "5p3Vuu15J3_qo3MMGOLl"
NAVER_SECRET = "3Yx_9guJfU"

SENT_EQK_FILE = "sent_earthquakes.json"
LAST_RUN_FILE = "last_run_state.json"

TARGET_KEYWORDS = ["국토교통부", "대전지방국토관리청", "건설 사고", "지반 침하", "화재", "지진"]
TARGET_REGIONS = ["대전", "충남", "충북", "세종"]
PORTALS = ["네이버", "구글", "다음"]

KST = datetime.timezone(datetime.timedelta(hours=9))
now_kst = datetime.datetime.now(KST)

# ==========================================
# 💾 상태 관리 함수
# ==========================================
def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

# ==========================================
# 📱 텔레그램 전송 함수
# ==========================================
def send_telegram_message(text):
    if not TELE_TOKEN or not TELE_CHAT_ID: return None
    url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendMessage"
    payload = {"chat_id": TELE_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        return requests.post(url, json=payload, timeout=10)
    except Exception:
        return None

def send_telegram_photo(photo_url, caption):
    if not TELE_TOKEN or not TELE_CHAT_ID: return None
    url = f"https://api.telegram.org/bot{TELE_TOKEN}/sendPhoto"
    payload = {"chat_id": TELE_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
    try:
        res = requests.post(url, json=payload, timeout=12)
        if res.status_code == 200: return res
    except Exception:
        pass
    return send_telegram_message(caption)

def format_eqk_time(s):
    s = str(s).strip()
    if len(s) >= 12:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}"
    return s

# ==========================================
# 🚨 1. 기상청 국내 신규 지진 감시 & 즉시 발송
# ==========================================
def check_and_send_earthquakes():
    from_tm = (now_kst - datetime.timedelta(days=3)).strftime("%Y%m%d")
    to_tm = now_kst.strftime("%Y%m%d")
    url = f"http://apis.data.go.kr/1360000/EqkInfoService/getEqkMsg?serviceKey={KMA_KEY}&dataType=JSON&numOfRows=30&pageNo=1&fromTmFc={from_tm}&toTmFc={to_tm}"
    
    try:
        res = requests.get(url, timeout=10, verify=False)
        data = res.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        if isinstance(items, dict): items = [items]
    except Exception:
        items = []

    foreign_keywords = ["일본", "대만", "중국", "러시아", "필리핀", "칠레", "인도네시아", "튀르키예"]
    sent_set = set(load_json(SENT_EQK_FILE, []))

    for eq in items:
        loc = str(eq.get("loc", ""))
        rem = str(eq.get("rem", ""))
        fcTp = str(eq.get("fcTp", ""))

        if any(fk in loc for fk in foreign_keywords) or any(fk in rem for fk in ["국외지진", "국외 지진"]) or fcTp in ["2", "12"]:
            continue

        eq_id = f"{eq.get('tmEqk')}_{loc}_{eq.get('mt')}"
        if eq_id not in sent_set:
            tm_eqk_f = format_eqk_time(eq.get('tmEqk', '-'))
            tm_fc_f = format_eqk_time(eq.get('tmFc', '-'))
            img_url = eq.get('img')

            msg = (
                f"🚨 <b>[기상청 국내 지진 긴급 속보]</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📍 <b>진앙:</b> {loc}\n"
                f"💥 <b>규모:</b> M{eq.get('mt', '-')} (최대진도: {eq.get('inT', '-')})\n"
                f"📏 <b>발생깊이:</b> {eq.get('dep', '-')} km\n"
                f"⏱ <b>발생시각:</b> {tm_eqk_f}\n"
                f"📢 <b>발표시각:</b> {tm_fc_f}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>상세:</b> {rem}"
            )

            if img_url and isinstance(img_url, str) and img_url.startswith("http"):
                res = send_telegram_photo(img_url, msg)
            else:
                res = send_telegram_message(msg)

            if res and res.status_code == 200:
                sent_set.add(eq_id)
                print(f"✅ 지진 속보 발송 완료: M{eq.get('mt')} ({loc})")

    save_json(SENT_EQK_FILE, list(sent_set))

# ==========================================
# 📰 2. 뉴스 수집 및 정시 발송
# ==========================================
def get_naver_news(keyword):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    params = {"query": keyword, "display": 50, "sort": "sim"}
    results = []
    try:
        res = requests.get(url, headers=headers, params=params, timeout=8)
        if res.status_code == 200:
            for item in res.json().get('items', []):
                t = item['title'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
                d = item['description'].replace('<b>', '').replace('</b>', '').replace('&quot;', '"').replace('&apos;', "'")
                results.append({"title": t, "link": item['link'], "description": d, "portal": "네이버"})
    except Exception:
        pass
    return results

def get_google_news(keyword):
    encoded = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"
    results = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:50]:
            results.append({"title": entry.title, "link": entry.link, "description": "", "portal": "구글"})
    except Exception:
        pass
    return results

def get_daum_news(keyword):
    encoded = urllib.parse.quote(keyword)
    url = f"https://search.daum.net/search?w=news&q={encoded}&sort=accuracy&p=1"
    headers = {"User-Agent": "Mozilla/5.0"}
    results = []
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.select('div.item-title a, a.tit_main, a.item-title, ul.c-list-basic li a'):
                t = a.get_text(strip=True)
                l = a.get('href')
                if t and l and l.startswith("http"):
                    results.append({"title": t, "link": l, "description": "", "portal": "다음"})
                    if len(results) >= 50: break
    except Exception:
        pass
    return results

def collect_filtered_news(keyword):
    pool = get_naver_news(keyword) + get_google_news(keyword) + get_daum_news(keyword)
    seen = set()
    matched = []
    for n in pool:
        if n['link'] in seen: continue
        for reg in TARGET_REGIONS:
            if reg in n['title'] or reg in n['description']:
                n_copy = n.copy()
                n_copy['region'] = reg
                matched.append(n_copy)
                seen.add(n['link'])
                break
    return matched[:8]

def check_and_send_scheduled_news():
    curr_hour = now_kst.hour
    # 아침 8시 ~ 저녁 6시 (08~18시) 정각에만 발송
    if not (8 <= curr_hour <= 18):
        return

    state = load_json(LAST_RUN_FILE, {})
    last_sent_date_hour = state.get("last_news_sent")
    current_date_hour = now_kst.strftime("%Y%m%d_%H")

    # 이번 시간대에 이미 보냈다면 중복 발송 안함
    if last_sent_date_hour == current_date_hour:
        return

    print(f"📰 {curr_hour}시 정각 뉴스 수집 및 발송 시작...")
    msg_body = f"📰 <b>[정시 알림] 실시간 뉴스 모니터링</b> ({now_kst.strftime('%Y-%m-%d %H:%M')})\n\n"
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_map = {executor.submit(collect_filtered_news, kw): kw for kw in TARGET_KEYWORDS}
        for future in concurrent.futures.as_completed(future_map):
            kw = future_map[future]
            try:
                news_list = future.result()
            except Exception:
                news_list = []
            
            msg_body += f"📂 <b>[{kw}]</b>\n"
            if not news_list:
                msg_body += "관련 기사 없음\n\n"
            else:
                for news in news_list:
                    urgent = "🚨" if any(w in news['title'] for w in ["속보", "긴급", "단독"]) else "•"
                    safe_title = news['title'].replace('<', '&lt;').replace('>', '&gt;')
                    msg_body += f"{urgent} [{news['region']}][{news['portal']}] <a href='{news['link']}'>{safe_title}</a>\n"
                msg_body += "\n"

    res = send_telegram_message(msg_body)
    if res and res.status_code == 200:
        state["last_news_sent"] = current_date_hour
        save_json(LAST_RUN_FILE, state)
        print("✅ 정시 뉴스 전송 완료")

if __name__ == "__main__":
    check_and_send_earthquakes()
    check_and_send_scheduled_news()
