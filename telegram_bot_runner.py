"""
ANTIGRAVITY Telegram Bot Runner
Provides live interactive bot handling for @kino05_promaks_bot.
Handles /start, /id, grades lookup, homework checking, and automatic account binding via contact/phone.
"""
import os
import time
import threading
import requests
from dotenv import load_dotenv
from database import get_db_connection
import telegram_service

load_dotenv()

def get_bot_token():
    return telegram_service.get_bot_token()

def send_bot_reply(chat_id, text, reply_markup=None):
    token = get_bot_token()
    if not token:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=8)
        return res.json().get("ok", False)
    except Exception as e:
        print(f"[Bot Runner Error] send_bot_reply: {e}")
        return False

def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "🆔 Mening Chat ID raqamim"}],
            [{"text": "📚 Oxirgi baholarim"}, {"text": "📝 Uyga vazifalarim"}],
            [{"text": "📞 Kontaktni ulash", "request_contact": True}],
            [{"text": "ℹ️ Markaz haqida"}]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def handle_start(chat_id, user_info):
    first_name = user_info.get("first_name", "Foydalanuvchi")
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # Automatically save/update this chat_id as admin_telegram_chat_id
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_telegram_chat_id', ?)", (str(chat_id),))
    conn.commit()

    cursor.execute("SELECT * FROM students WHERE telegram_chat_id = ? OR parent_telegram_chat_id = ?", (str(chat_id), str(chat_id)))
    student = cursor.fetchone()
    conn.close()

    if student:
        welcome_text = (
            f"Assalomu alaykum, <b>{first_name}</b>! 👋\n\n"
            f"Siz ANTIGRAVITY tizimida <b>{student['first_name']} {student['last_name']}</b> sifatida ulangansiz.\n\n"
            f"🆔 <b>Sizning Chat ID:</b> <code>{chat_id}</code>\n"
            f"👤 <b>O'quvchi ID:</b> #{student['id']}\n\n"
            "✅ Profilingiz to'liq ulangan! Barcha yangi baholar, uyga vazifalar va xabarlar shu yerga keladi."
        )
    else:
        welcome_text = (
            f"Assalomu alaykum, <b>{first_name}</b>! 👋\n\n"
            "<b>ANTIGRAVITY Ta'lim Markazi</b> rasmiy botiga xush kelibsiz!\n\n"
            f"🆔 <b>Sizning Telegram Chat ID raqamingiz:</b>\n<code>{chat_id}</code>\n\n"
            "🎉 <b>Bot tizimga muvaffaqiyatli ulandi!</b>\n"
            "Ushbu hisob tizimda faol bildirishnoma qabul qiluvchi sifatida saqlandi.\n\n"
            "<b>O'quvchi profilini ulash:</b>\n"
            "Agar o'quvchi bo'lsangiz, pastdagi <b>«📞 Kontaktni ulash»</b> tugmasini bosing yoki o'quvchi ID raqamingizni (masalan: <b>ID: 15</b>) yozib yuboring."
        )
    send_bot_reply(chat_id, welcome_text, get_main_keyboard())

def handle_chat_id(chat_id):
    text = (
        f"🆔 <b>Sizning Telegram Chat ID:</b> <code>{chat_id}</code>\n\n"
        "Nusxa olish uchun raqam ustiga bosing.\n"
        "Ushbu raqamni <a href=\"http://10.91.161.247:5000/student/login\">ANTIGRAVITY shaxsiy kabinetida</a> "
        "saqlasangiz, barcha baholar va dars ma'lumotlari sizga avtomatik yetkaziladi."
    )
    send_bot_reply(chat_id, text, get_main_keyboard())

