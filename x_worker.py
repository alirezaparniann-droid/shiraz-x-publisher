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

# ۱. بانک کلمات کلیدی مستقیم که در صورت وجود در متن، مستقیماً هشتگ می‌شوند
DIRECT_ENTITY_TAGS = {
    "فجر سپاسی|فجرسپاسی|فجر شهید سپاسی": "#فجر_سپاسی",
    "پرسپولیس": "#پرسپولیس",
    "استقلال": "#استقلال",
    "سپاهان": "#سپاهان",
    "تراکتور": "#تراکتور",
    "تیم ملی": "#تیم_ملی",
    "تخت جمشید|پارسه": "#تخت_جمشید",
    "حافظیه|حافظ": "#حافظیه",
    "سعدیه|سعدی": "#سعدیه",
    "شاهچراغ": "#شاهچراغ",
    "دروازه قرآن": "#دروازه_قرآن",
    "باغ ارم": "#باغ_ارم",
    "بازار وکیل": "#بازار_وکیل",
    "مترو شیراز|خط مترو": "#مترو_شیراز",
    "شهرداری شیراز|شهردار شیراز": "#شهرداری_شیراز",
    "دانشگاه شیراز": "#دانشگاه_شیراز",
    "علوم پزشکی شیراز": "#علوم_پزشکی_شیراز",
    "تنگه هرمز": "#تنگه_هرمز",
    "خلیج فارس": "#خلیج_فارس",
    "صدرا|شهر صدرا": "#شهر_صدرا",
    "مرودشت": "#مرودشت",
    "کازرون": "#کازرون",
    "جهرم": "#جهرم",
    "لارستان|شهر لار": "#لارستان",
    "فسا": "#فسا",
    "داراب": "#داراب",
    "فیروزآباد": "#فیروزآباد",
    "ممسنی|نورآباد": "#ممسنی",
    "آباده": "#آباده",
    "سپیدان|مارگون": "#سپیدان",
    "پاسارگاد": "#پاسارگاد"
}

# ۲. بانک جامع هشتگ‌های ترند و پربازدید توییتر فارسی بر اساس موضوع خبر
TRENDING_CATEGORY_RULES = [
    (
        "اصابت|شلیک|موشک|پدافند|انفجار|سپاه|تنگه هرمز|ارتش|حمله|جنگ|پهپاد|نظامی|امنیتی",
        ["#فوری", "#ایران", "#خبر_فوری", "#انفجار", "#سپاه", "#امنیت"]
    ),
    (
        "طلا|سکه|دلار|یورو|تورم|بازار|قیمت|اقتصاد|مسکن|بورس|یارانه|کالابرگ|معیشت|خودرو|بانک",
        ["#دلار", "#طلا", "#سکه", "#اقتصاد", "#تورم", "#قیمت_طلا"]
    ),
    (
        "فوتبال|فجر|سپاسی|لیگ برتر|ورزش|استقلال|پرسپولیس|ورزشگاه پارس|گل |داور|جام حذفی",
        ["#فوتبال", "#لیگ_برتر", "#فجر_سپاسی", "#ورزش_فارس", "#ورزشی"]
    ),
    (
        "ترافیک|مسدود|راهور|تصادف|دروازه قرآن|بلوار چمران|کمربندی|جاده|پلیس راه",
        ["#ترافیک", "#شیراز", "#راهور", "#حوادث_شیراز", "#خبر_فوری"]
    ),
    (
        "حادثه|آتش‌سوزی|آتش سوزی|اورژانس|پلیس|بازداشت|قتل|سرقت|زورگیری|زلزله|سیل|غرق",
        ["#حوادث", "#خبر_فوری", "#فوری", "#پلیس", "#اورژانس", "#حوادث_شیراز"]
    ),
    (
        "شهرداری|مترو|شورای شهر|عمرانی|خیابان|پل |بزرگراه|آسفالت|بوستان|تاکسی|اتوبوس",
        ["#شهرداری_شیراز", "#کلانشهر_شیراز", "#مترو_شیراز", "#شورای_شهر"]
    ),
    (
        "هواشناسی|باران|برف|آلودگی هوا|دما|سد درودزن|آبفا|قطعی برق|قطعی آب|طوفان|گردوخاک",
        ["#هواشناسی", "#باران", "#قطعی_برق", "#آلودگی_هوا", "#وضعیت_هوا"]
    ),
    (
        "تعطیل|تعطیلی|مدارس|دانشگاه|آموزش و پرورش|کنکور|دانشجو|فرهنگیان|امتحانات",
        ["#تعطیلی_مدارس", "#فوری", "#دانشگاه_شیراز", "#آموزش_و_پرورش", "#دانشجو"]
    ),
    (
        "دادگستری|قوه قضاییه|دادستان|حکم|پرونده|تعزیرات|قاچاق",
        ["#قوه_قضاییه", "#پلیس", "#خبر_فوری", "#حوادث"]
    ),
    (
        "حافظیه|سعدی|تخت جمشید|گردشگری|مسافر|میراث فرهنگی|نوروز|کافه|بافت تاریخی|هتل",
        ["#شیرازگردی", "#گردشگری", "#تخت_جمشید", "#حافظیه", "#ایرانگردی"]
    ),
    (
        "رییس جمهور|رئیس جمهور|دولت|مجلس|وزیر|استاندار فارس|فرماندار|انتخابات|سیاسی",
        ["#ایران", "#دولت", "#مجلس", "#استان_فارس", "#سیاسی"]
    )
]

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
    """محاسبه دقیق وزن کاراکترها طبق الگوریتم ۲۸۰ کاراکتری X"""
    weight = 0
    for ch in text:
        if ord(ch) >= 0x2300:
            weight += 2
        else:
            weight += 1
    return weight

