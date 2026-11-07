import os
import re
import json
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
import tweepy

# خواندن تمامی کلیدها و کوکی‌ها از GitHub Secrets
API_KEY = os.environ.get("X_API_KEY", "").strip()
API_SECRET = os.environ.get("X_API_SECRET", "").strip()
ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN", "").strip()
ACCESS_SECRET = os.environ.get("X_ACCESS_SECRET", "").strip()

X_AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "").strip()
X_CT0 = os.environ.get("X_CT0", "").strip()
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "shirazlastnews").strip()

HISTORY_FILE = "posted_x_ids.json"

# بانک جامع هشتگ‌های ترند شیراز و ایران در X
TAG_RULES = {
    "فوتبال|فجر|سپاسی|لیگ|ورزش|استقلال|پرسپولیس|ورزشگاه|پارس": ["#فجر_سپاسی", "#فوتبال", "#ورزش_فارس"],
    "حادثه|آتش|تصادف|اورژانس|پلیس|بازداشت|قتل|سرقت|انفجار": ["#حوادث", "#خبر_فوری", "#حوادث_شیراز"],
    "شهرداری|مترو|ترافیک|شورای_شهر|عمران|خیابان|پل|بزرگراه": ["#شهرداری_شیراز", "#کلانشهر_شیراز"],
    "هواشناسی|باران|برف|آلودگی|دما|سد|آب|برق": ["#هواشناسی", "#وضعیت_هوا"],
    "طلا|سکه|دلار|تورم|بازار|قیمت|اقتصاد|مسکن": ["#اقتصاد", "#بازار_شیراز"],
    "حافظیه|سعدی|تخت_جمشید|گردشگری|مسافر|میراث|کافه": ["#گردشگری", "#شیرازگردی"]
}

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-200:], f, ensure_ascii=False, indent=2)

def select_smart_hashtags(text):
    tags = ["#شیراز", "#اخبار_شیراز", "#فارس"]
    for pattern, pattern_tags in TAG_RULES.items():
        if re.search(pattern, text):
            for t in pattern_tags:
                if t not in tags:
                    tags.append(t)
    return " ".join(tags[:5])

def detect_category_emoji(text):
    if re.search("فوری|حادثه|آتش|انفجار|تصادف", text):
        return "🚨"
    if re.search("فوتبال|فجر|ورزش|لیگ", text):
        return "⚽️"
    if re.search("هواشناسی|باران|برف|دما", text):
        return "🌤"
    return "📌"

def format_for_x(raw_text, post_id):
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    clean_lines = [l for l in lines if not ("t.me/" in l or "@" in l or "shirazlastnews" in l.lower())]
    
    if not clean_lines:
        return None

    emoji = detect_category_emoji(raw_text)
    headline = clean_lines[0]
    body = " ".join(clean_lines[1:]) if len(clean_lines) > 1 else ""
    hashtags = select_smart_hashtags(raw_text)
    post_link = f"https://t.me/{CHANNEL}/{post_id}"

    # هر لینک در X دقیقاً ۲۳ کاراکتر محاسبه می‌شود
    base_len = len(emoji) + 1 + len(headline) + 2 + len(hashtags) + 2 + 23
    available_for_body = 275 - base_len

    if body and available_for_body > 35:
        short_body = body[:available_for_body - 6].rsplit(" ", 1)[0] + "..."
        tweet_text = f"{emoji} {headline}\n\n▫️ {short_body}\n\n{hashtags}\n{post_link}"
    else:
        if base_len > 275:
            max_head = 275 - (len(hashtags) + 30)
            headline = headline[:max_head].rsplit(" ", 1)[0] + "..."
        tweet_text = f"{emoji} {headline}\n\n{hashtags}\n{post_link}"

    return tweet_text

def fetch_latest_telegram_posts():
    url = f"https://t.me/s/{CHANNEL}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")
    
    posts = []
    for wrap in soup.select(".tgme_widget_message"):
        post_id = wrap.get("data-post", "").split("/")[-1]
        text_elem = wrap.select_one(".tgme_widget_message_text")
        if not post_id or not text_elem:
            continue
            
        raw_text = text_elem.get_text("\n").strip()
        
        photo_url = None
        photo_elem = wrap.select_one(".tgme_widget_message_photo_wrap")
        if photo_elem and "background-image" in photo_elem.get("style", ""):
            match = re.search(r"url\(['\"]?(.*?)['\"]?\)", photo_elem["style"])
            if match:
                photo_url = match.group(1)
                
        posts.append({
            "id": post_id,
            "text": raw_text,
            "photo_url": photo_url
        })
    return posts

