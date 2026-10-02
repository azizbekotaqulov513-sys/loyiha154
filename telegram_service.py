import os
import requests
from dotenv import load_dotenv
from database import get_db_connection

load_dotenv()

def get_setting(key, default=''):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row and row['value']:
        return row['value']
    return os.getenv(key.upper(), default)

def get_bot_token():
    # Priority: DB setting first, then env variable
    token = get_setting('telegram_bot_token', '')
    if not token or token.strip() == '':
        token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    return token.strip() if token else ''

def get_bot_username():
    bot_name = get_setting('telegram_bot_name', '')
    if not bot_name or bot_name.strip() == '':
        bot_name = os.getenv('TELEGRAM_BOT_NAME', '@kino05_promaks_bot')
    return bot_name.strip() if bot_name else '@kino05_promaks_bot'

def get_bot_url():
    bot_url = get_setting('telegram_bot_url', '')
    if not bot_url or bot_url.strip() == '':
        bot_url = os.getenv('TELEGRAM_BOT_URL', 'https://t.me/kino05_promaks_bot')
    return bot_url.strip() if bot_url else 'https://t.me/kino05_promaks_bot'

def log_notification(recipient_type, recipient_name, chat_id, message_type, message_body, status, error_message=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO notification_logs (recipient_type, recipient_name, chat_id, message_type, message_body, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (recipient_type, recipient_name, str(chat_id), message_type, message_body, status, error_message))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error logging notification: {e}")

def send_telegram_raw(chat_id, text):
    """
    Sends raw message to Telegram API.
    Returns (success: bool, status_str: 'sent'|'failed', error: str|None)
    """
    token = get_bot_token()
    if not token:
        return False, "failed", "Telegram bot token sozlanmagan."

    if not chat_id or str(chat_id).strip() == '':
        return False, "failed", "Telegram Chat ID kiritilmagan."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=8)
        data = response.json()
        if response.status_code == 200 and data.get("ok"):
            return True, "sent", None
        else:
            error_desc = data.get("description", f"Telegram API xatosi (status {response.status_code})")
            return False, "failed", error_desc
    except requests.exceptions.RequestException as e:
        return False, "failed", f"Tarmoq yoki ulanish xatosi: {str(e)}"

def verify_bot_token(token):
    """Checks if a bot token is valid via Telegram getMe."""
    if not token or token.strip() == '':
        return False, "Token kiritilmagan"
    try:
        url = f"https://api.telegram.org/bot{token.strip()}/getMe"
        res = requests.get(url, timeout=5)
        data = res.json()
        if res.status_code == 200 and data.get("ok"):
            bot_info = data.get("result", {})
            return True, f"Ulandi: @{bot_info.get('username')} ({bot_info.get('first_name')})"
        else:
            return False, data.get("description", "Token yaroqsiz")
    except Exception as e:
        return False, f"Ulanish xatosi: {str(e)}"

def send_student_grade_notification(student, grade):
    """
    Yangi baho qo'yilganda o'quvchiga Telegram xabari:
    📚 ANTIGRAVITY

    Salom, {Ism}!

    Sizga yangi baho qo‘yildi.

    Fan: {Fan}
    Baho: {Baho}
    Sana: {Sana}
    Izoh: {Izoh}

    ANTIGRAVITY ta'lim markazi
    """
    if get_setting('notification_grade_enabled', 'true').lower() != 'true':
        return False, "O'quvchiga baho bildirishnomasi sozlamalarda o'chirilgan."

    chat_id = student.get('telegram_chat_id')
    student_name = f"{student.get('first_name')} {student.get('last_name')}"
    
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    msg = (
        "📚 <b>ANTIGRAVITY</b>\n\n"
        f"Salom, <b>{student.get('first_name')}</b>!\n\n"
        "Sizga yangi baho qo‘yildi.\n\n"
        f"<b>Fan:</b> {grade.get('subject')}\n"
        f"<b>Baho:</b> {grade.get('score')}\n"
        f"<b>Sana:</b> {grade.get('assessment_date')}\n"
        f"<b>Nazorat turi:</b> {grade.get('assessment_type', 'Dars bahosi')}\n"
        f"<b>Izoh:</b> {grade.get('comment') or 'Muntazam darslarga tayyorlanib boring.'}\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY ta'lim markazi</i>"
    )

    if not chat_id:
        log_notification("student", student_name, "Yo'q", "grade", msg, "failed", "O'quvchining Telegram Chat ID raqami kiritilmagan.")
        return False, "Chat ID yo'q"

    success, status, err = send_telegram_raw(chat_id, msg)
    log_notification("student", student_name, chat_id, "grade", msg, status, err)
    return success, err or "Yuborildi"

