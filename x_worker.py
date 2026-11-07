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
    line = re.sub(r"^[\s🔴🟠🟡🟢🔵🟣⚫️⚪️🟤🚨📌⚽️🌤🔹🔸▫️▪️•\-_#*«»🎬]+", "", line)
    return to_persian_num(line.strip())

def detect_category_icon(text, has_video=False):
    if has_video:
        return "🎬"
    if re.search("فوری|حادثه|آتش|انفجار|تصادف|اورژانس|پلیس", text):
        return "🚨"
    if re.search("فوتبال|فجر|ورزش|لیگ|ورزشگاه", text):
        return "⚽️"
    if re.search("هواشناسی|باران|برف|دما|آلودگی", text):
        return "🌤"
    return "📌"

def format_for_x(raw_text, has_video=False):
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    filtered_lines = [
        l for l in lines
        if not (
            "t.me/" in l
            or "@" in l
            or "shirazlastnews" in l.lower()
            or "آخرین خبرهای شیراز" in l
            or "منبع خبر:" in l
            or l.startswith("#")
        )
    ]

    if not filtered_lines:
        return None

    icon = detect_category_icon(raw_text, has_video=has_video)
    headline = clean_text_line(filtered_lines[0])

    lead = ""
    for l in filtered_lines[1:]:
        cleaned = clean_text_line(l)
        if len(cleaned) > 15:
            lead = cleaned
            break

    header = f"{icon} «{headline}»"

    if not lead:
        return f"{header}\n\n#شیراز #اخبار_شیراز"[:275]

    combined = f"{header}\n\n▪️ {lead}"

    if len(combined) <= 250:
        return f"{combined}\n\n#شیراز #اخبار_شیراز"

    if len(combined) <= 278:
        return combined

    available_for_lead = 274 - len(header) - 6
    if available_for_lead > 30:
        full_possible_lead = lead[:available_for_lead].rsplit(" ", 1)[0] + "…"
        return f"{header}\n\n▪️ {full_possible_lead}"

    return header[:275]

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

        # ۱. بررسی وجود ویدیو در پست تلگرام (مورد ۲۹)
        video_url = None
        video_elem = wrap.select_one("video.tgme_widget_message_video")
        if video_elem and video_elem.get("src"):
            video_url = video_elem.get("src")

        # ۲. بررسی وجود عکس یا تامبنیل ویدیو
        photo_url = None
        photo_elem = wrap.select_one(".tgme_widget_message_photo_wrap, .tgme_widget_message_video_thumb")
        if photo_elem and "background-image" in photo_elem.get("style", ""):
            match = re.search(r"url\(['\"]?(.*?)['\"]?\)", photo_elem["style"])
            if match:
                photo_url = match.group(1)

        posts.append({
            "id": post_id,
            "text": raw_text,
            "photo_url": photo_url,
            "video_url": video_url
        })
    return posts

def download_media_for_x(photo_url=None, video_url=None):
    """دانلود هوشمند ویدیو (زیر ۳۵ مگابایت) یا تصویر خبر"""
    if video_url:
        try:
            print("در حال بررسی و دانلود ویدیوی خبر برای X...")
            r = requests.get(video_url, stream=True, timeout=25)
            if r.status_code == 200:
                vid_path = os.path.abspath("temp_news_video.mp4")
                size = 0
                too_large = False
                with open(vid_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 512):
                        if chunk:
                            f.write(chunk)
                            size += len(chunk)
                            if size > 35 * 1024 * 1024:
                                too_large = True
                                break
                if not too_large and size > 20000:
                    print(f"ویدیو با موفقیت دانلود شد ({round(size / (1024*1024), 1)} MB).")
                    return vid_path, True
                else:
                    print("ویدیو بیش از حد سنگین بود؛ استفاده از تصویر کاور به جای ویدیو.")
        except Exception as e:
            print(f"خطا در دانلود ویدیو: {e}")

    if photo_url:
        try:
            img_data = requests.get(photo_url, timeout=15).content
            image_path = os.path.abspath("temp_news.jpg")
            with open(image_path, "wb") as f:
                f.write(img_data)
            print("تصویر خبر دانلود شد.")
            return image_path, False
        except Exception as e:
            print(f"خطا در دانلود تصویر خبر: {e}")

    return None, False

def post_with_real_browser(tweet_text, photo_url=None, video_url=None):
    if not X_AUTH_TOKEN or not X_CT0:
        raise RuntimeError("مقادیر X_AUTH_TOKEN و X_CT0 در GitHub Secrets خالی هستند!")

    media_path, is_video = download_media_for_x(photo_url, video_url)

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

        textbox = page.locator('[data-testid="tweetTextarea_0"]').first
        textbox.wait_for(state="visible", timeout=30000)
        textbox.click()
        page.wait_for_timeout(1000)

        if media_path and os.path.exists(media_path):
            try:
                file_input = page.locator('input[data-testid="fileInput"]').first
                file_input.set_input_files(media_path)
                if is_video:
                    print("ویدیو بارگذاری شد؛ انتظار برای پردازش ویدیو در سرور X...")
                    page.wait_for_timeout(18000)
                else:
                    print("تصویر بارگذاری شد...")
                    page.wait_for_timeout(6000)
            except Exception as e:
                print(f"ادامه بدون پیوست فایل رسانه: {e}")

        textbox.fill(tweet_text + " ")
        page.wait_for_timeout(1500)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        post_button = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first
        # اگر ویدیو در حال پردازش نهایی است، تا آماده شدن دکمه Post صبر کن
        for _ in range(10):
            if post_button.get_attribute("aria-disabled") == "true":
                page.wait_for_timeout(2000)
            else:
                break

        if post_button.count() > 0:
            post_button.evaluate("el => el.click()")
            print("دستور ارسال از طریق جاوااسکریپت اجرا شد.")
        else:
            page.keyboard.press("Control+Enter")

        page.wait_for_timeout(8000 if is_video else 6000)
        print("✅ خبر با موفقیت در X منتشر شد!")
        browser.close()

def main():
    history = load_history()
    posts = fetch_latest_telegram_posts()

    if not posts:
        print("هیچ پستی از صفحه وب تلگرام دریافت نشد.")
        return

    new_posts = [p for p in posts if p["id"] not in history]

    if not new_posts:
        if EVENT_NAME in ("workflow_dispatch", "repository_dispatch"):
            print("اجرای دستی یا فرمان VIP: ارسال آخرین خبر...")
            target_post = posts[-1]
        else:
            print("همه اخبار فعلی قبلاً در X منتشر شده‌اند.")
            return
    else:
        target_post = new_posts[-1]

    has_vid = bool(target_post.get("video_url"))
    tweet_text = format_for_x(target_post["text"], has_video=has_vid)
    if not tweet_text:
        return

    post_with_real_browser(tweet_text, target_post["photo_url"], target_post.get("video_url"))

    for p in posts:
        if p["id"] not in history:
            history.append(p["id"])
    save_history(history)

if __name__ == "__main__":
    main()
