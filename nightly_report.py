import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID = "30956754"
CHANNEL = "shirazlastnews"

def get_telegram_info():
    try:
        url = f"https://t.me/s/{CHANNEL}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        counter = soup.select_one(".tgme_header_counter")
        subs = counter.get_text(strip=True) if counter else "نامشخص"
        posts = soup.select(".tgme_widget_message")
        last_post_id = posts[-1].get("data-post", "").split("/")[-1] if posts else "0"
        return subs, last_post_id
    except Exception:
        return "نامشخص", "0"

def get_x_count():
    if os.path.exists("posted_x_ids.json"):
        try:
            with open("posted_x_ids.json", "r", encoding="utf-8") as f:
                return len(json.load(f))
        except Exception:
            return 0
    return 0

def main():
    if not BOT_TOKEN:
        print("توکن BOT_TOKEN در Secrets تنظیم نشده است.")
        return

    iran_tz = timezone(timedelta(hours=3, minutes=30))
    now_str = datetime.now(iran_tz).strftime("%Y/%m/%d - %H:%M")
    subs, last_id = get_telegram_info()
    x_count = get_x_count()

    text = (
        f"📊 <b>گزارش شبانه رسانه آخرین خبرهای شیراز</b>\n"
        f"🗓 زمان گزارش: <code>{now_str}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📢 <b>کانال تلگرام (@{CHANNEL}):</b>\n"
        f"👥 تعداد اعضا: <code>{subs}</code>\n"
        f"🔢 آخرین شماره پست کانال: <code>{last_id}</code>\n\n"
        f"🐦 <b>شبکه اجتماعی X (توییتر):</b>\n"
        f"✅ پست‌های منتشرشده اخیر در حافظه: <code>{x_count} پست</code>\n"
        f"⏱ وضعیت ربات: <code>فعال (چرخه ۱۰ دقیقه‌ای)</code>\n\n"
        f"📸 <b>پیج اینستاگرام:</b>\n"
        f"🎯 وضعیت زمان‌بندی: <code>ساعت طلایی فعال</code>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": ADMIN_ID,
        "text": text,
        "parse_mode": "HTML"
    }, timeout=15)
    print("✅ گزارش شبانه به تلگرام ادمین ارسال شد.")

if __name__ == "__main__":
    main()
