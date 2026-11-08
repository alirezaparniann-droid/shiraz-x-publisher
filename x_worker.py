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

# بانک هشتگ‌های کوتاه و پربازدید متناسب با موضوع خبر
TAG_RULES = {
    "اصابت|شلیک|موشک|پدافند|انفجار|سپاه|تنگه هرمز|ارتش|حمله": ["#جنگ", "#انفجار"],
    "حادثه|آتش|تصادف|اورژانس|پلیس|بازداشت|قتل|سرقت|زلزله": ["#حوادث", "#خبر_فوری"],
    "فوتبال|فجر|سپاسی|لیگ|ورزش|استقلال|پرسپولیس|ورزشگاه": ["#فجر_سپاسی", "#فوتبال"],
    "شهرداری|مترو|ترافیک|شورای_شهر|عمران|خیابان|پل": ["#شیراز", "#شهرداری_شیراز"],
    "هواشناسی|باران|برف|آلودگی|دما|سد|آب|برق": ["#شیراز", "#هواشناسی"],
    "طلا|سکه|دلار|تورم|بازار|قیمت|اقتصاد|مسکن": ["#اقتصاد", "#طلا"],
    "حافظیه|سعدی|تخت_جمشید|گردشگری|مسافر|میراث": ["#شیراز", "#شیرازگردی"]
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

def calc_x_len(text):
    """محاسبه دقیق طول کاراکتر طبق استاندارد X (حروف فارسی ۱ واحد، ایموجی ۲ واحد)"""
    weight = 0
    for ch in text:
        if ord(ch) >= 0x2300:
            weight += 2
        else:
            weight += 1
    return weight

def clean_line_prefix(line):
    line = re.sub(r"^[\s🔴🟠🟡🟢🔵🟣⚫️⚪️🟤🚨📌⚽️🌤🔹🔸▫️▪️•\-_#*«»🎬⭕️✅🎥]+", "", line)
    return to_persian_num(line.strip())

def style_lead_with_diamond(lead_text):
    """افزودن علامت 🔸 بعد از منبع نقل‌قول (مانند: خبرنگار صداوسیما: 🔸...)"""
    if "🔸" in lead_text:
        return lead_text
    match = re.match(r"^([^:：]{3,35}[:：])\s*(.+)$", lead_text)
    if match:
        return f"{match.group(1)} 🔸{match.group(2)}"
    return f"🔸{lead_text}"

def select_top_hashtags(raw_text):
    tags = []
    for pattern, pattern_tags in TAG_RULES.items():
        if re.search(pattern, raw_text):
            for t in pattern_tags:
                if t not in tags:
                    tags.append(t)
    if not tags:
        tags = ["#شیراز", "#اخبار_شیراز"]
    elif len(tags) == 1:
        tags.append("#شیراز")
    return " ".join(tags[:2])

def split_text_cleanly(text, max_weight):
    """برش متن در انتهای جمله یا ویرگول یا فاصله، بدون ناقص شدن کلمات"""
    if calc_x_len(text) <= max_weight:
        return text, ""

    # پیدا کردن بیشترین کاراکتر مجاز
    cut_idx = len(text)
    while cut_idx > 0 and calc_x_len(text[:cut_idx]) > max_weight:
        cut_idx -= 1

    candidate = text[:cut_idx]

    # اولویت ۱: برش در پایان جمله (. یا ! یا ؟ یا /)
    for sep in [". ", "!\n", "؟ ", ". ", "/ "]:
        pos = candidate.rfind(sep)
        if pos > int(cut_idx * 0.55):
            part1 = candidate[:pos + 1].strip()
            part2 = text[pos + 1:].strip()
            return part1, part2

    # اولویت ۲: برش در ویرگول (،)
    for sep in ["، ", "؛ "]:
        pos = candidate.rfind(sep)
        if pos > int(cut_idx * 0.60):
            part1 = candidate[:pos + 1].strip()
            part2 = text[pos + 1:].strip()
            return part1, part2

    # اولویت ۳: برش در آخرین فاصله بین کلمات
    pos = candidate.rfind(" ")
    if pos > 0:
        return candidate[:pos].strip(), text[pos:].strip()

    return candidate.strip(), text[cut_idx:].strip()

def build_tweet_boxes(raw_text, has_video=False):
    """
    ساخت کادرهای توییت دقیقاً مشابه الگوی درخواستی:
    ⭕️ 🎥تیتر

    ✅ لید کامل (همراه با 🔸)
    🛑 @shirazlastnews
    #هشتگ۱ #هشتگ۲
    (اگر طولانی بود، ادامه لید به صورت کامل در کادر دوم قرار می‌گیرد)
    """
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

    # حذف خطوط اضافی تلگرام (منبع خبر، لینک، آیدی و هشتگ‌های قدیمی)
    content_lines = []
    for l in lines:
        if any(
            skip in l
            for skip in [
                "منبع خبر:",
                "t.me/",
                "@shirazlastnews",
                "آخرین خبرهای شیراز",
                "حجم بهینه‌شده:",
                "#️⃣"
            ]
        ) or l.startswith("#"):
            continue
        content_lines.append(l)

    if not content_lines:
        return []

    is_vid = has_video or ("🎥" in raw_text) or ("ویدیو" in lines[0]) or ("فیلم" in lines[0])
    raw_title = clean_line_prefix(content_lines[0])
    title_prefix = "⭕️ 🎥" if is_vid else "⭕️ "
    title_line = f"{title_prefix}{raw_title}"

    # جمع‌آوری کامل لید خبر از تمام خطوط متنی باقی‌مانده
    lead_parts = [clean_line_prefix(l) for l in content_lines[1:] if len(clean_line_prefix(l)) > 10]
    full_lead_raw = " ".join(lead_parts).strip()

    hashtags = select_top_hashtags(raw_text)
    footer_block = f"🛑 @shirazlastnews\n{hashtags}"

    # اگر خبر فقط تیتر داشت
    if not full_lead_raw:
        box1 = f"{title_line}\n\n{footer_block}"
        return [box1]

    styled_lead = style_lead_with_diamond(full_lead_raw)
    lead_line = f"✅ {styled_lead}"

    # بررسی جا شدن کامل در ۱ توییت (حداکثر ۲۷۶ کاراکتر استاندارد X)
    single_tweet = f"{title_line}\n\n{lead_line}\n{footer_block}"
    if calc_x_len(single_tweet) <= 276:
        return [single_tweet]

    # اگر مجموع تیتر و لید کامل از ۲۷۶ کاراکتر بیشتر بود -> تقسیم در کادر اول و کادر دوم (بدون حذف هیچ کلمه‌ای)
    boxes = []
    header_and_check = f"{title_line}\n\n✅ "
    avail_in_box1 = 272 - calc_x_len(header_and_check)

    if avail_in_box1 >= 70:
        part1, remaining_lead = split_text_cleanly(styled_lead, avail_in_box1)
        boxes.append(f"{title_line}\n\n✅ {part1}")
    else:
        # اگر خود تیتر خیلی طولانی بود، تیتر در کادر اول و کل لید در کادر دوم قرار می‌گیرد
        boxes.append(title_line)
        remaining_lead = styled_lead

    # قرار دادن ادامه کامل لید + امضا + هشتگ در کادر دوم (و سوم در صورت نیاز)
    while remaining_lead:
        candidate_last_box = f"✅ {remaining_lead}\n{footer_block}"
        if calc_x_len(candidate_last_box) <= 276:
            boxes.append(candidate_last_box)
            break
        else:
            part_next, remaining_lead = split_text_cleanly(remaining_lead, 265)
            boxes.append(f"✅ {part_next}")
            if len(boxes) >= 3:
                # در کادر آخر امضا و هشتگ را می‌چسبانیم
                boxes[-1] = f"✅ {part_next}\n{footer_block}"
                break

    return boxes

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

        video_url = None
        video_elem = wrap.select_one("video.tgme_widget_message_video")
        if video_elem and video_elem.get("src"):
            video_url = video_elem.get("src")

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
    if video_url:
        try:
            print("در حال دانلود ویدیوی خبر برای X...")
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
                    print(f"ویدیو دانلود شد ({round(size / (1024*1024), 1)} MB).")
                    return vid_path, True
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

def post_thread_with_real_browser(tweet_boxes, photo_url=None, video_url=None):
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
            viewport={"width": 1280, "height": 900},
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

        # ۱. آماده‌سازی کادر اول و آپلود رسانه
        textbox_0 = page.locator('[data-testid="tweetTextarea_0"]').first
        textbox_0.wait_for(state="visible", timeout=30000)
        textbox_0.click(force=True)
        page.wait_for_timeout(800)

        if media_path and os.path.exists(media_path):
            try:
                file_input = page.locator('input[data-testid="fileInput"]').first
                file_input.set_input_files(media_path)
                if is_video:
                    print("ویدیو بارگذاری شد؛ انتظار برای پردازش...")
                    page.wait_for_timeout(18000)
                else:
                    print("تصویر بارگذاری شد...")
                    page.wait_for_timeout(6000)
            except Exception as e:
                print(f"ادامه بدون پیوست فایل رسانه: {e}")

        # ۲. نوشتن کادر اول و در صورت نیاز افزودن کادر دوم (رشته‌توییت همزمان)
        for idx, box_text in enumerate(tweet_boxes):
            if idx > 0:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                add_btn = page.locator('[data-testid="addButton"]').first
                if add_btn.count() > 0:
                    # کلیک مستقیم جاوااسکریپت روی دکمه + برای عبور از هر لایه مزاحم
                    add_btn.evaluate("el => el.click()")
                    print(f"کادر شماره {idx + 1} رشته‌توییت باز شد.")
                    page.wait_for_timeout(1800)

            current_box = page.locator(f'[data-testid="tweetTextarea_{idx}"]').first
            current_box.wait_for(state="visible", timeout=20000)
            current_box.click(force=True)
            page.wait_for_timeout(500)
            current_box.fill(box_text + " ")
            page.wait_for_timeout(1200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # ۳. ارسال نهایی (تک‌توییت یا رشته‌توییت کامل)
        post_button = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first
        for _ in range(10):
            if post_button.get_attribute("aria-disabled") == "true":
                page.wait_for_timeout(2000)
            else:
                break

        if post_button.count() > 0:
            post_button.evaluate("el => el.click()")
            print(f"دستور انتشار ({len(tweet_boxes)} کادر) اجرا شد.")
        else:
            page.keyboard.press("Control+Enter")

        page.wait_for_timeout(8000 if is_video else 6000)
        print("✅ خبر به صورت کامل و بدون بریدگی در X منتشر شد!")
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
            print("اجرای دستی: ارسال آخرین خبر با قالب کامل جدید...")
            target_post = posts[-1]
        else:
            print("همه اخبار فعلی قبلاً در X منتشر شده‌اند.")
            return
    else:
        target_post = new_posts[-1]

    has_vid = bool(target_post.get("video_url"))
    tweet_boxes = build_tweet_boxes(target_post["text"], has_video=has_vid)
    if not tweet_boxes:
        return

    print(f"تعداد کادرهای آماده ارسال برای این خبر: {len(tweet_boxes)}")
    for i, b in enumerate(tweet_boxes, 1):
        print(f"--- کادر {i} ({calc_x_len(b)} کاراکتر) ---\n{b}\n")

    post_thread_with_real_browser(tweet_boxes, target_post["photo_url"], target_post.get("video_url"))

    for p in posts:
        if p["id"] not in history:
            history.append(p["id"])
    save_history(history)

if __name__ == "__main__":
    main()