def handle_my_grades(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE telegram_chat_id = ? OR parent_telegram_chat_id = ?", (str(chat_id), str(chat_id)))
    students = cursor.fetchall()

    if not students:
        conn.close()
        send_bot_reply(
            chat_id,
            "⚠️ <b>Profilingiz topilmadi!</b>\n\n"
            "Baholaringizni ko'rish uchun avval hisobingizni botga ulang.\n"
            "«📞 Kontaktni ulash» tugmasini bosing yoki telefon raqamingizni (masalan: 901234567) yuboring.",
            get_main_keyboard()
        )
        return

    for st in students:
        cursor.execute("""
        SELECT * FROM grades 
        WHERE student_id = ? 
        ORDER BY assessment_date DESC, id DESC 
        LIMIT 5
        """, (st['id'],))
        grades = cursor.fetchall()

        cursor.execute("SELECT ROUND(AVG(score), 1) as avg_score FROM grades WHERE student_id = ?", (st['id'],))
        avg_row = cursor.fetchone()
        avg_score = avg_row['avg_score'] if avg_row and avg_row['avg_score'] else '—'

        text = f"📚 <b>{st['first_name']} {st['last_name']}</b> — Oxirgi baholari:\n"
        text += f"⭐️ <b>Umumiy o'rtacha ball:</b> {avg_score}\n\n"

        if grades:
            for g in grades:
                score_icon = "🟢" if g['score'] >= 80 else ("🟡" if g['score'] >= 60 else "🔴")
                text += f"{score_icon} <b>{g['subject']}</b>: {g['score']} ball ({g['assessment_date']})\n"
                if g['comment']:
                    text += f"   <i>Izoh: {g['comment']}</i>\n"
        else:
            text += "<i>Hozircha baholar mavjud emas.</i>\n"

        text += "\nTo'liq ma'lumot shaxsiy kabinetda."
        send_bot_reply(chat_id, text, get_main_keyboard())

    conn.close()

def handle_my_homework(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE telegram_chat_id = ?", (str(chat_id),))
    student = cursor.fetchone()

    if not student:
        conn.close()
        send_bot_reply(
            chat_id,
            "⚠️ <b>Profilingiz topilmadi!</b>\n\n"
            "Vazifalarni ko'rish uchun avval profilingizni botga ulang. «📞 Kontaktni ulash» tugmasini bosing.",
            get_main_keyboard()
        )
        return

    group_id = student['group_id']
    if not group_id:
        conn.close()
        send_bot_reply(chat_id, "Siz hali guruhga biriktirilmagansiz.", get_main_keyboard())
        return

    cursor.execute("""
    SELECT h.*, c.title as course_title,
           hs.status as submission_status, hs.score as submission_score
    FROM homework h
    LEFT JOIN courses c ON h.course_id = c.id
    LEFT JOIN homework_submissions hs ON hs.homework_id = h.id AND hs.student_id = ?
    WHERE h.group_id = ?
    ORDER BY h.due_date DESC
    LIMIT 5
    """, (student['id'], group_id))
    hws = cursor.fetchall()
    conn.close()

    if not hws:
        send_bot_reply(chat_id, "📝 <b>Sizning guruhingizda hozircha faol uyga vazifalar yo'q.</b>", get_main_keyboard())
        return

    text = f"📝 <b>Guruhdagi Uyga Vazifalar ({student['first_name']} uchun):</b>\n\n"
    for hw in hws:
        status_str = "✅ Topshirilgan" if hw['submission_status'] == 'submitted' else (
            f"⭐️ Baholandi: {hw['submission_score']} ball" if hw['submission_status'] == 'graded' else "⏳ Topshirilmagan"
        )
        text += (
            f"📌 <b>{hw['title']}</b>\n"
            f"Fan: {hw['course_title'] or 'Asosiy fan'}\n"
            f"Muddati: {hw['due_date']}\n"
            f"Holati: <b>{status_str}</b>\n\n"
        )
    text += "Topshiriqni platformadagi shaxsiy kabinetingiz orqali topshirishingiz mumkin."
    send_bot_reply(chat_id, text, get_main_keyboard())

def handle_center_info(chat_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()

    text = (
        f"🏛 <b>{settings.get('center_name', 'ANTIGRAVITY Ta\'lim Markazi')}</b>\n\n"
        f"📞 <b>Telefon:</b> {settings.get('center_phone', '+998 71 200 45 45')}\n"
        f"📍 <b>Manzil:</b> {settings.get('center_address', 'Toshkent sh.')}\n"
        f"⏰ <b>Ish vaqti:</b> {settings.get('center_work_hours', 'Dush-Shan: 08:00 - 20:00')}\n"
        f"🌐 <b>Lokal Platforma:</b> <a href=\"http://10.91.161.247:5000\">http://10.91.161.247:5000</a>"
    )
    send_bot_reply(chat_id, text, get_main_keyboard())

def link_phone_number(chat_id, phone):
    clean_phone = "".join([c for c in phone if c.isdigit()])
    if len(clean_phone) > 9:
        clean_phone = clean_phone[-9:]

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT * FROM students 
    WHERE REPLACE(REPLACE(REPLACE(REPLACE(phone, '+', ''), ' ', ''), '-', ''), '(', '') LIKE ?
       OR REPLACE(REPLACE(REPLACE(REPLACE(parent_phone, '+', ''), ' ', ''), '-', ''), '(', '') LIKE ?
    """, (f"%{clean_phone}", f"%{clean_phone}"))
    students = cursor.fetchall()

    if students:
        found_names = []
        for s in students:
            s_clean = "".join([c for c in (s['phone'] or '') if c.isdigit()])
            if clean_phone in s_clean:
                cursor.execute("UPDATE students SET telegram_chat_id = ? WHERE id = ?", (str(chat_id), s['id']))
                found_names.append(f"{s['first_name']} {s['last_name']} (O'quvchi)")
            else:
                cursor.execute("UPDATE students SET parent_telegram_chat_id = ? WHERE id = ?", (str(chat_id), s['id']))
                found_names.append(f"{s['first_name']} {s['last_name']} (Ota-ona)")

        conn.commit()
        conn.close()

        names_str = ", ".join(found_names)
        send_bot_reply(
            chat_id,
            f"🎉 <b>Muvaffaqiyatli bog'landi!</b>\n\n"
            f"Profilingiz topildi: <b>{names_str}</b>\n"
            f"Endi barcha baholar, ogohlantirishlar va uyga vazifalar to'g'ridan-to'g'ri Telegramingizga keladi!",
            get_main_keyboard()
        )
    else:
        conn.close()
        send_bot_reply(
            chat_id,
            f"Telefon raqam ({phone}) bo'yicha o'quvchi topilmadi.\n\n"
            "Iltimos, o'quvchi ID raqamingizni (masalan: <b>ID: 15</b> yoki <b>15</b>) yozib yuboring yoki markaz ma'muriyatiga murojaat qiling.",
            get_main_keyboard()
        )

def process_message(msg):
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    if not chat_id:
        return

    text = msg.get("text", "").strip()
    contact = msg.get("contact")

    if contact and contact.get("phone_number"):
        phone = contact.get("phone_number")
        link_phone_number(chat_id, phone)
        return

    if text.startswith("/start"):
        handle_start(chat_id, msg.get("from", {}))
    elif text == "🆔 Mening Chat ID raqamim" or text.startswith("/id"):
        handle_chat_id(chat_id)
    elif text == "📚 Oxirgi baholarim" or text.startswith("/baholar"):
        handle_my_grades(chat_id)
    elif text == "📝 Uyga vazifalarim" or text.startswith("/vazifalar"):
        handle_my_homework(chat_id)
    elif text == "ℹ️ Markaz haqida":
        handle_center_info(chat_id)
    elif any(c.isdigit() for c in text):
        digits = "".join([c for c in text if c.isdigit()])
        if len(digits) >= 7:
            link_phone_number(chat_id, digits)
        elif len(digits) > 0 and len(digits) <= 5:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM students WHERE id = ?", (int(digits),))
            st = cursor.fetchone()
            if st:
                cursor.execute("UPDATE students SET telegram_chat_id = ? WHERE id = ?", (str(chat_id), st['id']))
                conn.commit()
                conn.close()
                send_bot_reply(
                    chat_id,
                    f"🎉 <b>Muvaffaqiyatli bog'landi!</b>\n\n"
                    f"O'quvchi: <b>{st['first_name']} {st['last_name']}</b> (#{st['id']})\n"
                    "Telegram Chat ID raqamingiz muvaffaqiyatli saqlandi!",
                    get_main_keyboard()
                )
            else:
                conn.close()
                send_bot_reply(chat_id, f"#{digits} raqamli o'quvchi topilmadi.", get_main_keyboard())
        else:
            handle_start(chat_id, msg.get("from", {}))
    else:
        handle_start(chat_id, msg.get("from", {}))

def run_polling_loop(stop_event=None):
    print("[Bot Runner] Starting Telegram Bot Polling Listener for @kino05_promaks_bot...")
    offset = 0
    while stop_event is None or not stop_event.is_set():
        token = get_bot_token()
        if not token:
            time.sleep(5)
            continue

        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"offset": offset, "timeout": 8}
            res = requests.get(url, params=params, timeout=12)
            data = res.json()

            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update.get("update_id", 0) + 1
                    msg = update.get("message")
                    if msg:
                        process_message(msg)
            else:
                time.sleep(3)
        except Exception as e:
            time.sleep(3)

def start_bot_background_thread():
    t = threading.Thread(target=run_polling_loop, daemon=True)
    t.start()
    return t

if __name__ == '__main__':
    run_polling_loop()