def send_parent_grade_notification(student, grade, current_avg):
    """
    Yangi baho qo'yilganda ota-onaga Telegram xabari:
    👨👩👦 ANTIGRAVITY

    Farzandingizga yangi baho qo‘yildi.

    O‘quvchi: Aziz Karimov
    Fan: Ingliz tili
    Baho: 78
    Sana: 12.09.2026

    Joriy o‘rtacha natija: 82
    """
    if get_setting('notification_parent_grade_enabled', 'true').lower() != 'true':
        return False, "Ota-onaga baho bildirishnomasi sozlamalarda o'chirilgan."

    parent_chat_id = student.get('parent_telegram_chat_id')
    parent_name = student.get('parent_name') or f"{student.get('last_name')} ota-onasi"
    student_fullname = f"{student.get('first_name')} {student.get('last_name')}"
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    msg = (
        "👨‍👩‍👦 <b>ANTIGRAVITY</b>\n\n"
        "Farzandingizga yangi baho qo‘yildi.\n\n"
        f"<b>O‘quvchi:</b> {student_fullname}\n"
        f"<b>Fan:</b> {grade.get('subject')}\n"
        f"<b>Baho:</b> {grade.get('score')}\n"
        f"<b>Sana:</b> {grade.get('assessment_date')}\n\n"
        f"<b>Joriy o‘rtacha natija:</b> {round(float(current_avg), 1) if current_avg else '—'}\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY ta'lim markazi</i>"
    )

    if not parent_chat_id:
        log_notification("parent", f"{parent_name} ({student_fullname})", "Yo'q", "parent_grade", msg, "failed", "Ota-onaning Telegram Chat ID raqami kiritilmagan.")
        return False, "Ota-ona Chat ID yo'q"

    success, status, err = send_telegram_raw(parent_chat_id, msg)
    log_notification("parent", f"{parent_name} ({student_fullname})", parent_chat_id, "parent_grade", msg, status, err)
    return success, err or "Yuborildi"

def send_student_warning_notification(student, previous_avg, current_avg, drop_amount):
    """
    Baho pasayganda o'quvchiga avtomatik ogohlantirish:
    ⚠️ ANTIGRAVITY OGOHLANTIRISH

    Sizning o‘quv natijangiz pasaymoqda.

    Oldingi o‘rtacha baho: 89
    Hozirgi o‘rtacha baho: 76

    Iltimos, keyingi darslarda natijangizni yaxshilashga harakat qiling.
    """
    if get_setting('notification_warning_enabled', 'true').lower() != 'true':
        return False, "Ogohlantirish bildirishnomasi sozlamalarda o'chirilgan."

    chat_id = student.get('telegram_chat_id')
    student_name = f"{student.get('first_name')} {student.get('last_name')}"

    prev_val = round(float(previous_avg), 1) if previous_avg else '—'
    curr_val = round(float(current_avg), 1) if current_avg else '—'

    msg = (
        "⚠️ <b>ANTIGRAVITY OGOHLANTIRISH</b>\n\n"
        "Sizning o‘quv natijangiz pasaymoqda.\n\n"
        f"<b>Oldingi o‘rtacha baho:</b> {prev_val}\n"
        f"<b>Hozirgi o‘rtacha baho:</b> {curr_val}\n"
        f"<b>Pasayish:</b> -{round(float(drop_amount), 1)} ball\n\n"
        "Iltimos, keyingi darslarda natijangizni yaxshilashga harakat qiling.\n\n"
        "<i>ANTIGRAVITY ta'lim markazi</i>"
    )

    if not chat_id:
        log_notification("student", student_name, "Yo'q", "warning", msg, "failed", "O'quvchining Telegram Chat ID raqami kiritilmagan.")
        return False, "Chat ID yo'q"

    success, status, err = send_telegram_raw(chat_id, msg)
    log_notification("student", student_name, chat_id, "warning", msg, status, err)
    return success, err or "Yuborildi"