def clean_line_text(line):
    """حذف ایموجی‌های تزیینی تلگرام و مقدمه‌چینی‌های اضافی خبرگزاری‌ها"""
    line = re.sub(r"^[\s🔴🟠🟡🟢🔵🟣⚫️⚪️🟤🚨📌⚽️🌤🔹🔸▫️▪️•\-_#*«»🎬⭕️✅🎥]+", "", line)
    line = re.sub(
        r"^به گزارش\s+(خبرنگار\s+|گروه\s+[^،]{2,20}\s+)?(خبرگزاری\s+|پایگاه خبری\s+)?(ایرنا|مهر|تسنیم|ایسنا|فارس|صدا و سیما|صداوسیما|دانشجو)[^،:]{0,25}[،:]\s*",
        "",
        line
    )
    line = re.sub(r"^[\s🔹🔸▫️▪️•\-]+", "", line)
    return to_persian_num(line.strip())

def ensure_sentence_end(text):
    t = text.strip().rstrip("،؛:- ")
    if not t:
        return ""
    if t[-1] not in [".", "!", "؟", "»"]:
        t += "."
    return t

def detect_hook_prefix(raw_text, has_video=False):
    if re.search("فوری|انفجار|اصابت|شلیک|زلزله|آتش‌سوزی|تصادف شدید|مسدود", raw_text):
        return "🔴 فوری:"
    if has_video or "🎥" in raw_text or "ویدیو" in raw_text:
        return "🎥 ویدیو:"
    if re.search("فوتبال|فجر|سپاسی|لیگ برتر|گل |ورزشگاه|پرسپولیس|استقلال", raw_text):
        return "⚽️ ورزشی:"
    if re.search("هواشناسی|باران|برف|دما|آلودگی|هشدار", raw_text):
        return "🌤 هواشناسی:"
    if re.search("ترافیک|شهرداری|مترو|عمرانی|خیابان|بلوار", raw_text):
        return "🚨 اطلاعیه شهری:"
    return "📌 شیراز:"

def select_trending_hashtags(raw_text, max_count=6):
    """
    انتخاب هوشمند ۵ تا ۶ هشتگ ترکیبی از:
    ۱. موجودیت‌های دقیق داخل خبر (شهر، تیم، مکان)
    ۲. هشتگ‌های ترند توییتر فارسی متناسب با موضوع خبر
    ۳. هشتگ‌های پایه شیراز و فارس
    """
    tags = []

    # اگر خبر مربوط به شیراز یا فارس است، همیشه #شیراز اول باشد
    if re.search("شیراز|فارس|مرودشت|کازرون|جهرم|لار|فسا|صدرا", raw_text):
        tags.append("#شیراز")

    # ۱. استخراج موجودیت‌های مستقیم از داخل متن خبر
    for pattern, entity_tag in DIRECT_ENTITY_TAGS.items():
        if re.search(pattern, raw_text) and entity_tag not in tags:
            tags.append(entity_tag)

    # ۲. افزودن هشتگ‌های ترند موضوعی توییتر
    for pattern, cat_tags in TRENDING_CATEGORY_RULES:
        if re.search(pattern, raw_text):
            for ct in cat_tags:
                if ct not in tags:
                    tags.append(ct)

    # ۳. تکمیل با هشتگ‌های پربازدید عمومی شیراز و ایران در صورت کم بودن
    fallback_trending = ["#شیراز", "#اخبار_شیراز", "#فارس", "#خبر_فوری", "#ایران"]
    for ft in fallback_trending:
        if len(tags) >= max_count:
            break
        if ft not in tags:
            tags.append(ft)

    return tags[:max_count]

