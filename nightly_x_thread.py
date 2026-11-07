import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

X_AUTH_TOKEN = os.environ.get("X_AUTH_TOKEN", "").strip()
X_CT0 = os.environ.get("X_CT0", "").strip()
CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "shirazlastnews").strip()

def to_persian_num(text):
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def get_iran_jalali_str():
    iran_now = datetime.now(timezone(timedelta(hours=3, minutes=30)))
    gy, gm, gd = iran_now.year, iran_now.month, iran_now.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm = 1 + (days // 31) if days < 186 else 7 + ((days - 186) // 30)
    jd = 1 + (days % 31) if days < 186 else 1 + ((days - 186) % 30)
    return to_persian_num(f"{jy:04d}/{jm:02d}/{jd:02d}")

def clean_headline(raw_text):
    lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
    if not lines:
        return None
    h = re.sub(r"^[\s🔴🟠🟡🟢🔵🟣⚫️⚪️🟤🚨📌⚽️🌤🔹🔸▫️▪️•\-_#*«»🎬⭕️✅]+", "", lines[0]).strip()
    if any(skip in h for skip in ["صبح بخیر شیراز", "پادکست صوتی", "استوری ویژه", "پنجشنبه‌های گردشگری"]):
        return None
    return to_persian_num(h)

def fetch_top_5_headlines():
    url = f"https://t.me/s/{CHANNEL}"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    soup = BeautifulSoup(resp.text, "html.parser")
    headlines = []
    for wrap in soup.select(".tgme_widget_message"):
        t_el = wrap.select_one(".tgme_widget_message_text")
        if not t_el:
            continue
        h = clean_headline(t_el.get_text("\n"))
        if h and len(h) > 15 and h not in headlines:
            headlines.append(h)
    return headlines[-5:]

def post_single_box(page, text):
    page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    textbox = page.locator('[data-testid="tweetTextarea_0"]').first
    textbox.wait_for(state="visible", timeout=30000)
    textbox.click()
    page.wait_for_timeout(800)
    textbox.fill(text + " ")
    page.wait_for_timeout(1200)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    post_button = page.locator('[data-testid="tweetButton"], [data-testid="tweetButtonInline"]').first
    post_button.evaluate("el => el.click()")
    page.wait_for_timeout(6000)

def main():
    headlines = fetch_top_5_headlines()
    if len(headlines) < 3:
        print("تعداد خبرهای کافی برای خلاصه شبانه یافت نشد.")
        return

    today_fa = get_iran_jalali_str()

    # تقسیم ۵ تیتر مهم روز در ۲ پست مکمل تا کاملاً در محدودیت ۲۸۰ کاراکتر جا شوند
    part1_lines = [f"🌙 مرور مهم‌ترین خبرهای امروز شیراز ({today_fa}) | بخش ۱:\n"]
    for idx, h in enumerate(headlines[:2], 1):
        short_h = h[:85].rsplit(" ", 1)[0] + "…" if len(h) > 85 else h
        part1_lines.append(f"{to_persian_num(idx)}️⃣ {short_h}")
    part1_lines.append("\n#شیراز #اخبار_شیراز")
    tweet_1 = "\n".join(part1_lines)[:275]

    part2_lines = [f"🌙 ادامه مهم‌ترین سرخط‌های امروز شیراز ({today_fa}) | بخش ۲:\n"]
    for idx, h in enumerate(headlines[2:5], 3):
        short_h = h[:62].rsplit(" ", 1)[0] + "…" if len(h) > 62 else h
        part2_lines.append(f"{to_persian_num(idx)}️⃣ {short_h}")
    part2_lines.append("\n#شیراز #فارس")
    tweet_2 = "\n".join(part2_lines)[:275]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
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

        post_single_box(page, tweet_1)
        if len(headlines) > 2:
            post_single_box(page, tweet_2)

        print("✅ مرور شبانه اخبار شیراز با موفقیت در X منتشر شد!")
        browser.close()

if __name__ == "__main__":
    main()