def send_parent_warning_notification(student, previous_avg, current_avg, drop_amount):
    """
    Baho pasayganda ota-onaga avtomatik ogohlantirish:
    ⚠️ Muhim ogohlantirish

    Farzandingizning o‘quv natijalarida pasayish kuzatildi.

    Oldingi o‘rtacha: 91
    Hozirgi o‘rtacha: 78

    Iltimos, natijalarni nazorat qilib boring.
    """
    if get_setting('notification_parent_warning_enabled', 'true').lower() != 'true':
        return False, "Ota-onaga ogohlantirish bildirishnomasi sozlamalarda o'chirilgan."

    parent_chat_id = student.get('parent_telegram_chat_id')
    parent_name = student.get('parent_name') or f"{student.get('last_name')} ota-onasi"
    student_fullname = f"{student.get('first_name')} {student.get('last_name')}"

    prev_val = round(float(previous_avg), 1) if previous_avg else '—'
    curr_val = round(float(current_avg), 1) if current_avg else '—'

    msg = (
        "⚠️ <b>Muhim ogohlantirish</b>\n\n"
        "Farzandingizning o‘quv natijalarida pasayish kuzatildi.\n\n"
        f"<b>O‘quvchi:</b> {student_fullname}\n"
        f"<b>Oldingi o‘rtacha:</b> {prev_val}\n"
        f"<b>Hozirgi o‘rtacha:</b> {curr_val}\n"
        f"<b>Pasayish darajasi:</b> -{round(float(drop_amount), 1)} ball\n\n"
        "Iltimos, natijalarni nazorat qilib boring.\n\n"
        "<i>ANTIGRAVITY ta'lim markazi</i>"
    )

    if not parent_chat_id:
        log_notification("parent", f"{parent_name} ({student_fullname})", "Yo'q", "parent_warning", msg, "failed", "Ota-onaning Telegram Chat ID raqami kiritilmagan.")
        return False, "Ota-ona Chat ID yo'q"

    success, status, err = send_telegram_raw(parent_chat_id, msg)
    log_notification("parent", f"{parent_name} ({student_fullname})", parent_chat_id, "parent_warning", msg, status, err)
    return success, err or "Yuborildi"

def send_custom_test_notification(recipient_type, recipient_name, chat_id, custom_text):
    """Admin console test sender."""
    msg = f"🧪 <b>ANTIGRAVITY Test Xabari</b>\n\n{custom_text}\n\n<i>Sana va vaqt: Tizim tekshiruvi</i>"
    success, status, err = send_telegram_raw(chat_id, msg)
    log_notification(recipient_type, recipient_name, chat_id, "test", msg, status, err)
    return success, err or "Xabar muvaffaqiyatli yuborildi"

def send_chat_notification(recipient_name, chat_id, sender_name, message_snippet, chat_type='teacher'):
    """
    O'quvchi ustozga yoki ustoz o'quvchiga xabar yozganda Telegram orqali bildirishnoma.
    """
    if not chat_id:
        return False, "Chat ID yo'q"
    bot_name = get_bot_username()
    bot_url = get_bot_url()
    title = "💬 Yangi Ustoz-O'quvchi Xabari" if chat_type == 'teacher' else "👥 Yangi Guruh Xabari"
    msg = (
        f"<b>{title}</b>\n\n"
        f"Salom, <b>{recipient_name}</b>!\n"
        f"Sizga <b>{sender_name}</b> yangi xabar yozdi:\n\n"
        f"<i>«{message_snippet[:120]}»</i>\n\n"
        f"Platformaga kirib to'liq javob qaytarishingiz mumkin.\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>"
    )
    success, status, err = send_telegram_raw(chat_id, msg)
    log_notification("chat", recipient_name, chat_id, "chat_message", msg, status, err)
    return success, err or "Yuborildi"