def post_via_browser_impersonation(tweet_text, photo_url=None):
    """ارسال مستقیم با شبیه‌سازی مرورگر کروم واقعی برای دور زدن محدودیت ۴۰۲ و کلودفلر"""
    if not X_AUTH_TOKEN or not X_CT0:
        raise RuntimeError("کوکی‌های X_AUTH_TOKEN و X_CT0 در بخش Secrets تنظیم نشده‌اند.")

    session = cffi_requests.Session(impersonate="chrome120")
    cookies = {"auth_token": X_AUTH_TOKEN, "ct0": X_CT0}
    
    # توکن عمومی استاندارد وب‌اپلیکیشن X
    bearer = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
    headers = {
        "authorization": f"Bearer {bearer}",
        "x-csrf-token": X_CT0,
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "fa",
        "content-type": "application/json",
        "origin": "https://x.com",
        "referer": "https://x.com/compose/post"
    }

    media_entities = []
    if photo_url:
        try:
            img_bytes = requests.get(photo_url, timeout=15).content
            upload_headers = {
                "authorization": f"Bearer {bearer}",
                "x-csrf-token": X_CT0,
                "x-twitter-auth-type": "OAuth2Session",
                "origin": "https://x.com",
                "referer": "https://x.com/"
            }
            up_resp = session.post(
                "https://upload.twitter.com/1.1/media/upload.json",
                headers=upload_headers,
                cookies=cookies,
                files={"media": ("news.jpg", img_bytes, "image/jpeg")},
                timeout=30
            )
            if up_resp.status_code == 200:
                media_id = up_resp.json().get("media_id_string")
                if media_id:
                    media_entities.append({"media_id": media_id, "tagged_users": []})
                    print(f"تصویر با موفقیت آپلود شد: {media_id}")
        except Exception as e:
            print(f"ادامه ارسال بدون تصویر مجزا (نمایش از طریق کارت لینک): {e}")

    # دریافت خودکار GraphQL QueryId یا استفاده از مقدار پایدار CreateTweet
    query_id = "xT36w0XM6A8jDyn-ram2Aw"
    url = f"https://x.com/i/api/graphql/{query_id}/CreateTweet"

    payload = {
        "variables": {
            "tweet_text": tweet_text,
            "dark_request": False,
            "media": {
                "media_entities": media_entities,
                "possibly_sensitive": False
            },
            "semantic_annotation_ids": []
        },
        "features": {
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "tweetypie_unmention_optimization_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "articles_preview_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_enhance_cards_enabled": False
        },
        "queryId": query_id
    }

    resp = session.post(url, headers=headers, cookies=cookies, json=payload, timeout=30)
    if resp.status_code == 200 and "errors" not in resp.json():
        print("✅ پست با موفقیت از طریق شبیه‌ساز مرورگر کروم در X منتشر شد!")
        return True
    else:
        raise RuntimeError(f"پاسخ سرور X ({resp.status_code}): {resp.text[:300]}")

def main():
    history = load_history()
    posts = fetch_latest_telegram_posts()
    
    if not posts:
        print("هیچ پستی از صفحه وب تلگرام دریافت نشد.")
        return

    new_posts = [p for p in posts if p["id"] not in history]
    if not new_posts:
        print("همه اخبار فعلی قبلاً در X منتشر شده‌اند.")
        return

    target_post = new_posts[-1]
    tweet_text = format_for_x(target_post["text"], target_post["id"])
    if not tweet_text:
        return

    published = False

    # موتور اول: تلاش با API رسمی (بدون آپلود مدیای پولی که باعث خطای 402 می‌شد)
    if API_KEY and API_SECRET and ACCESS_TOKEN and ACCESS_SECRET:
        try:
            print("تلاش برای ارسال با API رسمی v2...")
            client_v2 = tweepy.Client(
                consumer_key=API_KEY,
                consumer_secret=API_SECRET,
                access_token=ACCESS_TOKEN,
                access_token_secret=ACCESS_SECRET
            )
            res = client_v2.create_tweet(text=tweet_text)
            print(f"✅ منتشر شد (API رسمی)! Tweet ID: {res.data['id']}")
            published = True
        except Exception as e:
            print(f"⚠️ API رسمی نیاز به پلن پولی داشت ({e}). تغییر خودکار به موتور شبیه‌ساز مرورگر...")

    # موتور دوم: ارسال رایگان با شبیه‌ساز مرورگر کروم (دور زدن خطای 402 و کلودفلر)
    if not published:
        post_via_browser_impersonation(tweet_text, target_post["photo_url"])

    # ثبت در تاریخچه برای جلوگیری از ارسال تکراری
    for p in new_posts:
        if p["id"] not in history:
            history.append(p["id"])
    save_history(history)

if __name__ == "__main__":
    main()
