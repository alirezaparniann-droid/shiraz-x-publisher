import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# خواندن کوکی‌ها از GitHub Secrets
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
    available_for_body = 270 - base_len

    if body and available_for_body > 35:
        short_body = body[:available_for_body - 6].rsplit(" ", 1)[0] + "..."
        tweet_text = f"{emoji} {headline}\n\n▫️ {short_body}\n\n{hashtags}\n{post_link}"
    else:
        if base_len > 270:
            max_head = 270 - (len(hashtags) + 30)
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

def post_with_real_browser(tweet_text, photo_url=None):
    if not X_AUTH_TOKEN or not X_CT0:
        raise RuntimeError("مقادیر X_AUTH_TOKEN و X_CT0 در GitHub Secrets خالی هستند!")

    image_path = None
    if photo_url:
        try:
            img_data = requests.get(photo_url, timeout=15).content
            image_path = os.path.abspath("temp_news.jpg")
            with open(image_path, "wb") as f:
                f.write(img_data)
            print("تصویر خبر با موفقیت دانلود شد.")
        except Exception as e:
            print(f"خطا در دانلود تصویر خبر: {e}")
            image_path = None

    with sync_playwright() as p:
        # راه‌اندازی مرورگر کروم با غیرفعال کردن فلگ‌های تشخیص ربات کلودفلر
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )

        # حذف ردپای WebDriver برای عبور کامل از کلودفلر
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # تزریق کوکی‌های معتبر روی هر دو دامنه x.com و twitter.com
        cookies = []
        for domain in [".x.com", ".twitter.com"]:
            cookies.extend([
                {"name": "auth_token", "value": X_AUTH_TOKEN, "domain": domain, "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
                {"name": "ct0", "value": X_CT0, "domain": domain, "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
            ])
        context.add_cookies(cookies)

        page = context.new_page()
        print("در حال باز کردن صفحه ارسال پست در X...")
        page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # بررسی لاگین بودن
        if "login" in page.url.lower():
            raise RuntimeError("کوکی‌های X_AUTH_TOKEN یا X_CT0 منقضی یا اشتباه هستند (هدایت به صفحه لاگین).")

        # انتظار برای ظاهر شدن کادر متن توییت
        textbox = page.locator('[data-testid="tweetTextarea_0"]').first
        textbox.wait_for(state="visible", timeout=30000)
        textbox.click()
        page.wait_for_timeout(1000)

        # آپلود تصویر در صورت وجود
        if image_path and os.path.exists(image_path):
            try:
                file_input = page.locator('input[data-testid="fileInput"]').first
                file_input.set_input_files(image_path)
                print("تصویر داخل ادیتور X بارگذاری شد. انتظار برای پردازش...")
                page.wait_for_timeout(6000)
            except Exception as e:
                print(f"ادامه بدون پیوست فایل تصویر: {e}")

        # وارد کردن متن خبر
        textbox.fill(tweet_text)
        page.wait_for_timeout(2000)

        # کلیک روی دکمه ارسال (Post)
        post_button = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first
        post_button.wait_for(state="visible", timeout=15000)
        post_button.click()

        # انتظار برای ثبت نهایی در سرور X
        page.wait_for_timeout(6000)
        print("✅ خبر با موفقیت کامل در شبکه اجتماعی X منتشر شد!")
        browser.close()

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

    post_with_real_browser(tweet_text, target_post["photo_url"])

    # ذخیره در تاریخچه برای جلوگیری از تکرار
    for p in new_posts:
        if p["id"] not in history:
            history.append(p["id"])
    save_history(history)

if __name__ == "__main__":
    main()
