import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), 'antigravity.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('superadmin', 'admin', 'teacher')),
        email TEXT,
        phone TEXT,
        teacher_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE SET NULL
    )
    ''')

    # 2. Courses table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        description TEXT NOT NULL,
        level TEXT NOT NULL,
        duration TEXT NOT NULL,
        price TEXT NOT NULL,
        icon TEXT DEFAULT 'book',
        color TEXT DEFAULT 'blue',
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 3. Teachers table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teachers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        subject TEXT NOT NULL,
        experience_years INTEGER NOT NULL,
        bio TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        photo_url TEXT,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 4. Groups table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        course_id INTEGER NOT NULL,
        teacher_id INTEGER NOT NULL,
        room TEXT,
        schedule TEXT,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE RESTRICT
    )
    ''')

    # 5. Students table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        birth_date TEXT,
        course_id INTEGER,
        group_id INTEGER,
        teacher_id INTEGER,
        telegram_chat_id TEXT,
        parent_name TEXT,
        parent_phone TEXT,
        parent_telegram_chat_id TEXT,
        status TEXT DEFAULT 'active' CHECK(status IN ('active', 'graduated', 'inactive')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE SET NULL
    )
    ''')

    # 6. Grades table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS grades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        assessment_date TEXT NOT NULL,
        assessment_type TEXT NOT NULL,
        score REAL NOT NULL,
        comment TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
    )
    ''')

    # 7. Attendance table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        group_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('present', 'absent', 'late', 'excused')),
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        UNIQUE(student_id, group_id, date)
    )
    ''')

    # 8. Warnings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        warning_type TEXT NOT NULL,
        previous_avg REAL,
        current_avg REAL,
        drop_amount REAL,
        subjects TEXT,
        trigger_reason TEXT NOT NULL,
        resolved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')

    # 9. Notification logs
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS notification_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient_type TEXT NOT NULL,
        recipient_name TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        message_type TEXT NOT NULL,
        message_body TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('sent', 'failed', 'simulated')),
        error_message TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 10. Settings table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    ''')

    # 11. Leads table (contact and course requests from public site)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        course_name TEXT,
        message TEXT,
        status TEXT DEFAULT 'new' CHECK(status IN ('new', 'contacted', 'enrolled', 'cancelled')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 12. Teacher Messages (Student to Teacher Direct Chat)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS teacher_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        teacher_id INTEGER NOT NULL,
        sender_type TEXT NOT NULL CHECK(sender_type IN ('student', 'teacher')),
        sender_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
    )
    ''')

    # 13. Group Messages (Classmates Group Chat)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS group_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        sender_type TEXT NOT NULL CHECK(sender_type IN ('student', 'teacher', 'admin')),
        sender_id INTEGER NOT NULL,
        sender_name TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
    )
    ''')

    # 14. Homework table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS homework (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        course_id INTEGER,
        group_id INTEGER NOT NULL,
        teacher_id INTEGER,
        due_date TEXT NOT NULL,
        max_score REAL DEFAULT 100,
        file_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL,
        FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE SET NULL
    )
    ''')

    # 15. Homework Submissions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS homework_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        homework_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        submission_text TEXT,
        file_url TEXT,
        status TEXT DEFAULT 'submitted' CHECK(status IN ('submitted', 'graded', 'resubmit')),
        score REAL,
        feedback TEXT,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        graded_at TIMESTAMP,
        FOREIGN KEY (homework_id) REFERENCES homework(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        UNIQUE(homework_id, student_id)
    )
    ''')

    # 16. Payments table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payment_date TEXT NOT NULL,
        payment_method TEXT DEFAULT 'cash' CHECK(payment_method IN ('cash', 'card', 'click', 'payme', 'bank_transfer')),
        month_for TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')

    # 17. Rewards table (Coins Shop)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS rewards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        cost_coins INTEGER NOT NULL,
        icon TEXT DEFAULT 'gift',
        category TEXT DEFAULT 'merch',
        stock INTEGER DEFAULT 10,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 18. Reward Orders
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reward_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reward_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'delivered', 'cancelled')),
        ordered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        delivered_at TIMESTAMP,
        FOREIGN KEY (reward_id) REFERENCES rewards(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')

    # 19. Coins Transactions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS coins_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        reason TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')

    # 20. Quizzes
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS quizzes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        course_id INTEGER,
        time_limit_minutes INTEGER DEFAULT 15,
        passing_score INTEGER DEFAULT 70,
        description TEXT,
        active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
    )
    ''')

    # 21. Quiz Questions
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        question_text TEXT NOT NULL,
        option_a TEXT NOT NULL,
        option_b TEXT NOT NULL,
        option_c TEXT NOT NULL,
        option_d TEXT NOT NULL,
        correct_option TEXT NOT NULL CHECK(correct_option IN ('A', 'B', 'C', 'D')),
        points INTEGER DEFAULT 10,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
    )
    ''')

    # 22. Quiz Attempts
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quiz_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        score REAL NOT NULL,
        max_score REAL NOT NULL,
        passed INTEGER DEFAULT 0,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')

    # 23. Tournaments & Olympiads
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tournaments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        course_id INTEGER,
        description TEXT NOT NULL,
        prize_pool TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        max_participants INTEGER DEFAULT 50,
        status TEXT DEFAULT 'upcoming' CHECK(status IN ('upcoming', 'active', 'finished')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
    )
    ''')

    # 24. Tournament Participants
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tournament_participants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tournament_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        score REAL DEFAULT 0,
        rank INTEGER,
        prize_claimed INTEGER DEFAULT 0,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        UNIQUE(tournament_id, student_id)
    )
    ''')

    # 25. Call Logs (Virtual Call Center CRM)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS call_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id INTEGER,
        student_name TEXT NOT NULL,
        phone TEXT NOT NULL,
        call_type TEXT DEFAULT 'outgoing' CHECK(call_type IN ('incoming', 'outgoing')),
        status TEXT NOT NULL CHECK(status IN ('answered', 'no_answer', 'interested', 'trial_booked', 'rejected', 'enrolled')),
        duration_seconds INTEGER DEFAULT 60,
        notes TEXT,
        callback_date TEXT,
        created_by TEXT DEFAULT 'Admin',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 26. Competency Scores (360 Radar Matrix)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS competency_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        theory INTEGER DEFAULT 80,
        practice INTEGER DEFAULT 85,
        discipline INTEGER DEFAULT 90,
        speed INTEGER DEFAULT 75,
        teamwork INTEGER DEFAULT 85,
        mentor_notes TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        UNIQUE(student_id)
    )
    ''')

    # 27. Educational Contracts
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS contracts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contract_number TEXT UNIQUE NOT NULL,
        student_id INTEGER NOT NULL,
        parent_name TEXT NOT NULL,
        parent_phone TEXT,
        passport_series TEXT NOT NULL,
        address TEXT NOT NULL,
        monthly_amount REAL NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        status TEXT DEFAULT 'active' CHECK(status IN ('draft', 'signed', 'active', 'archived')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')

    # 28. Campus Room Bookings
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS room_bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room_name TEXT NOT NULL,
        title TEXT NOT NULL,
        booked_by TEXT NOT NULL,
        date TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 29. Official Certificates & Diplomas
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS certificates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        certificate_number TEXT UNIQUE NOT NULL,
        student_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        issue_date TEXT NOT NULL,
        grade_level TEXT DEFAULT 'A''lo darajali (With Distinction)',
        qr_code TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
    )
    ''')

    # 30. Academy Library Books
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS library_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        category TEXT NOT NULL,
        total_copies INTEGER DEFAULT 5,
        available_copies INTEGER DEFAULT 5,
        cover_icon TEXT DEFAULT 'book',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 31. Book Loans
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS book_loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        borrow_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        return_date TEXT,
        status TEXT DEFAULT 'borrowed',
        notes TEXT,
        FOREIGN KEY (book_id) REFERENCES library_books(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')

    # 32. Teacher Payroll Records
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payroll_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL,
        month_year TEXT NOT NULL,
        base_salary REAL NOT NULL,
        student_bonus REAL DEFAULT 0,
        kpi_bonus REAL DEFAULT 0,
        total_amount REAL NOT NULL,
        status TEXT DEFAULT 'pending',
        paid_at TIMESTAMP,
        notes TEXT,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
    )
    ''')

    conn.commit()
    conn.close()

def ensure_supplemental_seeds(cursor):
    today = datetime.now()
    # 1. Update telegram bot settings to @kino05_promaks_bot
    bot_settings = [
        ('center_name', 'Azizning 1-chi loyihasi'),
        ('telegram_bot_name', '@kino05_promaks_bot'),
        ('telegram_bot_url', 'https://t.me/kino05_promaks_bot'),
        ('telegram_bot_token', '8968202615:AAHxeDb7uh6wWwHzukpfg0nlve2SEEKyAkU')
    ]
    for k, v in bot_settings:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))
    cursor.execute("UPDATE settings SET value = '@kino05_promaks_bot' WHERE key = 'center_telegram' AND (value = '@antigravity_edu' OR value = '')")

    # 2. Seed Sample Teacher Messages if empty
    cursor.execute("SELECT COUNT(*) FROM teacher_messages")
    if cursor.fetchone()[0] == 0:
        sample_tm = [
            (1, 2, 'student', 1, "Assalomu alaykum, Dilshod aka! Bugungi geometriya masalasidagi 5-savol bo'yicha tushunmagan joyim bor edi.", 1, (today - timedelta(days=2)).strftime('%Y-%m-%d 15:30:00')),
            (1, 2, 'teacher', 2, "Va alaykum assalom, Aziz! Pifagor teoremasi bo'yicha gipotenuzani topib, keyin balandlik formulasini qo'llaysan. Ertaga dars boshlanishidan 10 daqiqa oldin kelsang, batafsil tushuntirib beraman.", 1, (today - timedelta(days=2)).strftime('%Y-%m-%d 15:45:00')),
            (1, 2, 'student', 1, "Katta rahmat, ustoz! Ertaga albatta vaqtliroq boraman.", 0, (today - timedelta(days=2)).strftime('%Y-%m-%d 16:00:00')),
            (4, 4, 'student', 4, "Ustoz, Python bot bo'yicha webhook ulashda xatolik beryapti, tekshirib bera olasizmi?", 0, (today - timedelta(days=1)).strftime('%Y-%m-%d 18:20:00'))
        ]
        cursor.executemany('''
        INSERT INTO teacher_messages (student_id, teacher_id, sender_type, sender_id, message, is_read, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_tm)

    # 3. Seed Sample Group Messages if empty
    cursor.execute("SELECT COUNT(*) FROM group_messages")
    if cursor.fetchone()[0] == 0:
        sample_gm = [
            (2, 'student', 1, 'Aziz Karimov', "Salom guruhdoshlar! Ertangi matematika testiga kim tayyor?", (today - timedelta(days=1)).strftime('%Y-%m-%d 12:00:00')),
            (2, 'student', 7, 'Nigora Xoliqova', "Salom Aziz! Men 12-mavzuni takrorlayapman, formulalarni yodlab oldim.", (today - timedelta(days=1)).strftime('%Y-%m-%d 12:05:00')),
            (2, 'teacher', 2, 'Dilshod Karimov (Ustoz)', "Hammamizga omad! Ertaga testda ayniqsa kvadrat tenglamalar va kasrli ifodalarga diqqat qilinglar.", (today - timedelta(days=1)).strftime('%Y-%m-%d 12:15:00')),
            (4, 'student', 4, 'Shahzod Tursunov', "Telegram bot bo'yicha uy vazifasini kim tugatdi?", (today - timedelta(days=1)).strftime('%Y-%m-%d 14:00:00')),
            (4, 'student', 6, 'Sardor Normatov', "Men inline buttonlarni tugatdim, judayam zo'r chiqdi!", (today - timedelta(days=1)).strftime('%Y-%m-%d 14:10:00'))
        ]
        cursor.executemany('''
        INSERT INTO group_messages (group_id, sender_type, sender_id, sender_name, message, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', sample_gm)

    # 4. Seed Rewards if empty
    cursor.execute("SELECT COUNT(*) FROM rewards")
    if cursor.fetchone()[0] == 0:
        rewards = [
            ("ANTIGRAVITY Futbolka (Brand T-shirt)", "Yuqori sifatli 100% paxta Antigravity logotipli futbolka (barcha o'lchamlar mavjud)", 300, "shirt", "merch", 20, 1),
            ("Brendli Termos / Krujka", "Issiq va sovuqni uzoq saqlaydigan qulay zanglamas metall termos", 200, "coffee", "merch", 25, 1),
            ("Bepul 1 haftalik Speaking Club", "Xorijlik ustoz bilan individual yoki mini-guruhda qo'shimcha dars", 150, "mic", "course", 50, 1),
            ("IT Pro Kursi uchun 20% Chegirma", "Keyingi oylik to'lov uchun 20% chegirma taqdim etuvchi vaucher", 250, "percent", "discount", 30, 1),
            ("Stikerlar to'plami (Coder & Math Pack)", "Noutbuk va daftarlar uchun maxsus vinil stikerlar to'plami", 50, "tag", "merch", 100, 1),
            ("Katta Noutbuk Ryukzaki", "Suv o'tkazmaydigan qulay va zamonaviy darslik ryukzaki", 500, "briefcase", "merch", 10, 1)
        ]
        cursor.executemany('''
        INSERT INTO rewards (title, description, cost_coins, icon, category, stock, active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', rewards)

    # 5. Seed Quizzes & Questions if empty
    cursor.execute("SELECT COUNT(*) FROM quizzes")
    if cursor.fetchone()[0] == 0:
        quizzes = [
            (1, "Matematika: Mantiqiy va Algebraik Blitz Test", 2, 15, 70, "Mantiqiy fikrlash, kasrlar va tenglamalar bo'yicha 5 ta tezkor savol", 1),
            (2, "IT & Python: Boshlang'ich Dasturlash Viktorinasi", 5, 10, 70, "O'zgaruvchilar, sikllar, funksiyalar va algoritmlar asoslari", 1),
            (3, "English Grammar & Vocabulary Challenge", 1, 15, 75, "Tenses, prepositions, phrasal verbs va so'z boyligi tekshiruvi", 1)
        ]
        cursor.executemany('''
        INSERT INTO quizzes (id, title, course_id, time_limit_minutes, passing_score, description, active)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', quizzes)

        questions = [
            # Quiz 1: Math
            (1, "Agar 5 ta ishchi 5 kunda 5 ta stol yasasa, 100 ta ishchi 100 ta stolni necha kunda yasaydi?", "100 kunda", "5 kunda", "20 kunda", "50 kunda", "B", 20),
            (1, "2x + 10 = 30 tenglamada x nimaga teng?", "5", "10", "15", "20", "B", 20),
            (1, "Uchburchakning barcha ichki burchaklari yig'indisi necha gradusga teng?", "90°", "180°", "360°", "270°", "B", 20),
            (1, "1, 4, 9, 16, 25, ... ketma-ketlikdagi keyingi son qaysi?", "36", "30", "49", "32", "A", 20),
            (1, "To'g'ri to'rtburchakning bo'yi 8 sm, eni 5 sm. Uning yuzi necha sm²?", "26 sm²", "40 sm²", "13 sm²", "35 sm²", "B", 20),
            
            # Quiz 2: IT Python
            (2, "Python dasturlash tilida ekranga ma'lumot chiqarish uchun qaysi funksiya ishlatiladi?", "echo()", "print()", "console.log()", "write()", "B", 25),
            (2, "Python tilida o'zgarmas ro'yxat (immutable list) nima deb ataladi?", "list", "tuple", "dict", "set", "B", 25),
            (2, "len('Antigravity') funksiyasi qanday natija qaytaradi?", "10", "11", "12", "9", "B", 25),
            (2, "Qaysi kalit so'z yordamida Python dasturlash tilida yangi funksiya e'lon qilinadi?", "func", "function", "def", "lambda", "C", 25),

            # Quiz 3: English
            (3, "Choose the correct form: She _____ to school every day.", "go", "goes", "going", "went", "B", 25),
            (3, "Which word is an antonym (opposite) of 'Generous'?", "Kind", "Mean / Stingy", "Polite", "Brave", "B", 25),
            (3, "He has lived in Tashkent _____ 2018.", "for", "since", "during", "at", "B", 25),
            (3, "I look forward to _____ you next week.", "see", "seeing", "saw", "seen", "B", 25)
        ]
        cursor.executemany('''
        INSERT INTO quiz_questions (quiz_id, question_text, option_a, option_b, option_c, option_d, correct_option, points)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', questions)

    # 6. Seed Sample Initial Coins for students if empty
    cursor.execute("SELECT COUNT(*) FROM coins_transactions")
    if cursor.fetchone()[0] == 0:
        cursor.execute("SELECT id FROM students LIMIT 20")
        sample_sids = [r[0] for r in cursor.fetchall()]
        sample_coins = []
        for sid in sample_sids:
            sample_coins.append((sid, 150, "Boshlang'ich a'lo o'qish uchun bonus"))
            sample_coins.append((sid, 50, "Darslardagi 100% davomat bonusi"))
        if sample_coins:
            cursor.executemany('''
            INSERT INTO coins_transactions (student_id, amount, reason)
            VALUES (?, ?, ?)
            ''', sample_coins)

    # 7. Seed Sample Payments if empty
    cursor.execute("SELECT COUNT(*) FROM payments")
    if cursor.fetchone()[0] == 0:
        cursor.execute("SELECT id, course_id FROM students LIMIT 15")
        rows = cursor.fetchall()
        sample_pmts = []
        current_month = today.strftime('%Y-%m')
        for sid, cid in rows:
            sample_pmts.append((sid, 650000.0, (today - timedelta(days=5)).strftime('%Y-%m-%d'), 'click', current_month, "Oylik to'lov to'liq to'landi"))
        if sample_pmts:
            cursor.executemany('''
            INSERT INTO payments (student_id, amount, payment_date, payment_method, month_for, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', sample_pmts)

    # 8. Seed Tournaments if empty
    cursor.execute("SELECT COUNT(*) FROM tournaments")
    if cursor.fetchone()[0] == 0:
        sample_tournaments = [
            ("Matematika Respublika Olimpiadasiga Saralash 2026", 2, "Markazning eng iqtidorli matematiklarini aniqlash va nufuzli sovrinlar taqdim etish musobaqasi.", "1 500 000 so'm + 500 Coins", (today - timedelta(days=2)).strftime('%Y-%m-%d'), (today + timedelta(days=5)).strftime('%Y-%m-%d'), 50, 'active'),
            ("Python Hackathon & Bot Creator Cup", 5, "Amaliy dasturlash va Telegram bot loyihalari bo'yicha yosh dasturchilar chempionati.", "2 000 000 so'm + Brand Ryukzak", (today + timedelta(days=7)).strftime('%Y-%m-%d'), (today + timedelta(days=10)).strftime('%Y-%m-%d'), 30, 'upcoming'),
            ("IELTS Speaking & Vocabulary Grand Prix", 3, "Speaking band 8.0+ darajasi uchun intensiv bahs-munozara va leksika turniri.", "Speaking Club Yillik Abonementi", (today - timedelta(days=14)).strftime('%Y-%m-%d'), (today - timedelta(days=7)).strftime('%Y-%m-%d'), 40, 'finished')
        ]
        cursor.executemany('''
        INSERT INTO tournaments (title, course_id, description, prize_pool, start_date, end_date, max_participants, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_tournaments)

        # Participants for Tournament 1 (active)
        parts = [
            (1, 1, 95.0, 1, 0),
            (1, 7, 92.5, 2, 0),
            (1, 10, 88.0, 3, 0),
            (1, 2, 79.0, 4, 0),
            (1, 3, 76.0, 5, 0)
        ]
        cursor.executemany('''
        INSERT INTO tournament_participants (tournament_id, student_id, score, rank, prize_claimed)
        VALUES (?, ?, ?, ?, ?)
        ''', parts)

    # 9. Seed Call Logs if empty
    cursor.execute("SELECT COUNT(*) FROM call_logs")
    if cursor.fetchone()[0] == 0:
        sample_calls = [
            (1, "Botir Qosimov", "+998 90 777 12 34", "incoming", "trial_booked", 180, "IELTS kursiga qiziqdi, Shanba 14:00 da bepul sinov darsiga yozildi.", (today + timedelta(days=1)).strftime('%Y-%m-%d 14:00:00'), "Nodira (Menejer)"),
            (2, "Gulbahor Karimova", "+998 93 456 78 90", "outgoing", "interested", 120, "O'g'li Python dasturlashga qiziqadi. Narxlar ma'lumotnomasi Telegramdan yuborildi.", (today + timedelta(days=2)).strftime('%Y-%m-%d 11:00:00'), "Nodira (Menejer)"),
            (3, "Shohrux Mirzayev", "+998 94 123 99 88", "incoming", "enrolled", 240, "Matematika guruhiga to'liq ro'yxatdan o'tdi, shartnoma imzolandi.", None, "Admin"),
            (None, "Anvar Narzullayev", "+998 97 333 44 55", "outgoing", "no_answer", 25, "Go'shakni ko'tarmadi, 2 soatdan keyin qayta qo'ng'iroq qilish kerak.", (today + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S'), "Admin")
        ]
        cursor.executemany('''
        INSERT INTO call_logs (lead_id, student_name, phone, call_type, status, duration_seconds, notes, callback_date, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_calls)

    # 10. Seed Competency Scores if empty
    cursor.execute("SELECT COUNT(*) FROM competency_scores")
    if cursor.fetchone()[0] == 0:
        competency_data = [
            (1, 92, 88, 95, 84, 90, "Nazariy va mantiqiy tafakkur kuchli. Doimiy darsga tayyor keladi."),
            (2, 65, 70, 75, 68, 80, "Amaliyotga ko'proq e'tibor berish lozim. Lug'at boyligini oshirish tavsiya etiladi."),
            (3, 95, 94, 98, 92, 88, "IELTS bo'yicha namunali o'quvchi. Listening va Speaking darajasi juda yuqori."),
            (4, 88, 96, 90, 92, 85, "Python va amaliy loyihalarda lider. Mustaqil botlar yoza oladi."),
            (7, 96, 94, 95, 98, 92, "Matematika bo'yicha olimpiadachi. Nostandart masalalarni tez yechadi.")
        ]
        cursor.executemany('''
        INSERT INTO competency_scores (student_id, theory, practice, discipline, speed, teamwork, mentor_notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', competency_data)

    # 11. Seed Educational Contracts if empty
    cursor.execute("SELECT COUNT(*) FROM contracts")
    if cursor.fetchone()[0] == 0:
        contracts_data = [
            ("SH-2026/0101", 1, "Farhod Karimov", "+998 90 999 88 77", "AA 1234567", "Toshkent sh., Yunusobod 4-mavze, 12-uy", 650000.0, "2026-09-01", "2027-06-30", "active"),
            ("SH-2026/0102", 2, "Gulnora Saidova", "+998 93 888 77 66", "AB 2345678", "Toshkent sh., Chilonzor 9-kvartal, 45-uy", 650000.0, "2026-09-01", "2027-06-30", "active"),
            ("SH-2026/0103", 3, "Akmal Eshmatov", "+998 94 777 66 55", "AC 3456789", "Toshkent sh., Mirzo Ulug'bek tumani, 18-uy", 850000.0, "2026-09-01", "2027-03-31", "signed"),
            ("SH-2026/0104", 4, "Olim Tursunov", "+998 97 666 55 44", "AD 4567890", "Toshkent sh., Shayxontohur tumani, 5-uy", 900000.0, "2026-09-01", "2027-05-31", "active")
        ]
        cursor.executemany('''
        INSERT INTO contracts (contract_number, student_id, parent_name, parent_phone, passport_series, address, monthly_amount, start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', contracts_data)

    # 12. Seed Campus Room Bookings if empty
    cursor.execute("SELECT COUNT(*) FROM room_bookings")
    if cursor.fetchone()[0] == 0:
        sample_bookings = [
            ("Lab 301", "AI Bot Hackathon Mini-sessiya", "Javohir Toshpulatov", today.strftime('%Y-%m-%d'), "14:00", "16:00", "20 ta iMac va proyektor zarur"),
            ("Xona 201", "Speaking Club (Mock Interview)", "Sanjar Alimov", today.strftime('%Y-%m-%d'), "16:30", "18:00", "Dumaloq stol formati"),
            ("Konferents-Zal", "Ota-onalar bilan oylik uchrashuv", "Direktor", (today + timedelta(days=2)).strftime('%Y-%m-%d'), "11:00", "13:00", "Mikrofon va audio tizim sozlanadi")
        ]
        cursor.executemany('''
        INSERT INTO room_bookings (room_name, title, booked_by, date, start_time, end_time, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_bookings)

    # 13. Ensure contracts table has cancellation columns
    try:
        cursor.execute("ALTER TABLE contracts ADD COLUMN termination_reason TEXT")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE contracts ADD COLUMN terminated_at TEXT")
    except Exception:
        pass

    # 14. Ensure certificates table exists and seed if empty
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS certificates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        certificate_number TEXT UNIQUE NOT NULL,
        student_id INTEGER NOT NULL,
        course_id INTEGER NOT NULL,
        issue_date TEXT NOT NULL,
        grade_level TEXT DEFAULT 'A''lo darajali (With Distinction)',
        qr_code TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
    )
    ''')
    cursor.execute("SELECT COUNT(*) FROM certificates")
    if cursor.fetchone()[0] == 0:
        sample_certs = [
            ("CRT-2026/001", 1, 2, "2026-09-20", "A'lo darajali (With Distinction)", "CRT-2026/001-AZIZ-MATH", "Olimpiada bosqichini a'lo natijalar bilan tamomladi"),
            ("CRT-2026/002", 3, 3, "2026-09-25", "A'lo darajali (Band 8.0)", "CRT-2026/002-JASUR-IELTS", "IELTS Intensive kursini muvaffaqiyatli yakunladi"),
            ("CRT-2026/003", 4, 5, "2026-09-28", "Yaxshi (Merit)", "CRT-2026/003-SHAHZOD-PYTHON", "Fullstack Python dasturlash loyihasini himoya qildi")
        ]
        cursor.executemany('''
        INSERT INTO certificates (certificate_number, student_id, course_id, issue_date, grade_level, qr_code, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_certs)

    # 15. Ensure library_books table exists and seed if empty
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS library_books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        author TEXT NOT NULL,
        category TEXT NOT NULL,
        total_copies INTEGER DEFAULT 5,
        available_copies INTEGER DEFAULT 5,
        cover_icon TEXT DEFAULT 'book',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cursor.execute("SELECT COUNT(*) FROM library_books")
    if cursor.fetchone()[0] == 0:
        sample_books = [
            ("Clean Code: Dasturiy ta'minot san'ati", "Robert C. Martin", "Dasturlash", 6, 4, "laptop-code"),
            ("Grokking Algorithms: Illyustratsiyali qo'llanma", "Aditya Bhargava", "Algoritmlar", 8, 5, "brain"),
            ("Python Crash Course: Amaliy kirish", "Eric Matthes", "Python & Backend", 10, 7, "code"),
            ("Cambridge IELTS 18 Academic with Answers", "Cambridge University", "Ingliz tili", 12, 9, "language"),
            ("Designing Data-Intensive Applications", "Martin Kleppmann", "Ma'lumotlar bazasi", 5, 3, "database"),
            ("Eloquent JavaScript: Zamonaviy veb qo'llanma", "Marijn Haverbeke", "Frontend", 7, 5, "globe")
        ]
        cursor.executemany('''
        INSERT INTO library_books (title, author, category, total_copies, available_copies, cover_icon)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', sample_books)

    # 16. Ensure book_loans table exists and seed if empty
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS book_loans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        borrow_date TEXT NOT NULL,
        due_date TEXT NOT NULL,
        return_date TEXT,
        status TEXT DEFAULT 'borrowed',
        notes TEXT,
        FOREIGN KEY (book_id) REFERENCES library_books(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
    )
    ''')
    cursor.execute("SELECT COUNT(*) FROM book_loans")
    if cursor.fetchone()[0] == 0:
        sample_loans = [
            (1, 1, '2026-09-15', '2026-09-29', None, 'overdue', 'Kechiktirilmoqda, 1 kundan oshdi'),
            (2, 2, '2026-09-20', '2026-10-04', None, 'borrowed', 'Algoritmlar olimpiadasiga tayyorgarlik'),
            (3, 4, '2026-09-18', '2026-10-02', None, 'borrowed', 'Django loyihasi uchun olingan'),
            (4, 3, '2026-09-10', '2026-09-24', '2026-09-23', 'returned', 'Vaqtida qaytarildi')
        ]
        cursor.executemany('''
        INSERT INTO book_loans (book_id, student_id, borrow_date, due_date, return_date, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', sample_loans)

    # 17. Ensure payroll_records table exists and seed if empty
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS payroll_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL,
        month_year TEXT NOT NULL,
        base_salary REAL NOT NULL,
        student_bonus REAL DEFAULT 0,
        kpi_bonus REAL DEFAULT 0,
        total_amount REAL NOT NULL,
        status TEXT DEFAULT 'pending',
        paid_at TIMESTAMP,
        notes TEXT,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
    )
    ''')
    cursor.execute("SELECT COUNT(*) FROM payroll_records")
    if cursor.fetchone()[0] == 0:
        sample_payrolls = [
            (1, '2026-09', 4500000.0, 1800000.0, 500000.0, 6800000.0, 'paid', '2026-09-25 11:30:00', 'IELTS guruhi yuqori natijasi bonusi bilan'),
            (2, '2026-09', 5000000.0, 2200000.0, 700000.0, 7900000.0, 'paid', '2026-09-25 11:35:00', 'Matematika olimpiadachilar tayyorlagani uchun'),
            (3, '2026-09', 4000000.0, 1400000.0, 300000.0, 5700000.0, 'pending', None, 'Sentyabr oylik maoshi hisob-kitobi'),
            (4, '2026-09', 5500000.0, 2600000.0, 900000.0, 9000000.0, 'paid', '2026-09-25 11:40:00', 'Python Bootcamp yuqori qamrovi bonusi'),
            (5, '2026-09', 4200000.0, 1200000.0, 400000.0, 5800000.0, 'pending', None, 'STEM va Robototexnika oylik maoshi'),
            (6, '2026-09', 4800000.0, 1900000.0, 600000.0, 7300000.0, 'pending', None, 'Abituriyentlar guruhi tayyorlovi')
        ]
        cursor.executemany('''
        INSERT INTO payroll_records (teacher_id, month_year, base_salary, student_bonus, kpi_bonus, total_amount, status, paid_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_payrolls)


def seed_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if already seeded
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] > 0:
        ensure_supplemental_seeds(cursor)
        conn.commit()
        conn.close()
        return

    # Seed Default Settings
    default_settings = [
        ('notification_grade_enabled', 'true'),
        ('notification_parent_grade_enabled', 'true'),
        ('notification_warning_enabled', 'true'),
        ('notification_parent_warning_enabled', 'true'),
        ('warning_threshold', '70'),
        ('warning_drop_percent', '10'),
        ('warning_consecutive_drops', '3'),
        ('telegram_bot_token', ''),
        ('telegram_bot_name', '@kino05_promaks_bot'),
        ('telegram_bot_url', 'https://t.me/kino05_promaks_bot'),
        ('center_name', 'ANTIGRAVITY Ta\'lim Markazi'),
        ('center_phone', '+998 71 200 45 45'),
        ('center_telegram', '@kino05_promaks_bot'),
        ('center_instagram', '@antigravity.uz'),
        ('center_address', 'Toshkent sh., Yunusobod tumani, Amir Temur shoh ko\'chasi, 107A'),
        ('center_work_hours', 'Dushanba - Shanba: 08:00 - 20:00, Yakshanba: 09:00 - 18:00')
    ]
    cursor.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", default_settings)

    # Seed Courses
    courses = [
        ('Ingliz tili', 'ingliz-tili', 'Boshlang\'ichdan yuqori darajagacha xalqaro metodika bo\'yicha o\'qitish. So\'zlashuv, grammatika va tinglash amaliyoti.', 'Beginner - Advanced', '6 oy', '650,000 so\'m / oy', 'language', 'blue', 1),
        ('Matematika', 'matematika', 'Maktab dasturi, akademik litsey va oliy o\'quv yurtlariga mukammal tayyorlov. Mantiqiy fikrlashni rivojlantirish.', 'Barcha darajalar', '9 oy', '600,000 so\'m / oy', 'calculator', 'emerald', 1),
        ('IELTS', 'ielts', 'IELTS 7.0+ kafolatlangan intensiv tayyorlov kursi. Har haftalik Mock imtihonlar va individual tahlil.', 'Intermediate+', '3 - 5 oy', '850,000 so\'m / oy', 'award', 'indigo', 1),
        ('CEFR', 'cefr', 'Milliy va xalqaro CEFR B2/C1 darajalariga tayyorlash. Imtiyozli sertifikat egalari bo\'lish imkoniyati.', 'B1 - C1', '4 oy', '700,000 so\'m / oy', 'badge-check', 'amber', 1),
        ('IT / Dasturlash', 'it-dasturlash', 'Zamonaviy Web dasturlash (Python, JavaScript, Django, React), real amaliy loyihalar va portfolio yaratish.', 'Junior dasturchi', '8 oy', '900,000 so\'m / oy', 'code', 'violet', 1),
        ('Robototexnika', 'robototexnika', 'Arduino, elektronika asoslari va avtomatlashtirilgan tizimlarni yaratish bo\'yicha amaliy mashg\'ulotlar.', 'Boshlang\'ich - O\'rta', '5 oy', '750,000 so\'m / oy', 'cpu', 'cyan', 1)
    ]
    cursor.executemany('''
    INSERT INTO courses (title, slug, description, level, duration, price, icon, color, active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', courses)

    # Seed Teachers
    teachers = [
        ('Sanjar Alimov', 'IELTS & Ingliz tili', 7, 'IELTS 8.5 sohibi, Buyuk Britaniya London universiteti bitiruvchisi. 500+ o\'quvchisi 7.0+ natijaga erishgan.', '+998 90 123 45 67', 'sanjar@antigravity.uz', 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400&auto=format&fit=crop&q=80', 1),
        ('Dilshod Karimov', 'Oliy Matematika', 9, 'Matematika fanlari nomzodi, Respublika olimpiadalari g\'oliblarini tayyorlagan oliy toifali pedagog.', '+998 91 234 56 78', 'dilshod@antigravity.uz', 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400&auto=format&fit=crop&q=80', 1),
        ('Madina Rustamova', 'CEFR & General English', 6, 'CEFR C1 darajasi, Cambridge CELTA sertifikati sohibasi. Zamonaviy kommunikativ metodika bo\'yicha mutaxassis.', '+998 93 345 67 89', 'madina@antigravity.uz', 'https://images.unsplash.com/photo-1573496359142-b8d87734a5a2?w=400&auto=format&fit=crop&q=80', 1),
        ('Javohir Toshpulatov', 'Fullstack Dasturlash (IT)', 5, 'Senior Python/Django dasturchi, 10+ tijoriy xalqaro loyihalar muallifi va mentor.', '+998 94 456 78 90', 'javohir@antigravity.uz', 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=400&auto=format&fit=crop&q=80', 1),
        ('Shahnoza Ismoilova', 'Robototexnika & STEM', 4, 'Toshkent Axborot Texnologiyalari Universiteti magistri, yosh ixtirochilar tanlovlari hakami.', '+998 97 567 89 01', 'shahnoza@antigravity.uz', 'https://images.unsplash.com/photo-1580489944761-15a19d654956?w=400&auto=format&fit=crop&q=80', 1),
        ('Bobur Mahmudov', 'Matematika & Mantiq', 8, 'Prezident maktablari va Al-Xorazmiy olimpiadasiga tayyorlov bo\'yicha mutaxassis.', '+998 99 678 90 12', 'bobur@antigravity.uz', 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400&auto=format&fit=crop&q=80', 1)
    ]
    cursor.executemany('''
    INSERT INTO teachers (full_name, subject, experience_years, bio, phone, email, photo_url, active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', teachers)

    # Seed Users
    # 1. Super Admin: admin / admin123
    # 2. Admin: menejer / admin123
    # 3. Teacher: ustoz / ustoz123 (linked to teacher id 1)
    # 4. Teacher: dilshod / ustoz123 (linked to teacher id 2)
    users = [
        ('admin', generate_password_hash('admin123'), 'Super Administrator', 'superadmin', 'admin@antigravity.uz', '+998 71 200 45 45', None),
        ('menejer', generate_password_hash('admin123'), 'Nodira Salimova (Administrator)', 'admin', 'menejer@antigravity.uz', '+998 90 999 11 22', None),
        ('ustoz', generate_password_hash('ustoz123'), 'Sanjar Alimov (Ustoz)', 'teacher', 'sanjar@antigravity.uz', '+998 90 123 45 67', 1),
        ('dilshod', generate_password_hash('ustoz123'), 'Dilshod Karimov (Ustoz)', 'teacher', 'dilshod@antigravity.uz', '+998 91 234 56 78', 2),
        ('javohir', generate_password_hash('ustoz123'), 'Javohir Toshpulatov (Ustoz)', 'teacher', 'javohir@antigravity.uz', '+998 94 456 78 90', 4),
        ('bobur', generate_password_hash('ustoz123'), 'Bobur Mahmudov (Ustoz)', 'teacher', 'bobur@antigravity.uz', '+998 99 678 90 12', 6)
    ]
    cursor.executemany('''
    INSERT INTO users (username, password_hash, full_name, role, email, phone, teacher_id)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', users)

    # Seed Groups
    groups = [
        ('IELTS-Target-8', 3, 1, 'Xona 201', 'Dush-Chor-Jum 16:00 - 18:00', 1),
        ('Math-Olimpiada-1', 2, 2, 'Xona 105', 'Sesh-Pay-Shan 14:00 - 16:00', 1),
        ('English-Pre-Inter-A', 1, 3, 'Xona 203', 'Dush-Chor-Jum 14:00 - 16:00', 1),
        ('Python-Bootcamp-2026', 5, 4, 'Lab 301', 'Sesh-Pay-Shan 16:00 - 18:00', 1),
        ('Robo-Starter-1', 6, 5, 'Lab 102', 'Shanba-Yakshanba 10:00 - 13:00', 1),
        ('Math-Abituriyent-Pro', 2, 6, 'Xona 108', 'Dush-Chor-Jum 18:00 - 20:00', 1)
    ]
    cursor.executemany('''
    INSERT INTO groups (name, course_id, teacher_id, room, schedule, active)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', groups)

    # Seed Students
    # We create a solid cohort of 14 students.
    # Notice student 1 has steady high scores (88-95).
    # Student 2 (Aziz Karimov) has consecutive dropping scores (90 -> 82 -> 68) to trigger the automated warning!
    # Student 3 (Malika Saidova) has average dropping below 70 (62, 58, 64) triggering threshold warning!
    students = [
        ('Aziz', 'Karimov', '+998 90 111 22 33', '2007-04-12', 2, 2, 2, '543210987', 'Farhod Karimov', '+998 90 999 88 77', '987654321', 'active'),
        ('Malika', 'Saidova', '+998 93 222 33 44', '2008-08-21', 1, 3, 3, '543210988', 'Gulnora Saidova', '+998 93 888 77 66', '987654322', 'active'),
        ('Jasur', 'Eshmatov', '+998 94 333 44 55', '2006-11-05', 3, 1, 1, '543210989', 'Akmal Eshmatov', '+998 94 777 66 55', '987654323', 'active'),
        ('Shahzod', 'Tursunov', '+998 97 444 55 66', '2007-02-18', 5, 4, 4, '543210990', 'Olim Tursunov', '+998 97 666 55 44', '987654324', 'active'),
        ('Dildora', 'Qodirova', '+998 99 555 66 77', '2008-05-30', 3, 1, 1, '543210991', 'Nargiza Qodirova', '+998 99 555 44 33', '987654325', 'active'),
        ('Sardor', 'Normatov', '+998 90 666 77 88', '2006-09-14', 5, 4, 4, '543210992', 'Bahrom Normatov', '+998 90 444 33 22', '987654326', 'active'),
        ('Nigora', 'Xoliqova', '+998 91 777 88 99', '2007-12-03', 2, 2, 2, '543210993', 'Dilfuza Xoliqova', '+998 91 333 22 11', '987654327', 'active'),
        ('Ulug\'bek', 'Rahimov', '+998 93 888 99 00', '2009-01-25', 6, 5, 5, '543210994', 'Jamshid Rahimov', '+998 93 222 11 00', '987654328', 'active'),
        ('Rayhona', 'Zokirova', '+998 94 999 00 11', '2008-07-07', 1, 3, 3, '543210995', 'Fotima Zokirova', '+998 94 111 00 99', '987654329', 'active'),
        ('Bekzod', 'Yusupov', '+998 97 101 12 13', '2007-10-19', 2, 6, 6, '543210996', 'Erkin Yusupov', '+998 97 000 99 88', '987654330', 'active'),
        ('Kamola', 'Mirzayeva', '+998 99 202 23 24', '2006-03-15', 3, 1, 1, '543210997', 'Shoira Mirzayeva', '+998 99 899 88 77', '987654331', 'active'),
        ('Farrux', 'Aliyev', '+998 90 303 34 35', '2008-11-28', 5, 4, 4, '543210998', 'Shavkat Aliyev', '+998 90 788 66 55', '987654332', 'active')
    ]
    cursor.executemany('''
    INSERT INTO students (first_name, last_name, phone, birth_date, course_id, group_id, teacher_id, telegram_chat_id, parent_name, parent_phone, parent_telegram_chat_id, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', students)

    # Seed Historical Grades
    # Format: (student_id, subject, assessment_date, assessment_type, score, comment, created_by)
    # Aziz Karimov (ID 1): Drops from 91 -> 84 -> 72 -> 65 (Demonstrating warning)
    today = datetime.now()
    d1 = (today - timedelta(days=21)).strftime('%Y-%m-%d')
    d2 = (today - timedelta(days=14)).strftime('%Y-%m-%d')
    d3 = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    d4 = (today - timedelta(days=2)).strftime('%Y-%m-%d')
    d_today = today.strftime('%Y-%m-%d')

    grades = [
        # Student 1 (Aziz Karimov) - Mathematics - dropping trend
        (1, 'Matematika', d1, 'Nazorat ishi', 91.0, 'A\'lo darajada boshladi, formulalarni yaxshi biladi.', 2),
        (1, 'Matematika', d2, 'Test', 84.0, 'Yaxshi natija, biroq geometriya savollarida xatolar bor.', 2),
        (1, 'Matematika', d3, 'Uyga vazifa', 72.0, 'Uyga vazifaning 3 ta masalasi ishlanmagan.', 2),
        (1, 'Matematika', d4, 'Nazorat ishi', 65.0, 'Mavzuni to\'liq o\'zlashtirmagan, shoshilgan.', 2),

        # Student 2 (Malika Saidova) - English - low average < 70
        (2, 'Ingliz tili', d1, 'Test', 62.0, 'Grammatika mavzularida qiynalmoqda.', 3),
        (2, 'Ingliz tili', d2, 'Og\'zaki so\'rov', 58.0, 'So\'z boyligi yetarli emas.', 3),
        (2, 'Ingliz tili', d3, 'Nazorat ishi', 64.0, 'Yozma ishda imlo xatolari ko\'p.', 3),

        # Student 3 (Jasur Eshmatov) - IELTS - high performer
        (3, 'IELTS', d1, 'Mock Exam', 86.0, 'Reading 8.0, Listening 8.5. Judayam kuchli.', 1),
        (3, 'IELTS', d2, 'Nazorat ishi', 88.0, 'Writing Task 1 va 2 yaxshi tahlil qilingan.', 1),
        (3, 'IELTS', d3, 'Og\'zaki so\'rov', 92.0, 'Speaking ravon va boy lug\'at bilan o\'tdi.', 1),
        (3, 'IELTS', d4, 'Mock Exam', 94.0, 'Ajoyib natija! Band 8.5 ko\'rsatkich.', 1),

        # Student 4 (Shahzod Tursunov) - IT / Python
        (4, 'IT / Dasturlash', d1, 'Test', 85.0, 'Python sintaksisi va funksiyalar yaxshi.', 4),
        (4, 'IT / Dasturlash', d2, 'Nazorat ishi', 89.0, 'OOP va modullar bo\'yicha amaliy topshiriq bajarildi.', 4),
        (4, 'IT / Dasturlash', d3, 'Uyga vazifa', 95.0, 'Telegram bot loyihasi muvaffaqiyatli topshirildi.', 4),

        # Student 5 (Dildora Qodirova) - IELTS
        (5, 'IELTS', d1, 'Test', 78.0, 'Yaxshi harakat.', 1),
        (5, 'IELTS', d2, 'Mock Exam', 82.0, 'Listening sezilarli yaxshilandi.', 1),
        (5, 'IELTS', d3, 'Nazorat ishi', 85.0, 'Writing bo\'yicha barqaror o\'sish.', 1),

        # Student 6 (Sardor Normatov) - IT
        (6, 'IT / Dasturlash', d1, 'Nazorat ishi', 75.0, 'Boshlang\'ich tushunchalar o\'zlashtirildi.', 4),
        (6, 'IT / Dasturlash', d2, 'Test', 80.0, 'SQL so\'rovlar yaxshi bajarildi.', 4),

        # Student 7 (Nigora Xoliqova) - Matematika
        (7, 'Matematika', d1, 'Test', 94.0, 'A\'lo natija, barcha topshiriqlar to\'g\'ri.', 2),
        (7, 'Matematika', d2, 'Nazorat ishi', 96.0, 'Olimpiada masalalari to\'liq yechildi.', 2),

        # Student 8 (Ulug'bek Rahimov) - Robototexnika
        (8, 'Robototexnika', d1, 'Nazorat ishi', 88.0, 'Sxematexnika va datchiklar bilan ishlash yaxshi.', 5),
        (8, 'Robototexnika', d2, 'Uyga vazifa', 90.0, 'Arduino loyihasi a\'lo darajada yig\'ilgan.', 5),

        # Student 9 (Rayhona Zokirova) - General English
        (9, 'Ingliz tili', d1, 'Test', 82.0, 'Grammar test yaxshi natija berdi.', 3),
        (9, 'Ingliz tili', d2, 'Og\'zaki so\'rov', 85.0, 'Speaking faolligi yuqori.', 3),

        # Student 10 (Bekzod Yusupov) - Matematika
        (10, 'Matematika', d1, 'Nazorat ishi', 78.0, 'Trigonometriya yaxshi o\'zlashtirilgan.', 6),
        (10, 'Matematika', d2, 'Test', 82.0, 'Murakkab tenglamalar to\'g\'ri yechildi.', 6),

        # Student 11 (Kamola Mirzayeva) - IELTS
        (11, 'IELTS', d1, 'Mock Exam', 80.0, 'Overall Band 7.0.', 1),
        (11, 'IELTS', d2, 'Test', 84.0, 'Reading comprehension kuchaygan.', 1),

        # Student 12 (Farrux Aliyev) - IT
        (12, 'IT / Dasturlash', d1, 'Test', 88.0, 'Web API va JSON mavzulari a\'lo.', 4),
        (12, 'IT / Dasturlash', d2, 'Nazorat ishi', 91.0, 'Django REST framework loyihasi himoya qilindi.', 4)
    ]
    cursor.executemany('''
    INSERT INTO grades (student_id, subject, assessment_date, assessment_type, score, comment, created_by)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', grades)

    # Seed Warnings (specifically for Student 1 and Student 2 to illustrate the automatic detection)
    warnings = [
        (1, 'consecutive_drop', 87.5, 78.0, 9.5, 'Matematika', 'Baholar 3 marta ketma-ket pasaygan (91 -> 84 -> 72 -> 65). O\'quvchi diqqatini oshirish zarur.', 0),
        (2, 'threshold_below', 74.0, 61.3, 12.7, 'Ingliz tili', 'O\'rtacha baho belgilangan chegara (70 ball)dan pastga tushdi (61.3 ball).', 0)
    ]
    cursor.executemany('''
    INSERT INTO warnings (student_id, warning_type, previous_avg, current_avg, drop_amount, subjects, trigger_reason, resolved)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', warnings)

    # Seed Sample Attendance Records
    attendance_records = []
    for s_id in range(1, 13):
        # assign groups: 1,7 in grp 2; 2,9 in grp 3; 3,5,11 in grp 1; 4,6,12 in grp 4; 8 in grp 5; 10 in grp 6
        grp_id = 1 if s_id in [3, 5, 11] else (2 if s_id in [1, 7] else (3 if s_id in [2, 9] else (4 if s_id in [4, 6, 12] else (5 if s_id == 8 else 6))))
        attendance_records.append((s_id, grp_id, d1, 'present', 'Darsda faol'))
        attendance_records.append((s_id, grp_id, d2, 'present' if s_id != 1 else 'late', '10 daqiqa kechikdi' if s_id == 1 else 'Vaqtida keldi'))
        attendance_records.append((s_id, grp_id, d3, 'present' if s_id != 2 else 'absent', 'Sababli' if s_id == 2 else 'Darsda qatnashdi'))
        attendance_records.append((s_id, grp_id, d4, 'present', 'Vaqtida keldi'))

    cursor.executemany('''
    INSERT INTO attendance (student_id, group_id, date, status, note)
    VALUES (?, ?, ?, ?, ?)
    ''', attendance_records)

    # Seed Sample Notification Logs
    notifications = [
        ('student', 'Aziz Karimov', '543210987', 'grade', '📚 ANTIGRAVITY\n\nSalom, Aziz!\n\nSizga yangi baho qo‘yildi.\n\nFan: Matematika\nBaho: 65\nSana: ' + d4 + '\nIzoh: Mavzuni to\'liq o\'zlashtirmagan, shoshilgan.\n\nANTIGRAVITY ta\'lim markazi', 'sent', None),
        ('student', 'Aziz Karimov', '543210987', 'warning', '⚠️ ANTIGRAVITY OGOHLANTIRISH\n\nSizning o‘quv natijangiz pasaymoqda.\n\nOldingi o‘rtacha baho: 87.5\nHozirgi o‘rtacha baho: 78.0\n\nIltimos, keyingi darslarda natijangizni yaxshilashga harakat qiling.', 'sent', None),
        ('parent', 'Farhod Karimov (Ota-ona)', '987654321', 'parent_warning', '⚠️ Muhim ogohlantirish\n\nFarzandingizning o‘quv natijalarida pasayish kuzatildi.\n\nO‘quvchi: Aziz Karimov\nOldingi o‘rtacha: 87.5\nHozirgi o‘rtacha: 78.0\n\nIltimos, natijalarni nazorat qilib boring.', 'sent', None),
        ('student', 'Jasur Eshmatov', '543210989', 'grade', '📚 ANTIGRAVITY\n\nSalom, Jasur!\n\nSizga yangi baho qo‘yildi.\n\nFan: IELTS\nBaho: 94\nSana: ' + d4 + '\nIzoh: Ajoyib natija! Band 8.5 ko\'rsatkich.\n\nANTIGRAVITY ta\'lim markazi', 'sent', None)
    ]
    cursor.executemany('''
    INSERT INTO notification_logs (recipient_type, recipient_name, chat_id, message_type, message_body, status, error_message)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', notifications)

    # Seed Sample Leads (from public site)
    leads = [
        ('Botir Qosimov', '+998 90 777 12 34', 'IELTS', 'Darslar vaqti va to\'lov haqida to\'liq ma\'lumot olmoqchiman.', 'new'),
        ('Gulbahor Karimova', '+998 93 456 78 90', 'IT / Dasturlash', 'Farzandim 15 yoshda, Python kursiga yozdirmoqchiman.', 'contacted'),
        ('Shohrux Mirzayev', '+998 94 123 99 88', 'Matematika', 'Repetitorlik va testlarga tayyorgarlik bo\'yicha qiziqmoqdaman.', 'enrolled')
    ]
    cursor.executemany('''
    INSERT INTO leads (full_name, phone, course_name, message, status)
    VALUES (?, ?, ?, ?, ?)
    ''', leads)

    conn.commit()
    conn.close()

if __name__ == '__main__':
    print("Initializing ANTIGRAVITY database...")
    init_db()
    seed_db()
    print("Database initialized and populated successfully!")