def send_student_welcome_notification(student, course_title='', group_name=''):
    """
    O'quvchi tizimga qo'shilganda o'quvchi va ota-onaga Telegram orqali xush kelibsiz xabari yuborish.
    """
    chat_id = student.get('telegram_chat_id')
    student_name = f"{student.get('first_name')} {student.get('last_name')}"
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    msg = (
        "🎉 <b>ANTIGRAVITY TA'LIM MARKAZI</b>\n\n"
        f"Assalomu alaykum, <b>{student.get('first_name')} {student.get('last_name')}</b>!\n\n"
        "Siz ANTIGRAVITY platformasiga muvaffaqiyatli qo‘shildingiz!\n\n"
        f"<b>Kurs:</b> {course_title or 'Belgilanmoqda'}\n"
        f"<b>Guruh:</b> {group_name or 'Belgilanmoqda'}\n"
        f"<b>O‘quvchi ID:</b> #{student.get('id')}\n\n"
        "Endi sizning barcha baholaringiz, davomat va ustoz tavsiyalari ushbu bot orqali yetkaziladi.\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY — Kelajagingizni biz bilan quring!</i>"
    )

    if chat_id:
        success, status, err = send_telegram_raw(chat_id, msg)
        log_notification("student", student_name, chat_id, "welcome", msg, status, err)

    parent_chat_id = student.get('parent_telegram_chat_id')
    if parent_chat_id:
        parent_msg = (
            "🎉 <b>ANTIGRAVITY TA'LIM MARKAZI</b>\n\n"
            f"Assalomu alaykum, hurmatli ota-ona!\n\n"
            f"Farzandingiz <b>{student_name}</b> markazimiz o‘quvchilar safiga qabul qilindi.\n\n"
            f"<b>Kurs:</b> {course_title or 'Belgilanmoqda'}\n"
            f"<b>Guruh:</b> {group_name or 'Belgilanmoqda'}\n\n"
            "Farzandingizning baholari va davomatini ushbu bot orqali muntazam kuzatib borishingiz mumkin.\n\n"
            f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>"
        )
        success_p, status_p, err_p = send_telegram_raw(parent_chat_id, parent_msg)
        log_notification("parent", student_name + " (Ota-ona)", parent_chat_id, "welcome_parent", parent_msg, status_p, err_p)

def send_student_expulsion_notification(student, score, subject, assessment_date):
    """
    10 balldan past baho olganda o'quvchi va ota-onasiga shoshilinch chetlashtirish xabari:
    ❌ DIQQAT: CHETLASHTIRISH XABARI!
    """
    student_name = f"{student.get('first_name')} {student.get('last_name')}"
    chat_id = student.get('telegram_chat_id')
    parent_chat_id = student.get('parent_telegram_chat_id')
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    msg = (
        "❌ <b>DIQQAT: CHETLASHTIRISH XABARI!</b>\n\n"
        f"Hurmatli <b>{student_name}</b>!\n\n"
        f"Siz <b>{subject}</b> fanidan <b>{score} ball</b> (< 10 ball) to'plaganligingiz sababli markaz ichki tartib-qoidalariga muvofiq o'quvchilar safidan <b>chetlashtirildingiz</b> (holatingiz nofaol qilib belgilandi).\n\n"
        f"<b>Fan:</b> {subject}\n"
        f"<b>Olingan baho:</b> {score} ball (Minimal chegara: 10 ball)\n"
        f"<b>Sana:</b> {assessment_date}\n\n"
        "Qo'shimcha ma'lumot olish yoki qayta tiklash masalasida markaz ma'muriyatiga murojaat qilishingiz mumkin.\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY ma'muriyati</i>"
    )

    if chat_id:
        success, status, err = send_telegram_raw(chat_id, msg)
        log_notification("student", student_name, chat_id, "expulsion", msg, status, err)

    if parent_chat_id:
        parent_msg = (
            "❌ <b>DIQQAT: FARZANDINGIZ CHETLASHTIRILDI!</b>\n\n"
            f"Hurmatli ota-ona! Farzandingiz <b>{student_name}</b> <b>{subject}</b> darsidan <b>{score} ball</b> (< 10 ball) olgani sababli o'quvchilar safidan chetlashtirildi.\n\n"
            f"<b>Olingan baho:</b> {score} ball\n"
            f"<b>Sana:</b> {assessment_date}\n\n"
            "Iltimos, markaz ma'muriyati bilan bog'laning.\n\n"
            f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
            "<i>ANTIGRAVITY ma'muriyati</i>"
        )
        success_p, status_p, err_p = send_telegram_raw(parent_chat_id, parent_msg)
        log_notification("parent", student_name + " (Ota-ona)", parent_chat_id, "expulsion_parent", parent_msg, status_p, err_p)