def split_on_sentence_boundary(text, max_weight):
    """شکستن هوشمند متن دقیقاً روی نقطه پایان جملات (بدون بریدن وسط کلمه)"""
    if calc_x_len(text) <= max_weight:
        return text, ""

    cut_idx = len(text)
    while cut_idx > 0 and calc_x_len(text[:cut_idx]) > max_weight:
        cut_idx -= 1

    candidate = text[:cut_idx]

    for sep in [". ", "!\n", "؟ ", "؛ ", "/ "]:
        pos = candidate.rfind(sep)
        if pos > int(cut_idx * 0.45):
            part1 = ensure_sentence_end(candidate[:pos + 1])
            part2 = text[pos + 1:].strip()
            return part1, part2

    pos_comma = candidate.rfind("، ")
    if pos_comma > int(cut_idx * 0.55):
        part1 = candidate[:pos_comma].strip() + "."
        part2 = text[pos_comma + 1:].strip()
        return part1, part2

    pos_space = candidate.rfind(" ")
    if pos_space > 0:
        return candidate[:pos_space].strip(), text[pos_space:].strip()

    return candidate.strip(), text[cut_idx:].strip()

def build_tweet_boxes(raw_text, has_video=False):
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

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

    hook = detect_hook_prefix(raw_text, has_video=has_video)
    raw_title = clean_line_text(content_lines[0]).rstrip(".")
    title_line = f"{hook} {raw_title}"

    lead_parts = [clean_line_text(l) for l in content_lines[1:] if len(clean_line_text(l)) > 10]
    full_lead = ensure_sentence_end(" ".join(lead_parts))

    # دریافت ۶ هشتگ ترند مرتبط با موضوع خبر
    all_tags = select_trending_hashtags(raw_text, max_count=6)
    hashtags_full_str = " ".join(all_tags[:5])

    # حالت اول: خبر فقط تیتر دارد
    if not full_lead:
        return [f"{title_line}\n\n{hashtags_full_str}\n🛑 @shirazlastnews"]

    # بررسی جا شدن کل خبر با ۵ یا ۶ هشتگ در یک توییت واحد
    for tag_cnt in [6, 5, 4]:
        tags_str = " ".join(all_tags[:tag_cnt])
        single_candidate = f"{title_line}\n\n{full_lead}\n\n{tags_str}"
        if calc_x_len(single_candidate) <= 275:
            return [single_candidate]

    # حالت دوم: خبر طولانی است -> ساخت رشته‌توییت (Thread) با ۴ تا ۵ هشتگ ترند
    raw_boxes = []
    box1_tags_str = " ".join(all_tags[:4])
    overhead_box1 = calc_x_len(title_line) + calc_x_len(box1_tags_str) + 14
    avail_lead_box1 = 272 - overhead_box1

    if avail_lead_box1 >= 65:
        lead_part1, remaining_lead = split_on_sentence_boundary(full_lead, avail_lead_box1)
        raw_boxes.append(f"{title_line}\n\n{lead_part1}\n\n{box1_tags_str}")
    else:
        raw_boxes.append(f"{title_line}\n\n{box1_tags_str}")
        remaining_lead = full_lead

    # در آخرین توییتِ رشته، علاوه بر آیدی کانال، هشتگ‌های مکمل هم قرار می‌گیرند
    extra_tags_str = " ".join(all_tags[2:6]) if len(all_tags) > 2 else box1_tags_str
    footer_ref = f"📢 جزئیات بیشتر در تلگرام:\n🛑 @shirazlastnews\n{extra_tags_str}"

    while remaining_lead:
        remaining_lead = ensure_sentence_end(remaining_lead)
        candidate_final = f"{remaining_lead}\n\n{footer_ref}"
        if calc_x_len(candidate_final) <= 266:
            raw_boxes.append(candidate_final)
            break
        else:
            part_next, remaining_lead = split_on_sentence_boundary(remaining_lead, 258)
            if not remaining_lead:
                raw_boxes.append(f"{part_next}\n\n{footer_ref}")
                break
            raw_boxes.append(part_next)
            if len(raw_boxes) >= 4:
                raw_boxes[-1] = f"{part_next}\n\n{footer_ref}"
                break

    # افزودن شماره (1، 2، 3...) در پایین سمت راست در صورت چندبخشی بودن
    if len(raw_boxes) > 1:
        numbered_boxes = []
        for idx, b_txt in enumerate(raw_boxes, 1):
            numbered_boxes.append(f"{b_txt}\n\u200f{idx}")
        return numbered_boxes

    return raw_boxes

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

        for idx, box_text in enumerate(tweet_boxes):
            if idx > 0:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                add_btn = page.locator('[data-testid="addButton"]').first
                if add_btn.count() > 0:
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
        print("✅ خبر با هشتگ‌های ترند و شماره‌گذاری رشته‌توییت در X منتشر شد!")
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
            print("اجرای دستی: ارسال آخرین خبر با هشتگ‌های ترند جدید...")
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

    print(f"تعداد کادرهای آماده ارسال: {len(tweet_boxes)}")
    for i, b in enumerate(tweet_boxes, 1):
        print(f"--- کادر {i} ({calc_x_len(b)} کاراکتر) ---\n{b}\n")

    post_thread_with_real_browser(tweet_boxes, target_post["photo_url"], target_post.get("video_url"))

    for p in posts:
        if p["id"] not in history:
            history.append(p["id"])
    save_history(history)

if __name__ == "__main__":
    main()
