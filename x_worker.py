import os
import re
import json
import asyncio
import requests
from bs4 import BeautifulSoup
from twikit import Client

# خواندن کوکی‌های رایگان X از GitHub Secrets
X_AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "").strip()
X_CT0 = os.environ.get("X_CT0", "").strip()
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "shirazlastnews").strip()

HISTORY_FILE = "posted_x_ids.json"

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

def format_for_x(raw_text):
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    clean_lines = [l for l in lines if not ("t.me/" in l or "@" in l or "shirazlastnews" in l.lower())]
    
    if not clean_lines:
        return None

    emoji = detect_category_emoji(raw_text)
    headline = clean_lines[0]
    body = " ".join(clean_lines[1:]) if len(clean_lines) > 1 else ""
    hashtags = select_smart_hashtags(raw_text)

    base_structure = f"{emoji} {headline}\n\n{hashtags}"
    available_chars = 270 - len(base_structure)

    if body and available_chars > 35:
        short_body = body[:available_chars - 3].rsplit(" ", 1)[0] + "..."
        tweet_text = f"{emoji} {headline}\n\n▫️ {short_body}\n\n{hashtags}"
    else:
        if len(base_structure) > 275:
            max_head = 270 - len(hashtags) - 5
            headline = headline[:max_head].rsplit(" ", 1)[0] + "..."
        tweet_text = f"{emoji} {headline}\n\n{hashtags}"

    return tweet_text

def fetch_latest_telegram_posts():
    url = f"https://t.me/s/{CHANNEL}"
    headers = {"User-Agent": "Mozilla/5.0"}
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

async def main():
    if not X_AUTH_TOKEN or not X_CT0:
        raise ValueError("کوکی‌های X_AUTH_TOKEN و X_CT0 در GitHub Secrets وارد نشده‌اند!")

    history = load_history()
    posts = fetch_latest_telegram_posts()
    
    new_posts = [p for p in posts if p["id"] not in history]
    if not new_posts:
        print("هیچ خبر جدیدی برای انتشار در X وجود ندارد.")
        return

    target_post = new_posts[-1]
    tweet_text = format_for_x(target_post["text"])
    if not tweet_text:
        return

    # اتصال مستقیم با کوکی مرورگر بدون نیاز به Developer API پولی
    client = Client("en-US")
    client.set_cookies({
        "auth_token": X_AUTH_TOKEN,
        "ct0": X_CT0
    })

    media_ids = []
    if target_post["photo_url"]:
        try:
            img_data = requests.get(target_post["photo_url"], timeout=15).content
            with open("temp_news.jpg", "wb") as f:
                f.write(img_data)
            media_id = await client.upload_media("temp_news.jpg")
            media_ids = [media_id]
        except Exception as e:
            print(f"خطا در دانلود/آپلود تصویر: {e}")

    # ۱. ارسال توییت اصلی
    main_tweet = await client.create_tweet(
        text=tweet_text,
        media_ids=media_ids if media_ids else None
    )
    print(f"توییت اصلی با موفقیت منتشر شد! ID: {main_tweet.id}")

    # ۲. ارسال خودکار کامنت (Reply) حاوی لینک کانال تلگرام
    await asyncio.sleep(3)
    reply_text = (
        f"🔗 جزئیات کامل و ویدیوهای بیشتر در کانال تلگرام آخرین خبرهای شیراز:\n"
        f"https://t.me/{CHANNEL}/{target_post['id']}"
    )
    await client.create_tweet(
        text=reply_text,
        reply_to=main_tweet.id
    )
    print("کامنت لینک کانال با موفقیت زیر توییت ثبت شد.")

    for p in new_posts:
        history.append(p["id"])
    save_history(history)

if __name__ == "__main__":
    asyncio.run(main())