def send_homework_notification(student, homework_title, subject, due_date, homework_id=None):
    """Yangi uyga vazifa berilganda o'quvchiga Telegram xabari"""
    chat_id = student.get('telegram_chat_id')
    if not chat_id:
        return False, "Chat ID yo'q"

    student_name = f"{student.get('first_name')} {student.get('last_name')}"
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    msg = (
        "📝 <b>YANGI UYGA VAZIFA!</b>\n\n"
        f"Salom, <b>{student.get('first_name')}</b>!\n"
        f"Guruhdoshlaringiz va siz uchun yangi topshiriq joylandi.\n\n"
        f"<b>Fan:</b> {subject}\n"
        f"<b>Mavzu:</b> {homework_title}\n"
        f"<b>Topshirish muddati:</b> {due_date}\n\n"
        "Shaxsiy kabinetingizga kirib topshiriqni o'z vaqtida topshiring!\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY ta'lim markazi</i>"
    )

    success, status, err = send_telegram_raw(chat_id, msg)
    log_notification("student", student_name, chat_id, "homework", msg, status, err)
    return success, err or "Yuborildi"

def send_homework_graded_notification(student, homework_title, score, feedback):
    """Uyga vazifa tekshirilganda o'quvchiga Telegram xabari"""
    chat_id = student.get('telegram_chat_id')
    if not chat_id:
        return False, "Chat ID yo'q"

    student_name = f"{student.get('first_name')} {student.get('last_name')}"
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    msg = (
        "✅ <b>UYGA VAZIFANGIZ TEKSHIRILDI!</b>\n\n"
        f"Salom, <b>{student.get('first_name')}</b>!\n"
        f"Ustozingiz siz topshirgan uy vazifasini tekshirdi va baholadi.\n\n"
        f"<b>Vazifa mavzusi:</b> {homework_title}\n"
        f"<b>Qo'yilgan baho:</b> <b>{score} ball</b>\n"
        f"<b>Ustoz fikri:</b> {feedback or 'Barakalla, vazifa qabul qilindi!'}\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY ta'lim markazi</i>"
    )

    success, status, err = send_telegram_raw(chat_id, msg)
    log_notification("student", student_name, chat_id, "homework_graded", msg, status, err)
    return success, err or "Yuborildi"

def send_admin_alert(subject, body):
    """Adminning Telegramiga platforma hodisalari haqida xabar yuborish"""
    admin_chat = get_setting('admin_telegram_chat_id', '')
    if not admin_chat:
        return False, "Admin chat ID sozlanmagan"

    bot_name = get_bot_username()
    bot_url = get_bot_url()
    msg = (
        f"🔔 <b>{subject}</b>\n\n"
        f"{body}\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY bildirishnoma tizimi</i>"
    )
    success, status, err = send_telegram_raw(admin_chat, msg)
    log_notification("admin", "Admin", admin_chat, "admin_alert", msg, status, err)
    return success, err or "Yuborildi"

