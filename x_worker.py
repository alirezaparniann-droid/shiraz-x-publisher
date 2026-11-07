import os
import re
import json
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

X_AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "").strip()
X_CT0 = os.environ.get("X_CT0", "").strip()
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "shirazlastnews").strip()
EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

HISTORY_FILE = "posted_x_ids.json"

TAG_RULES = {
    "فوتبال|فجر|سپاسی|لیگ|ورزش|استقلال|پرسپولیس|ورزشگاه|پارس": ["#فجر_سپاسی", "#ورزش_فارس"],
    "حادثه|آتش|تصادف|اورژانس|پلیس|بازداشت|قتل|سرقت|انفجار": ["#حوادث_شیراز", "#خبر_فوری"],
    "شهرداری|مترو|ترافیک|شورای_شهر|عمران|خیابان|پل|بزرگراه": ["#شهرداری_شیراز", "#کلانشهر_شیراز"],
    "هواشناسی|باران|برف|آلودگی|دما|سد|آب|برق": ["#هواشناسی_فارس", "#وضعیت_هوا"],
    "طلا|سکه|دلار|تورم|بازار|قیمت|اقتصاد|مسکن": ["#اقتصاد", "#بازار_شیراز"],
    "حافظیه|سعدی|تخت_جمشید|گردشگری|مسافر|میراث|کافه": ["#شیرازگردی", "#گردشگری"]
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

def to_persian_num(text):
    en_nums = "0123456789"
    fa_nums = "۰۱۲۳۴۵۶۷۸۹"
    return text.translate(str.maketrans(en_nums, fa_nums))

def clean_text_line(line):
    line = re.sub(r"^[\s🔴🟠🟡🟢🔵🟣⚫️⚪️🟤🚨📌⚽️🌤🔹🔸▫️▪️•\-_#*«»]+", "", line)
    return to_persian_num(line.strip())

def detect_category_icon(text):
    if re.search("فوری|حادثه|آتش|انفجار|تصادف|اورژانس|پلیس", text):
        return "🚨"
    if re.search("فوتبال|فجر|ورزش|لیگ|ورزشگاه", text):
        return "⚽️"
    if re.search("هواشناسی|باران|برف|دما|آلودگی", text):
        return "🌤"
    return "📌"

def select_smart_hashtags(text):
    tags = ["#شیراز", "#اخبار_شیراز"]
    for pattern, pattern_tags in TAG_RULES.items():
        if re.search(pattern, text):
            for t in pattern_tags:
                if t not in tags:
                    tags.append(t)
    return " ".join(tags[:4])

def build_tweet_parts(raw_text, post_id):
    """
    بازگرداندن لیست توییت‌ها (۱ یا ۲ بخش) تا تیتر و لید خبر ۱۰۰٪ کامل و بدون بریدگی منتشر شوند.
    """
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    filtered_lines = [
        l for l in lines
        if not (
            "t.me/" in l
            or "@" in l
            or "shirazlastnews" in l.lower()
            or "آخرین خبرهای شیراز" in l
            or l.startswith("#")
        )
    ]

    if not filtered_lines:
        return []

    icon = detect_category_icon(raw_text)
    headline = clean_text_line(filtered_lines[0])

    # استخراج لید کامل خبر (اولین پاراگراف پس از تیتر)
    lead = ""
    for l in filtered_lines[1:]:
        cleaned = clean_text_line(l)
        if len(cleaned) > 15:
            lead = cleaned
            break

    hashtags = select_smart_hashtags(raw_text)
    post_link = f"https://t.me/{CHANNEL}/{post_id}"

    # قالب اصلی: فقط تیتر + یک خط فاصله + لید کامل
    header = f"{icon} «{headline}»"

    if not lead:
        # اگر خبر فقط تیتر داشت
        full_single = f"{header}\n\n#شیراز #اخبار_شیراز"
        second_tweet = f"🔗 مشروح خبر در کانال تلگرام آخرین خبرهای شیراز:\n{post_link}\n\n{hashtags}"
        return [full_single[:275], second_tweet]

    # ترکیب تیتر و لید کامل
    combined = f"{header}\n\n▪️ {lead}"

    # حالت اول: تیتر و لید کامل به راحتی در یک توییت (زیر ۲۵۰ کاراکتر) جا می‌شوند
    if len(combined) <= 248:
        first_tweet = f"{combined}\n\n#شیراز #اخبار_شیراز"
        second_tweet = f"🔗 جزئیات بیشتر در کانال تلگرام آخرین خبرهای شیراز:\n{post_link}\n\n{hashtags}"
        return [first_tweet, second_tweet]

    # حالت دوم: تیتر و لید کامل بین ۲۵۰ تا ۲۷۵ کاراکتر هستند (بدون هشتگ در توییت اول تا لید کامل بماند)
    if len(combined) <= 275:
        first_tweet = combined
        second_tweet = f"🔗 جزئیات کامل خبر در تلگرام:\n{post_link}\n\n{hashtags}"
        return [first_tweet, second_tweet]

    # حالت سوم: تیتر + لید طولانی‌تر از ۲۷۵ کاراکتر است -> تقسیم هوشمند در دو توییت متوالی بدون حذف هیچ کلمه‌ای
    available_in_first = 270 - len(header) - 6
    if available_in_first > 60:
        split_lead_1 = lead[:available_in_first].rsplit(" ", 1)[0]
        split_lead_2 = lead[len(split_lead_1):].strip()
        first_tweet = f"{header}\n\n▪️ {split_lead_1} (۱/۲)"
        second_tweet = f"▫️ ادامه: {split_lead_2} (۲/۲)\n\n{hashtags}\n🔗 {post_link}"
        return [first_tweet, second_tweet[:275]]
    else:
        # اگر خود تیتر خیلی بلند بود، تیتر در توییت اول و لید کامل در توییت دوم قرار می‌گیرد
        first_tweet = f"{header}"
        second_tweet = f"▪️ {lead[:200]}\n\n{hashtags}\n🔗 {post_link}"
        return [first_tweet[:275], second_tweet[:275]]

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

def post_with_real_browser(tweet_parts, photo_url=None):
    if not X_AUTH_TOKEN or not X_CT0:
        raise RuntimeError("مقادیر X_AUTH_TOKEN و X_CT0 در GitHub Secrets خالی هستند!")

    image_path = None
    if photo_url:
        try:
            img_data = requests.get(photo_url, timeout=15).content
            image_path = os.path.abspath("temp_news.jpg")
            with open(image_path, "wb") as f:
                f.write(img_data)
            print("تصویر خبر دانلود شد.")
        except Exception as e:
            print(f"خطا در دانلود تصویر خبر: {e}")
            image_path = None

    with sync_playwright() as p:
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
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        cookies = []
        for domain in [".x.com", ".twitter.com"]:
            cookies.extend([
                {"name": "auth_token", "value": X_AUTH_TOKEN, "domain": domain, "path": "/", "secure": True, "httpOnly": True, "sameSite": "None"},
                {"name": "ct0", "value": X_CT0, "domain": domain, "path": "/", "secure": True, "httpOnly": False, "sameSite": "Lax"}
            ])
        context.add_cookies(cookies)

        page = context.new_page()
        print("در حال باز کردن صفحه X...")
        page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        if "login" in page.url.lower():
            raise RuntimeError("کوکی‌های X منقضی یا اشتباه هستند.")

        # کادر توییت اول (تیتر + لید کامل)
        textbox_0 = page.locator('[data-testid="tweetTextarea_0"]').first
        textbox_0.wait_for(state="visible", timeout=30000)
        textbox_0.click()
        page.wait_for_timeout(1000)

        if image_path and os.path.exists(image_path):
            try:
                file_input = page.locator('input[data-testid="fileInput"]').first
                file_input.set_input_files(image_path)
                print("تصویر بارگذاری شد...")
                page.wait_for_timeout(6000)
            except Exception as e:
                print(f"ادامه بدون پیوست فایل تصویر: {e}")

        textbox_0.fill(tweet_parts[0])
        page.wait_for_timeout(1500)

        # اگر بخش دوم (لینک و ادامه/هشتگ‌ها) وجود داشت، دکمه + (افزودن به رشته‌توییت) را بزن
        if len(tweet_parts) > 1 and tweet_parts[1]:
            try:
                add_thread_btn = page.locator('[data-testid="addButton"]').first
                if add_thread_btn.is_visible():
                    add_thread_btn.click()
                    page.wait_for_timeout(1500)
                    textbox_1 = page.locator('[data-testid="tweetTextarea_1"]').first
                    textbox_1.wait_for(state="visible", timeout=10000)
                    textbox_1.fill(tweet_parts[1])
                    page.wait_for_timeout(1500)
                    print("توییت دوم (مکمل و لینک) به رشته‌توییت اضافه شد.")
            except Exception as e:
                print(f"ارسال به صورت تک‌توییت (عدم افزودن بخش دوم): {e}")

        post_button = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first
        post_button.wait_for(state="visible", timeout=15000)
        post_button.click()

        page.wait_for_timeout(6000)
        print("✅ تیتر و لید کامل خبر با موفقیت در X منتشر شد!")
        browser.close()

def main():
    history = load_history()
    posts = fetch_latest_telegram_posts()

    if not posts:
        print("هیچ پستی از صفحه وب تلگرام دریافت نشد.")
        return

    new_posts = [p for p in posts if p["id"] not in history]

    if not new_posts:
        if EVENT_NAME == "workflow_dispatch":
            print("اجرای دستی: ارسال آخرین خبر با تیتر و لید کامل...")
            target_post = posts[-1]
        else:
            print("همه اخبار فعلی قبلاً در X منتشر شده‌اند.")
            return
    else:
        target_post = new_posts[-1]

    tweet_parts = build_tweet_parts(target_post["text"], target_post["id"])
    if not tweet_parts:
        return

    post_with_real_browser(tweet_parts, target_post["photo_url"])

    for p in posts:
        if p["id"] not in history:
            history.append(p["id"])
    save_history(history)

if __name__ == "__main__":
    main()
