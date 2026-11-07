import os
import re
import json
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

X_AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "").strip()
X_CT0 = os.environ.get("X_CT0", "").strip()
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "shirazlastnews").strip()

HISTORY_FILE = "posted_x_ids.json"

# بانک هشتگ‌های ترند شیراز و ایران در X
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
    """تبدیل اعداد انگلیسی به فارسی برای زیبایی بصری متن"""
    en_nums = "0123456789"
    fa_nums = "۰۱۲۳۴۵۶۷۸۹"
    trans_table = str.maketrans(en_nums, fa_nums)
    return text.translate(trans_table)

def clean_text_line(line):
    """حذف ایموجی‌ها و کاراکترهای تکراری ابتدای خطوط کپی شده از تلگرام"""
    line = re.sub(r"^[\s🔴🟠🟡🟢🔵🟣⚫️⚪️🟤🚨📌⚽️🌤🔹🔸▫️▪️•\-_#*]+", "", line)
    return to_persian_num(line.strip())

def detect_luxury_badge(text):
    if re.search("فوری|حادثه|آتش|انفجار|تصادف|اورژانس|پلیس", text):
        return "🔴 فوری | شیراز"
    if re.search("فوتبال|فجر|ورزش|لیگ|ورزشگاه", text):
        return "⚽️ ورزشی | شیراز"
    if re.search("هواشناسی|باران|برف|دما|آلودگی", text):
        return "🌤 هواشناسی | فارس"
    if re.search("طلا|سکه|دلار|قیمت|بازار|اقتصاد", text):
        return "📊 اقتصادی | شیراز"
    if re.search("شهرداری|مترو|ترافیک|شورای_شهر|خیابان|پل", text):
        return "🏛 شهرنگار | شیراز"
    return "💎 سرخط | شیراز"

def select_smart_hashtags(text):
    tags = ["#شیراز", "#اخبار_شیراز"]
    for pattern, pattern_tags in TAG_RULES.items():
        if re.search(pattern, text):
            for t in pattern_tags:
                if t not in tags:
                    tags.append(t)
    return " ".join(tags[:4])

def format_for_x(raw_text, post_id):
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    # حذف خطوط تبلیغاتی، آیدی‌ها و لینک‌های انتهای پست تلگرام
    filtered_lines = [
        l for l in lines
        if not ("t.me/" in l or "@" in l or "shirazlastnews" in l.lower() or "آخرین خبرهای شیراز" in l)
    ]
    
    if not filtered_lines:
        return None

    badge = detect_luxury_badge(raw_text)
    headline = clean_text_line(filtered_lines[0])
    
    # استخراج لید خبر از خطوط بعدی
    lead = ""
    if len(filtered_lines) > 1:
        lead_candidates = [clean_text_line(l) for l in filtered_lines[1:] if len(clean_text_line(l)) > 15]
        if lead_candidates:
            lead = " ".join(lead_candidates)

    hashtags = select_smart_hashtags(raw_text)
    post_link = f"https://t.me/{CHANNEL}/{post_id}"

    # ساختار پایه لاکچری با فاصله‌گذاری دقیق بین تیتر و لید
    header_part = f"{badge}\n\n«{headline}»"
    footer_part = f"{hashtags}\n🔗 {post_link}"

    # در X هر لینک ۲۳ کاراکتر محاسبه می‌شود
    fixed_len = len(header_part) + 4 + len( hashtags) + 4 + 23
    available_for_lead = 272 - fixed_len

    if lead and available_for_lead > 40:
        if len(lead) > available_for_lead:
            short_lead = lead[:available_for_lead - 5].rsplit(" ", 1)[0] + "…"
        else:
            short_lead = lead
        tweet_text = f"{header_part}\n\n▪️ {short_lead}\n\n{footer_part}"
    else:
        # اگر تیتر خیلی طولانی بود، آن را به تیتر و لید تقسیم یا خلاصه کن
        if fixed_len > 272:
            max_head = 272 - (len(badge) + len(hashtags) + 38)
            headline = headline[:max_head].rsplit(" ", 1)[0] + "…"
            header_part = f"{badge}\n\n«{headline}»"
        tweet_text = f"{header_part}\n\n{footer_part}"

    return tweet_text

def fetch_latest_telegram_posts():
    url = f"https://t.me/s/{CHANNEL}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    resp = requests.get(url, headers=headers, timeout=15)
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
            img_data = requests.get(photo_url, timeout=10).content
            image_path = os.path.abspath("temp_news.jpg")
            with open(image_path, "wb") as f:
                f.write(img_data)
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
        page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=45000)

        textbox = page.locator('[data-testid="tweetTextarea_0"]').first
        textbox.wait_for(state="visible", timeout=25000)
        textbox.click()

        if image_path and os.path.exists(image_path):
            try:
                file_input = page.locator('input[data-testid="fileInput"]').first
                file_input.set_input_files(image_path)
                page.wait_for_timeout(3500)
            except Exception as e:
                print(f"ادامه بدون پیوست فایل تصویر: {e}")

        textbox.fill(tweet_text)
        page.wait_for_timeout(1000)

        post_button = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first
        post_button.wait_for(state="visible", timeout=10000)
        post_button.click()

        page.wait_for_timeout(3500)
        print("✅ خبر با فرمت لاکچری در X منتشر شد!")
        browser.close()

def main():
    history = load_history()
    posts = fetch_latest_telegram_posts()
    
    if not posts:
        return

    if not history:
        for p in posts[:-1]:
            history.append(p["id"])

    new_posts = [p for p in posts if p["id"] not in history]
    if not new_posts:
        print("خبر جدیدی وجود ندارد.")
        return

    for target_post in new_posts[:2]:
        tweet_text = format_for_x(target_post["text"], target_post["id"])
        if tweet_text:
            post_with_real_browser(tweet_text, target_post["photo_url"])
        history.append(target_post["id"])
        save_history(history)

if __name__ == "__main__":
    main()