def send_payment_reminder(student, amount_due, month_for, course_title=""):
    """To'lov haqida o'quvchi va ota-onaga Telegram eslatmasi"""
    student_name = f"{student.get('first_name')} {student.get('last_name')}"
    chat_id = student.get('telegram_chat_id')
    parent_chat_id = student.get('parent_telegram_chat_id')
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    formatted_amount = f"{float(amount_due):,.0f} so'm".replace(",", " ")

    msg = (
        "💳 <b>ANTIGRAVITY TO'LOV ESLATMASI</b>\n\n"
        f"Hurmatli <b>{student_name}</b>!\n\n"
        f"Sizning <b>{month_for}</b> oyi uchun <b>{course_title or 'kurs'}</b> to'lovingiz kutilmoqda.\n\n"
        f"💵 <b>To'lov miqdori:</b> {formatted_amount}\n"
        "💳 <b>To'lov usullari:</b> Payme, Click yoki filial kassasi orqali\n\n"
        "Iltimos, mashg'ulotlardan uzilib qolmaslik uchun to'lovni o'z vaqtida amalga oshiring.\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY moliya bo'limi</i>"
    )

    sent_any = False
    err_last = None
    if chat_id:
        s, status, err = send_telegram_raw(chat_id, msg)
        log_notification("student", student_name, chat_id, "payment_reminder", msg, status, err)
        if s: sent_any = True
        else: err_last = err

    if parent_chat_id:
        parent_msg = (
            "💳 <b>ANTIGRAVITY TO'LOV ESLATMASI</b>\n\n"
            f"Hurmatli ota-ona! Farzandingiz <b>{student_name}</b> ning <b>{month_for}</b> oyi uchun ta'lim to'lovi kutilmoqda.\n\n"
            f"💵 <b>To'lov miqdori:</b> {formatted_amount}\n"
            f"📚 <b>Kurs:</b> {course_title or 'O\'quv kursi'}\n\n"
            "Iltimos, to'lovni amalga oshirib markaz ma'muriyatiga chekni taqdim etishingizni so'raymiz.\n\n"
            f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
            "<i>ANTIGRAVITY moliya bo'limi</i>"
        )
        s, status, err = send_telegram_raw(parent_chat_id, parent_msg)
        log_notification("parent", student_name + " (Ota-ona)", parent_chat_id, "payment_reminder_parent", parent_msg, status, err)
        if s: sent_any = True
        else: err_last = err

    return sent_any, err_last or "Eslatma yuborildi"

def send_ai_diagnostics_report(student, diagnostic_summary, recommendations, risk_level):
    """AI tashxis xulosasini o'quvchi va ota-onaga yuborish"""
    student_name = f"{student.get('first_name')} {student.get('last_name')}"
    chat_id = student.get('telegram_chat_id')
    parent_chat_id = student.get('parent_telegram_chat_id')
    bot_name = get_bot_username()
    bot_url = get_bot_url()

    risk_badges = {
        'high': "🔴 YUQORI XAVF (Natijalar pasaygan)",
        'medium': "🟡 O'RTA XAVF (E'tibor zarur)",
        'low': "🟢 BARQAROR / A'LO"
    }
    risk_title = risk_badges.get(risk_level, "ℹ️ AI TAHLIL")

    msg = (
        f"🤖 <b>ANTIGRAVITY AI O'QUVCHI TASHXISI</b>\n\n"
        f"O'quvchi: <b>{student_name}</b>\n"
        f"Holat: <b>{risk_title}</b>\n\n"
        f"📊 <b>AI Tahlili:</b>\n{diagnostic_summary}\n\n"
        f"💡 <b>Tavsiyalar:</b>\n{recommendations}\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY Sun'iy Intellekt Tahlil Tizimi</i>"
    )

    sent_any = False
    err_last = None
    if chat_id:
        s, status, err = send_telegram_raw(chat_id, msg)
        log_notification("student", student_name, chat_id, "ai_diagnostics", msg, status, err)
        if s: sent_any = True
        else: err_last = err

    if parent_chat_id:
        s, status, err = send_telegram_raw(parent_chat_id, msg)
        log_notification("parent", student_name + " (Ota-ona)", parent_chat_id, "ai_diagnostics_parent", msg, status, err)
        if s: sent_any = True
        else: err_last = err

    return sent_any, err_last or "AI hisoboti yuborildi"


