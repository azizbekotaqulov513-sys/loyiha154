import os
from functools import wraps
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    session, jsonify, abort
)
from dotenv import load_dotenv
from werkzeug.security import check_password_hash, generate_password_hash

import database
from database import get_db_connection, init_db, seed_db
import analytics_service
import telegram_service

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'antigravity-secret-key-2026-production')

# Ensure DB is ready
init_db()
seed_db()

# -------------------------------------------------------------
# Context Processors & Helpers
# -------------------------------------------------------------
@app.context_processor
def inject_global_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Active warning count for badge
    cursor.execute("SELECT COUNT(DISTINCT student_id) FROM warnings WHERE resolved = 0")
    unresolved_warnings_count = cursor.fetchone()[0]

    # Unread leads count
    cursor.execute("SELECT COUNT(*) FROM leads WHERE status = 'new'")
    new_leads_count = cursor.fetchone()[0]

    # Unread student messages to teacher
    unread_teacher_messages_count = 0
    if 'user' in session:
        u = session['user']
        if u.get('role') == 'teacher' and u.get('teacher_id'):
            cursor.execute("SELECT COUNT(*) FROM teacher_messages WHERE teacher_id = ? AND sender_type = 'student' AND is_read = 0", (u['teacher_id'],))
            unread_teacher_messages_count = cursor.fetchone()[0]
        elif u.get('role') in ['superadmin', 'admin']:
            cursor.execute("SELECT COUNT(*) FROM teacher_messages WHERE sender_type = 'student' AND is_read = 0")
            unread_teacher_messages_count = cursor.fetchone()[0]

    # Center settings
    cursor.execute("SELECT key, value FROM settings")
    settings_dict = {row['key']: row['value'] for row in cursor.fetchall()}

    conn.close()

    return {
        'unresolved_warnings_count': unresolved_warnings_count,
        'new_leads_count': new_leads_count,
        'unread_teacher_messages_count': unread_teacher_messages_count,
        'current_year': datetime.now().year,
        'center_settings': settings_dict,
        'current_user': session.get('user')
    }

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash("Tizimga kirishingiz lozim!", "warning")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            user_role = session['user']['role']
            if user_role not in roles and user_role != 'superadmin':
                flash("Ushbu bo'limga kirish uchun sizda yetarli huquq yo'q!", "danger")
                return redirect(url_for('admin_dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# -------------------------------------------------------------
# PUBLIC WEBSITE ROUTES
# -------------------------------------------------------------
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Active courses
    cursor.execute("SELECT * FROM courses WHERE active = 1 ORDER BY id ASC")
    courses = [dict(r) for r in cursor.fetchall()]

    # Active teachers
    cursor.execute("SELECT * FROM teachers WHERE active = 1 ORDER BY id ASC")
    teachers = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_template('public/index.html', courses=courses, teachers=teachers)

@app.route('/api/enroll', methods=['POST'])
def api_enroll():
    data = request.get_json() or request.form
    full_name = data.get('full_name', '').strip()
    phone = data.get('phone', '').strip()
    course_name = data.get('course_name', '').strip()
    message = data.get('message', '').strip()

    if not full_name or not phone:
        return jsonify({'success': False, 'message': 'Iltimos, ismingiz va telefon raqamingizni kiriting!'}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO leads (full_name, phone, course_name, message, status)
    VALUES (?, ?, ?, ?, 'new')
    ''', (full_name, phone, course_name, message))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'message': "Arizangiz muvaffaqiyatli qabul qilindi! Tez orada mutaxassisimiz siz bilan bog'lanadi."
    })

# -------------------------------------------------------------
# STUDENT PORTAL (O'quvchi Kabineti)
# -------------------------------------------------------------
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if 'student' in session:
        return redirect(url_for('student_cabinet'))

    if request.method == 'POST':
        identifier = request.form.get('student_identifier', '').strip()
        if not identifier:
            flash("Iltimos, ID raqamingiz yoki telefoningizni kiriting!", "danger")
            return render_template('public/student_login.html')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM students 
        WHERE id = ? OR phone = ? OR phone = ? OR telegram_chat_id = ?
        ''', (identifier, identifier, f"+{identifier}", identifier))
        student = cursor.fetchone()
        conn.close()

        if student:
            session['student'] = {
                'id': student['id'],
                'first_name': student['first_name'],
                'last_name': student['last_name'],
                'phone': student['phone']
            }
            flash(f"Xush kelibsiz, {student['first_name']}!", "success")
            return redirect(url_for('student_cabinet'))
        else:
            flash(f"Bunday ID ({identifier}) yoki telefon raqamli o'quvchi topilmadi! Ma'muriyatga murojaat qiling.", "danger")

    return render_template('public/student_login.html')

@app.route('/student')
@app.route('/student/cabinet')
def student_cabinet():
    if 'student' not in session:
        flash("Kabinetga kirish uchun o'quvchi ID raqamingizni kiriting!", "warning")
        return redirect(url_for('student_login'))

    student_id = session['student']['id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT 
        s.*,
        c.title as course_title,
        gr.name as group_name,
        gr.schedule as group_schedule,
        gr.room as group_room,
        t.full_name as teacher_name
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN teachers t ON s.teacher_id = t.id
    WHERE s.id = ?
    ''', (student_id,))
    student = cursor.fetchone()

    if not student:
        session.pop('student', None)
        flash("O'quvchi ma'lumotlari topilmadi!", "danger")
        return redirect(url_for('student_login'))

    stats = analytics_service.get_student_stats(student_id)

    cursor.execute('''
    SELECT * FROM grades
    WHERE student_id = ?
    ORDER BY assessment_date DESC, id DESC
    ''', (student_id,))
    grades = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
    SELECT * FROM warnings
    WHERE student_id = ? AND resolved = 0
    ORDER BY created_at DESC
    ''', (student_id,))
    warnings = [dict(r) for r in cursor.fetchall()]

    # 1. Teacher messages for this student
    cursor.execute('''
    SELECT tm.*, t.full_name as teacher_name
    FROM teacher_messages tm
    LEFT JOIN teachers t ON tm.teacher_id = t.id
    WHERE tm.student_id = ?
    ORDER BY tm.created_at ASC
    ''', (student_id,))
    teacher_messages = [dict(r) for r in cursor.fetchall()]

    # Mark unread incoming messages from teacher as read
    cursor.execute("UPDATE teacher_messages SET is_read = 1 WHERE student_id = ? AND sender_type = 'teacher'", (student_id,))
    conn.commit()

    # 2. Group messages & members
    group_messages = []
    group_members = []
    if student['group_id']:
        cursor.execute('''
        SELECT * FROM group_messages
        WHERE group_id = ?
        ORDER BY created_at ASC
        LIMIT 100
        ''', (student['group_id'],))
        group_messages = [dict(r) for r in cursor.fetchall()]

        cursor.execute('''
        SELECT id, first_name, last_name, phone
        FROM students
        WHERE group_id = ?
        ORDER BY first_name ASC
        ''', (student['group_id'],))
        group_members = [dict(r) for r in cursor.fetchall()]

        # 3. Homework assignments and submissions for this student
        cursor.execute('''
        SELECT h.*, c.title as course_title,
               hs.id as submission_id, hs.status as submission_status,
               hs.score as submission_score, hs.feedback as submission_feedback,
               hs.submission_text, hs.submitted_at
        FROM homework h
        LEFT JOIN courses c ON h.course_id = c.id
        LEFT JOIN homework_submissions hs ON hs.homework_id = h.id AND hs.student_id = ?
        WHERE h.group_id = ?
        ORDER BY h.due_date DESC
        ''', (student_id, student['group_id']))
        homework_list = [dict(r) for r in cursor.fetchall()]

    # Student rank on leaderboard
    cursor.execute('''
    SELECT student_id, ROUND(AVG(score), 1) as avg_score
    FROM grades
    GROUP BY student_id
    HAVING avg_score IS NOT NULL
    ORDER BY avg_score DESC
    ''')
    ranked_students = [r['student_id'] for r in cursor.fetchall()]
    student_rank = (ranked_students.index(student_id) + 1) if student_id in ranked_students else '—'

    # 4. Antigravity Coins balance & transactions
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM coins_transactions WHERE student_id = ?", (student_id,))
    coins_balance = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM coins_transactions WHERE student_id = ? ORDER BY created_at DESC LIMIT 10", (student_id,))
    coins_transactions = [dict(r) for r in cursor.fetchall()]

    # 5. Rewards shop catalog & student orders
    cursor.execute("SELECT * FROM rewards WHERE active = 1 ORDER BY cost_coins ASC")
    rewards = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
    SELECT ro.*, r.title as reward_title, r.cost_coins, r.icon
    FROM reward_orders ro
    JOIN rewards r ON ro.reward_id = r.id
    WHERE ro.student_id = ?
    ORDER BY ro.ordered_at DESC
    ''', (student_id,))
    reward_orders = [dict(r) for r in cursor.fetchall()]

    # 6. Interactive Quizzes
    cursor.execute('''
    SELECT q.*,
           (SELECT score FROM quiz_attempts qa WHERE qa.quiz_id = q.id AND qa.student_id = ? ORDER BY score DESC LIMIT 1) as best_score,
           (SELECT passed FROM quiz_attempts qa WHERE qa.quiz_id = q.id AND qa.student_id = ? ORDER BY score DESC LIMIT 1) as is_passed,
           (SELECT COUNT(*) FROM quiz_questions qq WHERE qq.quiz_id = q.id) as question_count
    FROM quizzes q
    WHERE q.active = 1
    ORDER BY q.id ASC
    ''', (student_id, student_id))
    quizzes = [dict(r) for r in cursor.fetchall()]

    conn.close()

    bot_name = telegram_service.get_bot_username()
    bot_url = telegram_service.get_bot_url()

    chart_grades = list(reversed(grades))
    chart_labels = [g['assessment_date'] for g in chart_grades]
    chart_scores = [g['score'] for g in chart_grades]

    return render_template(
        'public/student_cabinet.html',
        student=dict(student),
        stats=stats,
        grades=grades,
        warnings=warnings,
        teacher_messages=teacher_messages,
        group_messages=group_messages,
        group_members=group_members,
        homework_list=homework_list,
        student_rank=student_rank,
        coins_balance=coins_balance,
        coins_transactions=coins_transactions,
        rewards=rewards,
        reward_orders=reward_orders,
        quizzes=quizzes,
        bot_name=bot_name,
        bot_url=bot_url,
        chart_labels=chart_labels,
        chart_scores=chart_scores
    )

@app.route('/student/logout')
def student_logout():
    session.pop('student', None)
    flash("Kabinetdan chiqdingiz.", "info")
    return redirect(url_for('student_login'))

@app.route('/api/student/update-telegram', methods=['POST'])
def api_student_update_telegram():
    if 'student' not in session:
        return jsonify({'success': False, 'message': "Avtorizatsiyadan o'tilmagan"}), 401
    student_id = session['student']['id']
    chat_id = request.form.get('telegram_chat_id', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE students SET telegram_chat_id = ? WHERE id = ?", (chat_id if chat_id else None, student_id))
    conn.commit()
    conn.close()

    return jsonify({
        'success': True,
        'chat_id': chat_id,
        'message': f"Telegram Chat ID muvaffaqiyatli saqlandi! Endi baholar @kino05_promaks_bot orqali yuboriladi."
    })

@app.route('/api/chat/teacher/messages')
def api_chat_teacher_messages():
    if 'student' not in session:
        return jsonify({'success': False, 'message': "Avtorizatsiyadan o'tilmagan"}), 401
    student_id = session['student']['id']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT tm.*, t.full_name as teacher_name
    FROM teacher_messages tm
    LEFT JOIN teachers t ON tm.teacher_id = t.id
    WHERE tm.student_id = ?
    ORDER BY tm.created_at ASC
    ''', (student_id,))
    messages = [dict(r) for r in cursor.fetchall()]

    # Mark read
    cursor.execute("UPDATE teacher_messages SET is_read = 1 WHERE student_id = ? AND sender_type = 'teacher'", (student_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'messages': messages})

@app.route('/api/chat/teacher/send', methods=['POST'])
def api_chat_teacher_send():
    if 'student' not in session:
        return jsonify({'success': False, 'message': "Avtorizatsiyadan o'tilmagan"}), 401
    student_id = session['student']['id']
    message_text = request.form.get('message', '').strip()

    if not message_text:
        return jsonify({'success': False, 'message': "Xabar matnini kiriting!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT teacher_id, first_name, last_name FROM students WHERE id = ?", (student_id,))
    stu = cursor.fetchone()

    teacher_id = stu['teacher_id'] if (stu and stu['teacher_id']) else 1
    student_name = f"{stu['first_name']} {stu['last_name']}" if stu else "O'quvchi"

    cursor.execute('''
    INSERT INTO teacher_messages (student_id, teacher_id, sender_type, sender_id, message, is_read)
    VALUES (?, ?, 'student', ?, ?, 0)
    ''', (student_id, teacher_id, student_id, message_text))
    conn.commit()
    msg_id = cursor.lastrowid

    # Check if teacher has telegram chat id
    cursor.execute("SELECT phone FROM teachers WHERE id = ?", (teacher_id,))
    conn.close()

    return jsonify({
        'success': True,
        'message_id': msg_id,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'message': "Xabaringiz ustozga yuborildi!"
    })

@app.route('/api/chat/group/messages')
def api_chat_group_messages():
    if 'student' not in session:
        return jsonify({'success': False, 'message': "Avtorizatsiyadan o'tilmagan"}), 401
    student_id = session['student']['id']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT group_id FROM students WHERE id = ?", (student_id,))
    stu = cursor.fetchone()

    if not stu or not stu['group_id']:
        conn.close()
        return jsonify({'success': True, 'messages': [], 'group_name': None})

    group_id = stu['group_id']
    cursor.execute("SELECT name FROM groups WHERE id = ?", (group_id,))
    grp = cursor.fetchone()
    group_name = grp['name'] if grp else 'Guruh'

    cursor.execute('''
    SELECT * FROM group_messages
    WHERE group_id = ?
    ORDER BY created_at ASC
    LIMIT 100
    ''', (group_id,))
    messages = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return jsonify({'success': True, 'messages': messages, 'group_name': group_name, 'current_student_id': student_id})

@app.route('/api/chat/group/send', methods=['POST'])
def api_chat_group_send():
    if 'student' not in session:
        return jsonify({'success': False, 'message': "Avtorizatsiyadan o'tilmagan"}), 401
    student_id = session['student']['id']
    message_text = request.form.get('message', '').strip()

    if not message_text:
        return jsonify({'success': False, 'message': "Xabar matnini kiriting!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT group_id, first_name, last_name FROM students WHERE id = ?", (student_id,))
    stu = cursor.fetchone()

    if not stu or not stu['group_id']:
        conn.close()
        return jsonify({'success': False, 'message': "Siz hali guruhga biriktirilmagansiz!"}), 400

    group_id = stu['group_id']
    sender_name = f"{stu['first_name']} {stu['last_name']}"

    cursor.execute('''
    INSERT INTO group_messages (group_id, sender_type, sender_id, sender_name, message)
    VALUES (?, 'student', ?, ?, ?)
    ''', (group_id, student_id, sender_name, message_text))
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()

    return jsonify({
        'success': True,
        'message_id': msg_id,
        'sender_name': sender_name,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'message': "Xabar guruhga yuborildi!"
    })

# -------------------------------------------------------------
# AUTHENTICATION
# -------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user'] = {
                'id': user['id'],
                'username': user['username'],
                'full_name': user['full_name'],
                'role': user['role'],
                'email': user['email'],
                'phone': user['phone'],
                'teacher_id': user['teacher_id']
            }
            flash(f"Xush kelibsiz, {user['full_name']}!", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('admin_dashboard'))
        else:
            flash("Foydalanuvchi nomi yoki parol noto'g'ri!", "danger")

    return render_template('admin/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Tizimdan muvaffaqiyatli chiqdingiz.", "info")
    return redirect(url_for('login'))

# -------------------------------------------------------------
# ADMIN DASHBOARD
# -------------------------------------------------------------
@app.route('/admin')
@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    dashboard_data = analytics_service.get_dashboard_data()
    return render_template('admin/dashboard.html', data=dashboard_data)

# -------------------------------------------------------------
# STUDENTS MANAGEMENT (CRUD, Profile, Search, Filter)
# -------------------------------------------------------------
@app.route('/admin/students')
@login_required
def admin_students():
    search = request.args.get('search', '').strip()
    course_id = request.args.get('course_id', '').strip()
    group_id = request.args.get('group_id', '').strip()
    status_filter = request.args.get('status', '').strip()
    warning_filter = request.args.get('warning', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    # Query builders
    query = '''
    SELECT 
        s.*,
        c.title as course_title,
        gr.name as group_name,
        t.full_name as teacher_name,
        ROUND(AVG(g.score), 1) as avg_score,
        COUNT(g.id) as grades_count,
        (SELECT COUNT(*) FROM warnings w WHERE w.student_id = s.id AND w.resolved = 0) as active_warnings
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN teachers t ON s.teacher_id = t.id
    LEFT JOIN grades g ON s.id = g.student_id
    WHERE 1=1
    '''
    params = []

    # Teacher role filter: only see students assigned to their teacher profile
    if session['user']['role'] == 'teacher' and session['user']['teacher_id']:
        query += " AND s.teacher_id = ?"
        params.append(session['user']['teacher_id'])

    if search:
        query += " AND (s.first_name LIKE ? OR s.last_name LIKE ? OR s.phone LIKE ? OR s.telegram_chat_id LIKE ?)"
        wildcard = f"%{search}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])

    if course_id:
        query += " AND s.course_id = ?"
        params.append(course_id)

    if group_id:
        query += " AND s.group_id = ?"
        params.append(group_id)

    if status_filter:
        query += " AND s.status = ?"
        params.append(status_filter)

    query += " GROUP BY s.id"

    if warning_filter == '1':
        query += " HAVING active_warnings > 0"

    query += " ORDER BY s.id DESC"

    cursor.execute(query, params)
    all_students = [dict(r) for r in cursor.fetchall()]

    import math
    page = int(request.args.get('page', 1))
    per_page = 50
    total_students = len(all_students)
    total_pages = max(1, math.ceil(total_students / per_page))
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    paginated_students = all_students[(page - 1) * per_page : page * per_page]

    # Fetch courses, groups, teachers for filters & modal
    cursor.execute("SELECT id, title FROM courses WHERE active = 1")
    courses = cursor.fetchall()

    cursor.execute("SELECT id, name FROM groups WHERE active = 1")
    groups = cursor.fetchall()

    cursor.execute("SELECT id, full_name FROM teachers WHERE active = 1")
    teachers = cursor.fetchall()

    conn.close()

    return render_template(
        'admin/students.html',
        students=paginated_students,
        total_students=total_students,
        current_page=page,
        total_pages=total_pages,
        courses=courses,
        groups=groups,
        teachers=teachers,
        search=search,
        selected_course=course_id,
        selected_group=group_id,
        selected_status=status_filter,
        warning_filter=warning_filter
    )

@app.route('/admin/students/create', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def student_create():
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone = request.form.get('phone', '').strip()
    birth_date = request.form.get('birth_date', '').strip()
    course_id = request.form.get('course_id') or None
    group_id = request.form.get('group_id') or None
    teacher_id = request.form.get('teacher_id') or None
    telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
    parent_name = request.form.get('parent_name', '').strip()
    parent_phone = request.form.get('parent_phone', '').strip()
    parent_telegram_chat_id = request.form.get('parent_telegram_chat_id', '').strip()
    status = request.form.get('status', 'active')

    if not first_name or not last_name or not phone:
        flash("Ism, Familiya va Telefon raqami kiritilishi shart!", "danger")
        return redirect(url_for('admin_students'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO students (
        first_name, last_name, phone, birth_date, course_id, group_id, teacher_id,
        telegram_chat_id, parent_name, parent_phone, parent_telegram_chat_id, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        first_name, last_name, phone, birth_date, course_id, group_id, teacher_id,
        telegram_chat_id, parent_name, parent_phone, parent_telegram_chat_id, status
    ))
    conn.commit()
    new_student_id = cursor.lastrowid

    course_title = ''
    group_name = ''
    if course_id:
        cursor.execute("SELECT title FROM courses WHERE id = ?", (course_id,))
        cr = cursor.fetchone()
        if cr:
            course_title = cr['title']
    if group_id:
        cursor.execute("SELECT name FROM groups WHERE id = ?", (group_id,))
        gr = cursor.fetchone()
        if gr:
            group_name = gr['name']
    conn.close()

    # Send welcome notification via @kino05_promaks_bot
    telegram_service.send_student_welcome_notification(
        {
            'id': new_student_id,
            'first_name': first_name,
            'last_name': last_name,
            'telegram_chat_id': telegram_chat_id,
            'parent_telegram_chat_id': parent_telegram_chat_id
        },
        course_title=course_title,
        group_name=group_name
    )

    flash(f"O'quvchi {first_name} {last_name} muvaffaqiyatli qo'shildi va @kino05_promaks_bot orqali xabar yuborildi!", "success")
    return redirect(url_for('admin_students'))

@app.route('/admin/students/<int:id>')
@login_required
def student_detail(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Student info
    cursor.execute('''
    SELECT 
        s.*,
        c.title as course_title,
        gr.name as group_name,
        t.full_name as teacher_name
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN teachers t ON s.teacher_id = t.id
    WHERE s.id = ?
    ''', (id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("O'quvchi topilmadi!", "danger")
        return redirect(url_for('admin_students'))

    # Security check for teacher
    if session['user']['role'] == 'teacher' and session['user']['teacher_id']:
        if student['teacher_id'] != session['user']['teacher_id']:
            conn.close()
            flash("Siz faqat o'zingizga biriktirilgan o'quvchi profilini ko'ra olasiz!", "danger")
            return redirect(url_for('admin_students'))

    # Performance stats
    stats = analytics_service.get_student_stats(id)

    # Grades history
    cursor.execute('''
    SELECT 
        g.*,
        u.full_name as created_by_name
    FROM grades g
    LEFT JOIN users u ON g.created_by = u.id
    WHERE g.student_id = ?
    ORDER BY g.assessment_date DESC, g.id DESC
    ''', (id,))
    grades = [dict(r) for r in cursor.fetchall()]

    # Attendance history
    cursor.execute('''
    SELECT * FROM attendance
    WHERE student_id = ?
    ORDER BY date DESC
    LIMIT 20
    ''', (id,))
    attendances = [dict(r) for r in cursor.fetchall()]

    # Warnings history
    cursor.execute('''
    SELECT * FROM warnings
    WHERE student_id = ?
    ORDER BY created_at DESC
    ''', (id,))
    warnings = [dict(r) for r in cursor.fetchall()]

    # Lists for modals
    cursor.execute("SELECT id, title FROM courses WHERE active = 1")
    courses = cursor.fetchall()
    cursor.execute("SELECT id, name FROM groups WHERE active = 1")
    groups = cursor.fetchall()
    cursor.execute("SELECT id, full_name FROM teachers WHERE active = 1")
    teachers = cursor.fetchall()

    conn.close()

    # Grades data for single student chart
    chart_grades = list(reversed(grades))
    chart_labels = [g['assessment_date'] for g in chart_grades]
    chart_scores = [g['score'] for g in chart_grades]

    return render_template(
        'admin/student_detail.html',
        student=dict(student),
        stats=stats,
        grades=grades,
        attendances=attendances,
        warnings=warnings,
        courses=courses,
        groups=groups,
        teachers=teachers,
        chart_labels=chart_labels,
        chart_scores=chart_scores
    )

@app.route('/admin/students/<int:id>/update', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def student_update(id):
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone = request.form.get('phone', '').strip()
    birth_date = request.form.get('birth_date', '').strip()
    course_id = request.form.get('course_id') or None
    group_id = request.form.get('group_id') or None
    teacher_id = request.form.get('teacher_id') or None
    telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
    parent_name = request.form.get('parent_name', '').strip()
    parent_phone = request.form.get('parent_phone', '').strip()
    parent_telegram_chat_id = request.form.get('parent_telegram_chat_id', '').strip()
    status = request.form.get('status', 'active')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE students SET
        first_name = ?, last_name = ?, phone = ?, birth_date = ?,
        course_id = ?, group_id = ?, teacher_id = ?,
        telegram_chat_id = ?, parent_name = ?, parent_phone = ?,
        parent_telegram_chat_id = ?, status = ?
    WHERE id = ?
    ''', (
        first_name, last_name, phone, birth_date, course_id, group_id, teacher_id,
        telegram_chat_id, parent_name, parent_phone, parent_telegram_chat_id, status, id
    ))
    conn.commit()
    conn.close()

    flash("O'quvchi ma'lumotlari muvaffaqiyatli yangilandi!", "success")
    return redirect(url_for('student_detail', id=id))

@app.route('/admin/students/<int:id>/delete', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def student_delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("O'quvchi tizimdan o'chirildi.", "info")
    return redirect(url_for('admin_students'))

# -------------------------------------------------------------
# GRADES MANAGEMENT (Grading, Automatic Drop Detection, Telegram)
# -------------------------------------------------------------
@app.route('/admin/grades')
@login_required
def admin_grades():
    student_id = request.args.get('student_id', '').strip()
    course_id = request.args.get('course_id', '').strip()
    assessment_type = request.args.get('type', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
    SELECT 
        g.*,
        s.first_name,
        s.last_name,
        c.title as course_title,
        gr.name as group_name,
        u.full_name as teacher_name
    FROM grades g
    JOIN students s ON g.student_id = s.id
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN users u ON g.created_by = u.id
    WHERE 1=1
    '''
    params = []

    # If teacher role
    if session['user']['role'] == 'teacher' and session['user']['teacher_id']:
        query += " AND s.teacher_id = ?"
        params.append(session['user']['teacher_id'])

    if student_id:
        query += " AND g.student_id = ?"
        params.append(student_id)

    if course_id:
        query += " AND s.course_id = ?"
        params.append(course_id)

    if assessment_type:
        query += " AND g.assessment_type = ?"
        params.append(assessment_type)

    if date_from:
        query += " AND g.assessment_date >= ?"
        params.append(date_from)

    if date_to:
        query += " AND g.assessment_date <= ?"
        params.append(date_to)

    query += " ORDER BY g.assessment_date DESC, g.id DESC"

    cursor.execute(query, params)
    grades = [dict(r) for r in cursor.fetchall()]

    # Students list for add grade modal
    if session['user']['role'] == 'teacher' and session['user']['teacher_id']:
        cursor.execute("SELECT id, first_name, last_name FROM students WHERE teacher_id = ? AND status = 'active' ORDER BY first_name ASC", (session['user']['teacher_id'],))
    else:
        cursor.execute("SELECT id, first_name, last_name FROM students WHERE status = 'active' ORDER BY first_name ASC")
    students = cursor.fetchall()

    cursor.execute("SELECT id, title FROM courses WHERE active = 1")
    courses = cursor.fetchall()

    conn.close()

    return render_template(
        'admin/grades.html',
        grades=grades,
        students=students,
        courses=courses,
        selected_student=student_id,
        selected_course=course_id,
        selected_type=assessment_type,
        date_from=date_from,
        date_to=date_to
    )

@app.route('/admin/grades/create', methods=['POST'])
@login_required
def grade_create():
    student_id = request.form.get('student_id')
    subject = request.form.get('subject', '').strip()
    assessment_date = request.form.get('assessment_date') or datetime.now().strftime('%Y-%m-%d')
    assessment_type = request.form.get('assessment_type', 'Test')
    score_raw = request.form.get('score', '').strip()
    comment = request.form.get('comment', '').strip()

    if not student_id or not subject or not score_raw:
        flash("O'quvchi, fan va baho balli kiritilishi shart!", "danger")
        return redirect(request.referrer or url_for('admin_grades'))

    try:
        score = float(score_raw)
        if score < 0 or score > 100:
            flash("Baho 0 dan 100 gacha bo'lishi lozim!", "danger")
            return redirect(request.referrer or url_for('admin_grades'))
    except ValueError:
        flash("Baho raqam ko'rinishida bo'lishi kerak!", "danger")
        return redirect(request.referrer or url_for('admin_grades'))

    created_by = session['user']['id']

    # Record grade, trigger Telegram and warning analysis
    grade_id, warning, is_expelled = analytics_service.record_new_grade(
        student_id=int(student_id),
        subject=subject,
        assessment_date=assessment_date,
        assessment_type=assessment_type,
        score=score,
        comment=comment,
        created_by=created_by
    )

    if is_expelled:
        flash(
            f"🚫 DIQQAT: O'quvchi {score} ball (< 10 ball) olgani sababli tizimdan AVTOMATIK CHETLASHTIRILDI (Holati: Nofaol) va Telegram orqali chetlashtirish xabarnomasi yuborildi!",
            "danger"
        )
    elif warning:
        flash(
            f"Baho saqlandi va Telegram orqali yuborildi! ⚠️ DIQQAT: Ushbu o'quvchida baholar pasayishi aniqlandi va ogohlantirish yuborildi! ({warning['trigger_reason']})",
            "warning"
        )
    else:
        flash("Baho muvaffaqiyatli saqlandi va Telegram orqali xabar yuborildi!", "success")

    return redirect(request.referrer or url_for('admin_grades'))

@app.route('/admin/grades/<int:id>/delete', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def grade_delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM grades WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Baho o'chirildi.", "info")
    return redirect(request.referrer or url_for('admin_grades'))

# -------------------------------------------------------------
# DEDICATED WARNINGS SECTION (⚠️ Ogohlantirishlar)
# -------------------------------------------------------------
@app.route('/admin/warnings')
@login_required
def admin_warnings():
    status_filter = request.args.get('status', 'active') # 'active' or 'all' or 'resolved'

    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
    SELECT 
        w.*,
        s.first_name,
        s.last_name,
        s.phone,
        s.telegram_chat_id,
        s.parent_name,
        s.parent_phone,
        s.parent_telegram_chat_id,
        c.title as course_title,
        gr.name as group_name,
        t.full_name as teacher_name
    FROM warnings w
    JOIN students s ON w.student_id = s.id
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN teachers t ON s.teacher_id = t.id
    WHERE 1=1
    '''
    params = []

    if session['user']['role'] == 'teacher' and session['user']['teacher_id']:
        query += " AND s.teacher_id = ?"
        params.append(session['user']['teacher_id'])

    if status_filter == 'active':
        query += " AND w.resolved = 0"
    elif status_filter == 'resolved':
        query += " AND w.resolved = 1"

    query += " ORDER BY w.created_at DESC"

    cursor.execute(query, params)
    warnings = [dict(r) for r in cursor.fetchall()]

    # Append recent 3 grades to each warning for instant view
    for w in warnings:
        cursor.execute('''
        SELECT score, assessment_date, subject, assessment_type
        FROM grades
        WHERE student_id = ?
        ORDER BY assessment_date DESC, id DESC
        LIMIT 4
        ''', (w['student_id'],))
        w['recent_grades'] = [dict(g) for g in cursor.fetchall()]

    conn.close()

    return render_template('admin/warnings.html', warnings=warnings, status_filter=status_filter)

@app.route('/admin/warnings/<int:id>/resolve', methods=['POST'])
@login_required
def warning_resolve(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE warnings SET resolved = 1 WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Ogohlantirish holati 'Yechildi' deb belgilandi!", "success")
    return redirect(url_for('admin_warnings'))

@app.route('/admin/warnings/<int:id>/notify', methods=['POST'])
@login_required
def warning_notify(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT w.*, s.first_name, s.last_name, s.telegram_chat_id, s.parent_name, s.parent_telegram_chat_id
    FROM warnings w
    JOIN students s ON w.student_id = s.id
    WHERE w.id = ?
    ''', (id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        flash("Ogohlantirish topilmadi!", "danger")
        return redirect(url_for('admin_warnings'))

    student_dict = dict(row)
    telegram_service.send_student_warning_notification(
        student_dict,
        row['previous_avg'],
        row['current_avg'],
        row['drop_amount']
    )
    telegram_service.send_parent_warning_notification(
        student_dict,
        row['previous_avg'],
        row['current_avg'],
        row['drop_amount']
    )

    flash("O'quvchi va ota-onaga takroriy ogohlantirish xabari yuborildi!", "success")
    return redirect(url_for('admin_warnings'))

# -------------------------------------------------------------
# COURSES MANAGEMENT (CRUD)
# -------------------------------------------------------------
@app.route('/admin/courses')
@login_required
@role_required('superadmin', 'admin')
def admin_courses():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT 
        c.*,
        COUNT(DISTINCT s.id) as students_count,
        COUNT(DISTINCT gr.id) as groups_count
    FROM courses c
    LEFT JOIN students s ON c.id = s.course_id
    LEFT JOIN groups gr ON c.id = gr.course_id
    GROUP BY c.id
    ORDER BY c.id ASC
    ''')
    courses = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_template('admin/courses.html', courses=courses)

@app.route('/admin/courses/create', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def course_create():
    title = request.form.get('title', '').strip()
    slug = request.form.get('slug', '').strip().lower().replace(' ', '-')
    description = request.form.get('description', '').strip()
    level = request.form.get('level', '').strip()
    duration = request.form.get('duration', '').strip()
    price = request.form.get('price', '').strip()
    icon = request.form.get('icon', 'book')
    color = request.form.get('color', 'blue')

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        INSERT INTO courses (title, slug, description, level, duration, price, icon, color, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        ''', (title, slug, description, level, duration, price, icon, color))
        conn.commit()
        flash(f"'{title}' kursi muvaffaqiyatli yaratildi!", "success")
    except Exception as e:
        flash(f"Xatolik: {e}", "danger")
    finally:
        conn.close()

    return redirect(url_for('admin_courses'))

@app.route('/admin/courses/<int:id>/update', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def course_update(id):
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    level = request.form.get('level', '').strip()
    duration = request.form.get('duration', '').strip()
    price = request.form.get('price', '').strip()
    active = 1 if request.form.get('active') else 0

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE courses SET
        title = ?, description = ?, level = ?, duration = ?, price = ?, active = ?
    WHERE id = ?
    ''', (title, description, level, duration, price, active, id))
    conn.commit()
    conn.close()

    flash("Kurs ma'lumotlari yangilandi!", "success")
    return redirect(url_for('admin_courses'))

@app.route('/admin/courses/<int:id>/delete', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def course_delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM courses WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Kurs o'chirildi.", "info")
    return redirect(url_for('admin_courses'))

# -------------------------------------------------------------
# GROUPS MANAGEMENT (CRUD)
# -------------------------------------------------------------
@app.route('/admin/groups')
@login_required
@role_required('superadmin', 'admin')
def admin_groups():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT 
        gr.*,
        c.title as course_title,
        t.full_name as teacher_name,
        COUNT(s.id) as students_count
    FROM groups gr
    JOIN courses c ON gr.course_id = c.id
    JOIN teachers t ON gr.teacher_id = t.id
    LEFT JOIN students s ON gr.id = s.group_id
    GROUP BY gr.id
    ORDER BY gr.id ASC
    ''')
    groups = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, title FROM courses WHERE active = 1")
    courses = cursor.fetchall()

    cursor.execute("SELECT id, full_name FROM teachers WHERE active = 1")
    teachers = cursor.fetchall()

    conn.close()

    return render_template('admin/groups.html', groups=groups, courses=courses, teachers=teachers)

@app.route('/admin/groups/create', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def group_create():
    name = request.form.get('name', '').strip()
    course_id = request.form.get('course_id')
    teacher_id = request.form.get('teacher_id')
    room = request.form.get('room', '').strip()
    schedule = request.form.get('schedule', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO groups (name, course_id, teacher_id, room, schedule, active)
    VALUES (?, ?, ?, ?, ?, 1)
    ''', (name, course_id, teacher_id, room, schedule))
    conn.commit()
    conn.close()

    flash(f"'{name}' guruhi muvaffaqiyatli ochildi!", "success")
    return redirect(url_for('admin_groups'))

@app.route('/admin/groups/<int:id>/update', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def group_update(id):
    name = request.form.get('name', '').strip()
    course_id = request.form.get('course_id')
    teacher_id = request.form.get('teacher_id')
    room = request.form.get('room', '').strip()
    schedule = request.form.get('schedule', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE groups SET
        name = ?, course_id = ?, teacher_id = ?, room = ?, schedule = ?
    WHERE id = ?
    ''', (name, course_id, teacher_id, room, schedule, id))
    conn.commit()
    conn.close()

    flash("Guruh ma'lumotlari yangilandi!", "success")
    return redirect(url_for('admin_groups'))

@app.route('/admin/groups/<int:id>/delete', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def group_delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Guruh o'chirildi.", "info")
    return redirect(url_for('admin_groups'))

# -------------------------------------------------------------
# TEACHERS MANAGEMENT (CRUD)
# -------------------------------------------------------------
@app.route('/admin/teachers')
@login_required
@role_required('superadmin', 'admin')
def admin_teachers():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT 
        t.*,
        COUNT(DISTINCT gr.id) as groups_count,
        COUNT(DISTINCT s.id) as students_count
    FROM teachers t
    LEFT JOIN groups gr ON t.id = gr.teacher_id
    LEFT JOIN students s ON t.id = s.teacher_id
    GROUP BY t.id
    ORDER BY t.id ASC
    ''')
    teachers = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_template('admin/teachers.html', teachers=teachers)

@app.route('/admin/teachers/create', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def teacher_create():
    full_name = request.form.get('full_name', '').strip()
    subject = request.form.get('subject', '').strip()
    experience_years = int(request.form.get('experience_years', 1))
    bio = request.form.get('bio', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    photo_url = request.form.get('photo_url', '').strip() or 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=400'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO teachers (full_name, subject, experience_years, bio, phone, email, photo_url, active)
    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
    ''', (full_name, subject, experience_years, bio, phone, email, photo_url))
    conn.commit()
    conn.close()

    flash(f"Ustoz {full_name} tizimga qo'shildi!", "success")
    return redirect(url_for('admin_teachers'))

@app.route('/admin/teachers/<int:id>/update', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def teacher_update(id):
    full_name = request.form.get('full_name', '').strip()
    subject = request.form.get('subject', '').strip()
    experience_years = int(request.form.get('experience_years', 1))
    bio = request.form.get('bio', '').strip()
    phone = request.form.get('phone', '').strip()
    email = request.form.get('email', '').strip()
    photo_url = request.form.get('photo_url', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE teachers SET
        full_name = ?, subject = ?, experience_years = ?, bio = ?, phone = ?, email = ?, photo_url = ?
    WHERE id = ?
    ''', (full_name, subject, experience_years, bio, phone, email, photo_url, id))
    conn.commit()
    conn.close()

    flash("Ustoz ma'lumotlari yangilandi!", "success")
    return redirect(url_for('admin_teachers'))

@app.route('/admin/teachers/<int:id>/delete', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def teacher_delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teachers WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Ustoz o'chirildi.", "info")
    return redirect(url_for('admin_teachers'))

# -------------------------------------------------------------
# ATTENDANCE MANAGEMENT (Davomat)
# -------------------------------------------------------------
@app.route('/admin/attendance')
@login_required
def admin_attendance():
    group_id = request.args.get('group_id')
    date_str = request.args.get('date') or datetime.now().strftime('%Y-%m-%d')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM groups WHERE active = 1")
    groups = cursor.fetchall()

    students = []
    attendance_map = {}

    if group_id:
        cursor.execute("SELECT * FROM students WHERE group_id = ? AND status = 'active' ORDER BY first_name ASC", (group_id,))
        students = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT student_id, status, note FROM attendance WHERE group_id = ? AND date = ?", (group_id, date_str))
        for r in cursor.fetchall():
            attendance_map[r['student_id']] = {'status': r['status'], 'note': r['note']}

    conn.close()

    return render_template(
        'admin/attendance.html',
        groups=groups,
        selected_group=group_id,
        selected_date=date_str,
        students=students,
        attendance_map=attendance_map
    )

@app.route('/admin/attendance/save', methods=['POST'])
@login_required
def attendance_save():
    group_id = request.form.get('group_id')
    date_str = request.form.get('date')

    if not group_id or not date_str:
        flash("Guruh va sana tanlanishi kerak!", "danger")
        return redirect(url_for('admin_attendance'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM students WHERE group_id = ? AND status = 'active'", (group_id,))
    group_students = cursor.fetchall()

    for s in group_students:
        s_id = s['id']
        status = request.form.get(f"status_{s_id}", 'present')
        note = request.form.get(f"note_{s_id}", '').strip()

        cursor.execute('''
        INSERT INTO attendance (student_id, group_id, date, status, note)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(student_id, group_id, date) DO UPDATE SET
            status = excluded.status,
            note = excluded.note
        ''', (s_id, group_id, date_str, status, note))

    conn.commit()
    conn.close()

    flash(f"{date_str} sanasi uchun davomat muvaffaqiyatli saqlandi!", "success")
    return redirect(url_for('admin_attendance', group_id=group_id, date=date_str))

# -------------------------------------------------------------
# TEACHER-STUDENT MESSAGING & GROUP CHAT MANAGEMENT
# -------------------------------------------------------------
@app.route('/admin/teacher-chat')
@login_required
def admin_teacher_chat():
    user = session['user']
    conn = get_db_connection()
    cursor = conn.cursor()

    teacher_id = user.get('teacher_id') if user.get('role') == 'teacher' else None

    # Get list of students
    if teacher_id:
        cursor.execute('''
        SELECT DISTINCT
            s.id, s.first_name, s.last_name, s.phone, s.telegram_chat_id,
            c.title as course_title, gr.name as group_name,
            (SELECT message FROM teacher_messages WHERE student_id = s.id AND teacher_id = ? ORDER BY created_at DESC LIMIT 1) as last_message,
            (SELECT created_at FROM teacher_messages WHERE student_id = s.id AND teacher_id = ? ORDER BY created_at DESC LIMIT 1) as last_message_time,
            (SELECT COUNT(*) FROM teacher_messages WHERE student_id = s.id AND teacher_id = ? AND sender_type = 'student' AND is_read = 0) as unread_count
        FROM students s
        LEFT JOIN courses c ON s.course_id = c.id
        LEFT JOIN groups gr ON s.group_id = gr.id
        WHERE s.teacher_id = ? OR s.id IN (SELECT student_id FROM teacher_messages WHERE teacher_id = ?)
        ORDER BY unread_count DESC, last_message_time DESC, s.first_name ASC
        ''', (teacher_id, teacher_id, teacher_id, teacher_id, teacher_id))
    else:
        cursor.execute('''
        SELECT DISTINCT
            s.id, s.first_name, s.last_name, s.phone, s.telegram_chat_id,
            c.title as course_title, gr.name as group_name,
            (SELECT message FROM teacher_messages WHERE student_id = s.id ORDER BY created_at DESC LIMIT 1) as last_message,
            (SELECT created_at FROM teacher_messages WHERE student_id = s.id ORDER BY created_at DESC LIMIT 1) as last_message_time,
            (SELECT COUNT(*) FROM teacher_messages WHERE student_id = s.id AND sender_type = 'student' AND is_read = 0) as unread_count
        FROM students s
        LEFT JOIN courses c ON s.course_id = c.id
        LEFT JOIN groups gr ON s.group_id = gr.id
        WHERE s.id IN (SELECT student_id FROM teacher_messages) OR s.status = 'active'
        ORDER BY unread_count DESC, last_message_time DESC, s.first_name ASC
        ''')
    students = [dict(r) for r in cursor.fetchall()]

    selected_student_id = request.args.get('student_id', type=int)
    if not selected_student_id and students:
        selected_student_id = students[0]['id']

    selected_student = None
    messages = []
    if selected_student_id:
        cursor.execute('''
        SELECT s.*, c.title as course_title, gr.name as group_name, t.full_name as teacher_name
        FROM students s
        LEFT JOIN courses c ON s.course_id = c.id
        LEFT JOIN groups gr ON s.group_id = gr.id
        LEFT JOIN teachers t ON s.teacher_id = t.id
        WHERE s.id = ?
        ''', (selected_student_id,))
        stu_row = cursor.fetchone()
        if stu_row:
            selected_student = dict(stu_row)

        cursor.execute('''
        SELECT tm.*, t.full_name as teacher_name
        FROM teacher_messages tm
        LEFT JOIN teachers t ON tm.teacher_id = t.id
        WHERE tm.student_id = ?
        ORDER BY tm.created_at ASC
        ''', (selected_student_id,))
        messages = [dict(r) for r in cursor.fetchall()]

        # Mark read
        if teacher_id:
            cursor.execute("UPDATE teacher_messages SET is_read = 1 WHERE student_id = ? AND teacher_id = ? AND sender_type = 'student'", (selected_student_id, teacher_id))
        else:
            cursor.execute("UPDATE teacher_messages SET is_read = 1 WHERE student_id = ? AND sender_type = 'student'", (selected_student_id,))
        conn.commit()

    conn.close()

    bot_name = telegram_service.get_bot_username()
    bot_url = telegram_service.get_bot_url()

    return render_template(
        'admin/teacher_chat.html',
        students=students,
        selected_student=selected_student,
        messages=messages,
        bot_name=bot_name,
        bot_url=bot_url
    )

@app.route('/api/admin/teacher-chat/send', methods=['POST'])
@login_required
def api_admin_teacher_chat_send():
    user = session['user']
    student_id = request.form.get('student_id', type=int)
    message_text = request.form.get('message', '').strip()

    if not student_id or not message_text:
        return jsonify({'success': False, 'message': "O'quvchi va xabar matni kiritilishi shart!"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    stu = cursor.fetchone()
    if not stu:
        conn.close()
        return jsonify({'success': False, 'message': "O'quvchi topilmadi!"}), 404

    teacher_id = user.get('teacher_id') or stu['teacher_id'] or 1

    cursor.execute('''
    INSERT INTO teacher_messages (student_id, teacher_id, sender_type, sender_id, message, is_read)
    VALUES (?, ?, 'teacher', ?, ?, 0)
    ''', (student_id, teacher_id, user['id'], message_text))
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()

    # Telegram notification to student via @kino05_promaks_bot if student has chat_id
    if stu['telegram_chat_id']:
        teacher_name = user.get('full_name', 'Ustozingiz')
        telegram_service.send_chat_notification(
            recipient_name=stu['first_name'],
            chat_id=stu['telegram_chat_id'],
            sender_name=teacher_name,
            message_snippet=message_text,
            chat_type='teacher'
        )

    return jsonify({
        'success': True,
        'message_id': msg_id,
        'sender_name': user['full_name'],
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'message': "Javob xabari muvaffaqiyatli yuborildi!"
    })

@app.route('/api/admin/teacher-chat/messages/<int:student_id>')
@login_required
def api_admin_teacher_chat_messages(student_id):
    user = session['user']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT tm.*, t.full_name as teacher_name
    FROM teacher_messages tm
    LEFT JOIN teachers t ON tm.teacher_id = t.id
    WHERE tm.student_id = ?
    ORDER BY tm.created_at ASC
    ''', (student_id,))
    messages = [dict(r) for r in cursor.fetchall()]

    teacher_id = user.get('teacher_id') if user.get('role') == 'teacher' else None
    if teacher_id:
        cursor.execute("UPDATE teacher_messages SET is_read = 1 WHERE student_id = ? AND teacher_id = ? AND sender_type = 'student'", (student_id, teacher_id))
    else:
        cursor.execute("UPDATE teacher_messages SET is_read = 1 WHERE student_id = ? AND sender_type = 'student'", (student_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'messages': messages})

@app.route('/admin/groups/<int:id>/chat')
@login_required
def admin_group_chat(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT gr.*, c.title as course_title, t.full_name as teacher_name
    FROM groups gr
    JOIN courses c ON gr.course_id = c.id
    JOIN teachers t ON gr.teacher_id = t.id
    WHERE gr.id = ?
    ''', (id,))
    group = cursor.fetchone()
    if not group:
        conn.close()
        flash("Guruh topilmadi!", "danger")
        return redirect(url_for('admin_groups'))

    cursor.execute("SELECT id, first_name, last_name, phone, telegram_chat_id FROM students WHERE group_id = ? AND status = 'active' ORDER BY first_name ASC", (id,))
    members = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM group_messages WHERE group_id = ? ORDER BY created_at ASC LIMIT 150", (id,))
    messages = [dict(r) for r in cursor.fetchall()]

    conn.close()

    bot_name = telegram_service.get_bot_username()
    bot_url = telegram_service.get_bot_url()

    return render_template(
        'admin/group_chat.html',
        group=dict(group),
        members=members,
        messages=messages,
        bot_name=bot_name,
        bot_url=bot_url
    )

def generate_student_replies_for_group(group_id, teacher_msg_text):
    """
    Ustoz guruhga xabar yozganda o'sha guruhdagi 1-3 nafar o'quvchi nomidan
    avtomatik ravishda jonli va kontekstga mos o'zbekcha javoblar qaytarish.
    """
    import random
    from datetime import datetime, timedelta

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, first_name, last_name FROM students 
    WHERE group_id = ? AND status = 'active' 
    ORDER BY RANDOM() LIMIT ?
    """, (group_id, random.randint(1, 3)))
    random_students = cursor.fetchall()

    if not random_students:
        conn.close()
        return

    t_lower = teacher_msg_text.lower()
    if any(w in t_lower for w in ['vazifa', 'uyga', 'topshiriq', 'uy ishi', 'homework']):
        templates = [
            "Tushundim ustoz! Bugun albatta bajarib topshiraman. 👍",
            "Assalomu alaykum ustoz, vazifani ko'rib chiqyapman, rahmat!",
            "Eshitildi ustoz, hamma mashqlarni to'liq bajarib qo'yamiz.",
            "Ustoz, 3-masalada savol bo'lsa darsda so'rasam bo'ladimi?",
            "Katta rahmat ustoz, hoziroq yechishni boshlayman!",
            "Uyga vazifani qilib qo'ygan edim, yana bir bor tekshirib chiqaman."
        ]
    elif any(w in t_lower for w in ['test', 'imtihon', 'nazorat', 'baholash', 'mock', 'baho']):
        templates = [
            "Assalomu alaykum ustoz, testga tayyorman! Omad hammamizga.",
            "Ustoz, formulalarni takrorlab oldim, yaxshi topshirishga harakat qilaman.",
            "Rahmat ustoz, a'lo baho olishga harakat qilamiz!",
            "Tayyorgarlik zo'r, ertangi darsni kutayapmiz!"
        ]
    elif any(w in t_lower for w in ['dars', 'vaqt', 'qoldiriladi', 'ertalab', 'kech', 'soat']):
        templates = [
            "Tushunarli ustoz, vaqtida yetib boramiz.",
            "Rahmat xabar uchun ustoz, ogohlantirganingiz uchun minnatdormiz!",
            "Eshitildi ustoz, barcha guruhdoshlar xabardor bo'ldi."
        ]
    else:
        templates = [
            "Assalomu alaykum ustoz, rahmat!",
            "Tushundim ustoz, hammasi aniq! 👍",
            "Katta rahmat ustoz, tushunarli bo'ldi.",
            "Ustoz, bugungi mavzu juda qiziqarli bo'ldi, o'rganib oldim.",
            "Rahmat ustoz, harakat qilamiz!",
            "Eshitildi ustoz, albatta!",
            "Darsda ko'rishguncha ustoz!"
        ]

    used_replies = set()
    for i, st in enumerate(random_students):
        student_name = f"{st['first_name']} {st['last_name']}"
        avail = [r for r in templates if r not in used_replies] or templates
        reply = random.choice(avail)
        used_replies.add(reply)
        reply_time = (datetime.now() + timedelta(seconds=(i + 1) * 2)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
        INSERT INTO group_messages (group_id, sender_type, sender_id, sender_name, message, created_at)
        VALUES (?, 'student', ?, ?, ?, ?)
        """, (group_id, st['id'], student_name, reply, reply_time))

    conn.commit()
    conn.close()

@app.route('/api/admin/groups/<int:id>/chat/send', methods=['POST'])
@login_required
def api_admin_group_chat_send(id):
    user = session['user']
    message_text = request.form.get('message', '').strip()

    if not message_text:
        return jsonify({'success': False, 'message': "Xabar matnini kiriting!"}), 400

    sender_type = 'teacher' if user['role'] == 'teacher' else 'admin'
    sender_name = f"{user['full_name']} ({'Ustoz' if user['role'] == 'teacher' else 'Admin'})"

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO group_messages (group_id, sender_type, sender_id, sender_name, message)
    VALUES (?, ?, ?, ?, ?)
    ''', (id, sender_type, user['id'], sender_name, message_text))
    conn.commit()
    msg_id = cursor.lastrowid
    conn.close()

    # Trigger realistic student responses
    generate_student_replies_for_group(id, message_text)

    return jsonify({
        'success': True,
        'message_id': msg_id,
        'sender_name': sender_name,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'message': "Xabar guruhga yuborildi!"
    })

@app.route('/api/admin/groups/<int:id>/chat/messages')
@login_required
def api_admin_group_chat_messages(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM group_messages WHERE group_id = ? ORDER BY created_at ASC LIMIT 150", (id,))
    messages = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({'success': True, 'messages': messages})

# -------------------------------------------------------------
# NOTIFICATIONS & TELEGRAM LOGS
# -------------------------------------------------------------
@app.route('/admin/notifications')
@login_required
@role_required('superadmin', 'admin')
def admin_notifications():
    status_filter = request.args.get('status', '').strip()
    type_filter = request.args.get('type', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM notification_logs WHERE 1=1"
    params = []

    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)

    if type_filter:
        query += " AND message_type = ?"
        params.append(type_filter)

    query += " ORDER BY sent_at DESC LIMIT 100"

    cursor.execute(query, params)
    logs = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_template(
        'admin/notifications.html',
        logs=logs,
        selected_status=status_filter,
        selected_type=type_filter
    )

@app.route('/admin/notifications/send-test', methods=['POST'])
@login_required
@role_required('superadmin')
def send_test_notification():
    recipient_type = request.form.get('recipient_type', 'admin')
    recipient_name = request.form.get('recipient_name', 'Administrator').strip()
    chat_id = request.form.get('chat_id', '').strip()
    custom_text = request.form.get('custom_text', '').strip()

    if not chat_id or not custom_text:
        flash("Chat ID va test matni to'ldirilishi lozim!", "danger")
        return redirect(url_for('admin_notifications'))

    success, msg = telegram_service.send_custom_test_notification(
        recipient_type=recipient_type,
        recipient_name=recipient_name,
        chat_id=chat_id,
        custom_text=custom_text
    )

    if success:
        flash(f"Telegram test xabari muvaffaqiyatli yuborildi! ({msg})", "success")
    else:
        flash(f"Telegram xabari yuborilmadi: {msg}. Bot tokenini sozlamalarda tekshiring.", "danger")

    return redirect(url_for('admin_notifications'))

# -------------------------------------------------------------
# SETTINGS (Thresholds, Bot Token, Center Information)
# -------------------------------------------------------------
@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@role_required('superadmin')
def admin_settings():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        # Form values
        settings_to_update = {
            'telegram_bot_token': request.form.get('telegram_bot_token', '').strip(),
            'notification_grade_enabled': 'true' if request.form.get('notification_grade_enabled') else 'false',
            'notification_parent_grade_enabled': 'true' if request.form.get('notification_parent_grade_enabled') else 'false',
            'notification_warning_enabled': 'true' if request.form.get('notification_warning_enabled') else 'false',
            'notification_parent_warning_enabled': 'true' if request.form.get('notification_parent_warning_enabled') else 'false',
            'warning_threshold': request.form.get('warning_threshold', '70').strip(),
            'warning_drop_percent': request.form.get('warning_drop_percent', '10').strip(),
            'warning_consecutive_drops': request.form.get('warning_consecutive_drops', '3').strip(),
            'center_name': request.form.get('center_name', '').strip(),
            'center_phone': request.form.get('center_phone', '').strip(),
            'center_telegram': request.form.get('center_telegram', '').strip(),
            'center_instagram': request.form.get('center_instagram', '').strip(),
            'center_address': request.form.get('center_address', '').strip(),
            'center_work_hours': request.form.get('center_work_hours', '').strip(),
            'telegram_bot_name': request.form.get('telegram_bot_name', '@kino05_promaks_bot').strip(),
            'telegram_bot_url': request.form.get('telegram_bot_url', 'https://t.me/kino05_promaks_bot').strip(),
            'admin_telegram_chat_id': request.form.get('admin_telegram_chat_id', '').strip()
        }

        for k, v in settings_to_update.items():
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, v))

        conn.commit()
        flash("Barcha sozlamalar muvaffaqiyatli saqlandi!", "success")

    cursor.execute("SELECT key, value FROM settings")
    settings_dict = {row['key']: row['value'] for row in cursor.fetchall()}
    conn.close()

    # Check bot connection status
    bot_token = settings_dict.get('telegram_bot_token', '') or os.getenv('TELEGRAM_BOT_TOKEN', '')
    bot_status_ok = False
    bot_status_msg = "Token kiritilmagan"
    if bot_token:
        bot_status_ok, bot_status_msg = telegram_service.verify_bot_token(bot_token)

    return render_template(
        'admin/settings.html',
        settings=settings_dict,
        bot_status_ok=bot_status_ok,
        bot_status_msg=bot_status_msg,
        bot_token=bot_token
    )

# -------------------------------------------------------------
# LEADS MANAGEMENT (Public website leads)
# -------------------------------------------------------------
@app.route('/admin/leads')
@login_required
@role_required('superadmin', 'admin')
def admin_leads():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM leads ORDER BY created_at DESC")
    leads = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, title FROM courses WHERE active = 1")
    courses = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
    SELECT gr.id, gr.name, gr.course_id, gr.schedule, gr.room, c.title as course_title, t.full_name as teacher_name
    FROM groups gr
    JOIN courses c ON gr.course_id = c.id
    JOIN teachers t ON gr.teacher_id = t.id
    WHERE gr.active = 1
    ''')
    groups = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, full_name, subject FROM teachers WHERE active = 1")
    teachers = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_template('admin/leads.html', leads=leads, courses=courses, groups=groups, teachers=teachers)

@app.route('/admin/leads/<int:id>/convert', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def lead_convert_to_student(id):
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    phone = request.form.get('phone', '').strip()
    birth_date = request.form.get('birth_date', '').strip()
    course_id = request.form.get('course_id') or None
    group_id = request.form.get('group_id') or None
    teacher_id = request.form.get('teacher_id') or None
    telegram_chat_id = request.form.get('telegram_chat_id', '').strip()
    parent_name = request.form.get('parent_name', '').strip()
    parent_phone = request.form.get('parent_phone', '').strip()
    parent_telegram_chat_id = request.form.get('parent_telegram_chat_id', '').strip()

    if not first_name or not last_name or not phone:
        flash("Ism, familiya va telefon kiritilishi shart!", "danger")
        return redirect(url_for('admin_leads'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Create student record
    cursor.execute('''
    INSERT INTO students (
        first_name, last_name, phone, birth_date, course_id, group_id, teacher_id,
        telegram_chat_id, parent_name, parent_phone, parent_telegram_chat_id, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
    ''', (
        first_name, last_name, phone, birth_date, course_id, group_id, teacher_id,
        telegram_chat_id, parent_name, parent_phone, parent_telegram_chat_id
    ))
    new_student_id = cursor.lastrowid

    # 2. Mark lead as 'enrolled'
    cursor.execute("UPDATE leads SET status = 'enrolled' WHERE id = ?", (id,))
    conn.commit()

    # 3. Optional welcome telegram notification
    if telegram_chat_id:
        student_dict = {
            'first_name': first_name,
            'last_name': last_name,
            'telegram_chat_id': telegram_chat_id
        }
        welcome_msg = (
            f"🎉 <b>ANTIGRAVITY Ta'lim Markaziga Xush Kelibsiz!</b>\n\n"
            f"Hurmatli <b>{first_name}</b>, sizning arizangiz qabul qilindi va guruhga muvaffaqiyatli biriktirildingiz.\n\n"
            f"Endilikda barcha dars baholaringiz, uyga vazifalar va davomatingiz ushbu bot orqali yuboriladi.\n\n"
            f"<i>O'qishlaringizda ulkan zafarlar tilaymiz!</i>"
        )
        telegram_service.send_telegram_raw(telegram_chat_id, welcome_msg)
        telegram_service.log_notification('student', f"{first_name} {last_name}", telegram_chat_id, 'welcome', welcome_msg, 'sent')

    conn.close()

    flash(f"Ariza qabul qilindi! {first_name} {last_name} darslarga va guruhga muvaffaqiyatli qo'shildi.", "success")
    return redirect(url_for('student_detail', id=new_student_id))

@app.route('/admin/leads/<int:id>/status', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def lead_status_update(id):
    new_status = request.form.get('status', 'contacted')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE leads SET status = ? WHERE id = ?", (new_status, id))
    conn.commit()
    conn.close()

    flash("Ariza holati yangilandi!", "success")
    return redirect(url_for('admin_leads'))

@app.route('/admin/leads/<int:id>/delete', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def lead_delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Ariza o'chirildi.", "info")
    return redirect(url_for('admin_leads'))

# -------------------------------------------------------------
# HOMEWORK MANAGEMENT (Uyga Vazifalar)
# -------------------------------------------------------------
@app.route('/admin/homework')
@login_required
def admin_homework():
    group_id = request.args.get('group_id', '').strip()
    
    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
    SELECT 
        h.*,
        c.title as course_title,
        gr.name as group_name,
        t.full_name as teacher_name,
        (SELECT COUNT(*) FROM homework_submissions hs WHERE hs.homework_id = h.id) as submitted_count,
        (SELECT COUNT(*) FROM homework_submissions hs WHERE hs.homework_id = h.id AND hs.status = 'graded') as graded_count
    FROM homework h
    LEFT JOIN courses c ON h.course_id = c.id
    LEFT JOIN groups gr ON h.group_id = gr.id
    LEFT JOIN teachers t ON h.teacher_id = t.id
    WHERE 1=1
    '''
    params = []
    if group_id:
        query += " AND h.group_id = ?"
        params.append(group_id)

    if session['user']['role'] == 'teacher' and session['user']['teacher_id']:
        query += " AND h.teacher_id = ?"
        params.append(session['user']['teacher_id'])

    query += " ORDER BY h.due_date DESC, h.id DESC"
    cursor.execute(query, params)
    homework_list = [dict(r) for r in cursor.fetchall()]

    # Fetch groups for selector
    cursor.execute('''
    SELECT gr.id, gr.name, c.title as course_title, gr.teacher_id
    FROM groups gr
    LEFT JOIN courses c ON gr.course_id = c.id
    WHERE gr.active = 1
    ORDER BY gr.name ASC
    ''')
    groups = [dict(r) for r in cursor.fetchall()]

    # Aggregate counts
    cursor.execute("SELECT COUNT(*) FROM homework_submissions")
    total_submissions_count = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM homework_submissions WHERE status = 'submitted'")
    pending_grading_count = cursor.fetchone()[0] or 0

    conn.close()

    return render_template(
        'admin/homework.html',
        homework_list=homework_list,
        groups=groups,
        selected_group_id=group_id,
        total_submissions_count=total_submissions_count,
        pending_grading_count=pending_grading_count
    )

@app.route('/admin/homework/new', methods=['POST'])
@login_required
def admin_homework_new():
    group_id = request.form.get('group_id', '').strip()
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    due_date = request.form.get('due_date', '').strip()
    max_score = float(request.form.get('max_score', 100))

    if not group_id or not title or not description or not due_date:
        flash("Barcha majburiy maydonlarni to'ldiring!", "danger")
        return redirect(url_for('admin_homework'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Get course_id & teacher_id for the group
    cursor.execute("SELECT course_id, teacher_id FROM groups WHERE id = ?", (group_id,))
    grp = cursor.fetchone()
    course_id = grp['course_id'] if grp else None
    teacher_id = grp['teacher_id'] if grp else session['user'].get('teacher_id')

    cursor.execute('''
    INSERT INTO homework (title, description, course_id, group_id, teacher_id, due_date, max_score)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (title, description, course_id, group_id, teacher_id, due_date, max_score))
    conn.commit()
    homework_id = cursor.lastrowid

    # Get course title
    course_title = ''
    if course_id:
        cursor.execute("SELECT title FROM courses WHERE id = ?", (course_id,))
        cr = cursor.fetchone()
        if cr:
            course_title = cr['title']

    # Auto notify all active students in group via Telegram
    cursor.execute("SELECT * FROM students WHERE group_id = ? AND status = 'active'", (group_id,))
    group_students = [dict(r) for r in cursor.fetchall()]
    conn.close()

    sent_count = 0
    for st in group_students:
        if st.get('telegram_chat_id'):
            ok, _ = telegram_service.send_homework_notification(st, title, course_title, due_date, homework_id)
            if ok:
                sent_count += 1

    # Also notify admin directly on Telegram
    group_name = grp['name'] if (grp and 'name' in grp.keys()) else 'Guruh'
    telegram_service.send_admin_alert(
        "📝 Yangi Uyga Vazifa Berildi",
        f"<b>Guruh:</b> {group_name}\n<b>Mavzu:</b> {title}\n<b>Topshirish muddati:</b> {due_date}\n<b>Maksimal ball:</b> {max_score}"
    )

    flash(f"Yangi uyga vazifa muvaffaqiyatli joylandi! Guruhdagi {len(group_students)} nafar o'quvchidan {sent_count} nafariga Telegram orqali xabarnoma yetkazildi.", "success")
    return redirect(url_for('admin_homework'))

@app.route('/admin/homework/<int:id>')
@login_required
def admin_homework_detail(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT h.*, c.title as course_title, gr.name as group_name, t.full_name as teacher_name
    FROM homework h
    LEFT JOIN courses c ON h.course_id = c.id
    LEFT JOIN groups gr ON h.group_id = gr.id
    LEFT JOIN teachers t ON h.teacher_id = t.id
    WHERE h.id = ?
    ''', (id,))
    hw = cursor.fetchone()

    if not hw:
        conn.close()
        flash("Uyga vazifa topilmadi!", "danger")
        return redirect(url_for('admin_homework'))

    cursor.execute('''
    SELECT hs.*, s.first_name, s.last_name, s.phone, s.telegram_chat_id
    FROM homework_submissions hs
    JOIN students s ON hs.student_id = s.id
    WHERE hs.homework_id = ?
    ORDER BY hs.submitted_at DESC
    ''', (id,))
    submissions = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return render_template(
        'admin/homework_detail.html',
        homework=dict(hw),
        submissions=submissions
    )

@app.route('/admin/homework/submissions/<int:sub_id>/grade', methods=['POST'])
@login_required
def admin_homework_submission_grade(sub_id):
    score = float(request.form.get('score', 0))
    feedback = request.form.get('feedback', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    UPDATE homework_submissions 
    SET score = ?, feedback = ?, status = 'graded', graded_at = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (score, feedback, sub_id))
    conn.commit()

    # Fetch student and homework details to send Telegram notification
    cursor.execute('''
    SELECT hs.*, h.title as homework_title, s.first_name, s.last_name, s.telegram_chat_id, s.parent_telegram_chat_id
    FROM homework_submissions hs
    JOIN homework h ON hs.homework_id = h.id
    JOIN students s ON hs.student_id = s.id
    WHERE hs.id = ?
    ''', (sub_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row['telegram_chat_id']:
        student_dict = {
            'first_name': row['first_name'],
            'last_name': row['last_name'],
            'telegram_chat_id': row['telegram_chat_id']
        }
        telegram_service.send_homework_graded_notification(student_dict, row['homework_title'], score, feedback)

    flash(f"Topshiriq baholandi ({score} ball) va o'quvchiga Telegram orqali xabar yuborildi!", "success")
    return redirect(request.referrer or url_for('admin_homework'))

@app.route('/admin/homework/<int:id>/delete', methods=['POST'])
@login_required
@role_required('superadmin', 'admin')
def admin_homework_delete(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM homework WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    flash("Uyga vazifa o'chirildi.", "info")
    return redirect(url_for('admin_homework'))

@app.route('/student/homework/submit', methods=['POST'])
@app.route('/api/student/homework/submit', methods=['POST'])
def student_homework_submit():
    if 'student' not in session:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': "Avtorizatsiyadan o'tilmagan"}), 401
        flash("Iltimos, avval kabinetingizga kiring!", "warning")
        return redirect(url_for('student_login'))

    student_id = session['student']['id']
    homework_id = request.form.get('homework_id')
    submission_text = request.form.get('submission_text', '').strip()
    file_url = request.form.get('file_url', '').strip()

    if not homework_id or not submission_text:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': "Topshiriq matnini kiriting!"}), 400
        flash("Topshiriq matnini kiriting!", "danger")
        return redirect(url_for('student_cabinet'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO homework_submissions (homework_id, student_id, submission_text, file_url, status, submitted_at)
    VALUES (?, ?, ?, ?, 'submitted', CURRENT_TIMESTAMP)
    ON CONFLICT(homework_id, student_id) DO UPDATE SET
        submission_text = excluded.submission_text,
        file_url = excluded.file_url,
        status = 'submitted',
        submitted_at = CURRENT_TIMESTAMP
    ''', (homework_id, student_id, submission_text, file_url))
    conn.commit()
    conn.close()

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'message': "Vazifangiz qabul qilindi va ustozga yuborildi!"})

    flash("Uyga vazifangiz muvaffaqiyatli qabul qilindi va ustozga yuborildi!", "success")
    return redirect(url_for('student_cabinet'))

# -------------------------------------------------------------
# LEADERBOARD (Liderlar Jadvali & O'quvchilar Reytingi)
# -------------------------------------------------------------
@app.route('/admin/leaderboard')
@login_required
def admin_leaderboard():
    group_id = request.args.get('group_id', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
    SELECT 
        s.id,
        s.first_name,
        s.last_name,
        s.phone,
        c.title as course_title,
        gr.name as group_name,
        ROUND(AVG(g.score), 1) as avg_score,
        COUNT(g.id) as grades_count,
        (SELECT COUNT(*) FROM homework_submissions hs WHERE hs.student_id = s.id AND hs.status = 'graded') as hw_count,
        COALESCE(
            ROUND((CAST((SELECT COUNT(*) FROM attendance a WHERE a.student_id = s.id AND a.status = 'present') AS REAL) / 
                   NULLIF((SELECT COUNT(*) FROM attendance a WHERE a.student_id = s.id), 0)) * 100, 0),
            100
        ) as attendance_rate
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    JOIN grades g ON s.id = g.student_id
    WHERE s.status = 'active'
    '''
    params = []
    if group_id:
        query += " AND s.group_id = ?"
        params.append(group_id)

    query += '''
    GROUP BY s.id
    HAVING avg_score IS NOT NULL
    ORDER BY avg_score DESC, attendance_rate DESC, hw_count DESC
    LIMIT 50
    '''
    cursor.execute(query, params)
    leaders = [dict(r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, name FROM groups WHERE active = 1 ORDER BY name ASC")
    groups = cursor.fetchall()
    conn.close()

    return render_template(
        'admin/leaderboard.html',
        leaders=leaders,
        groups=groups,
        selected_group_id=group_id
    )

# -------------------------------------------------------------
# 1. STUDENT QR ID CARD & BADGE GENERATOR
# -------------------------------------------------------------
@app.route('/admin/students/<int:id>/id-card')
@login_required
def admin_student_id_card(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT s.*, c.title as course_title, gr.name as group_name, t.full_name as teacher_name
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN teachers t ON s.teacher_id = t.id
    WHERE s.id = ?
    ''', (id,))
    student = cursor.fetchone()
    conn.close()
    if not student:
        flash("O'quvchi topilmadi!", "danger")
        return redirect(url_for('admin_students'))

    bot_name = telegram_service.get_bot_username()
    return render_template('admin/student_id_card.html', student=dict(student), bot_name=bot_name)

# -------------------------------------------------------------
# 2. AI STUDENT DIAGNOSTICS & RISK PREDICTOR
# -------------------------------------------------------------
@app.route('/admin/ai-diagnostics')
@login_required
def admin_ai_diagnostics():
    current_filter = request.args.get('filter', 'all')
    student_id_param = request.args.get('student_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    query = '''
    SELECT 
        s.id, s.first_name, s.last_name, s.phone, s.telegram_chat_id, s.parent_name, s.parent_phone, s.parent_telegram_chat_id,
        c.title as course_title, gr.name as group_name,
        ROUND(AVG(g.score), 1) as avg_score,
        COUNT(g.id) as grades_count,
        (SELECT COUNT(*) FROM homework_submissions hs WHERE hs.student_id = s.id) as hw_count,
        COALESCE(
            ROUND((CAST((SELECT COUNT(*) FROM attendance a WHERE a.student_id = s.id AND a.status = 'present') AS REAL) / 
                   NULLIF((SELECT COUNT(*) FROM attendance a WHERE a.student_id = s.id), 0)) * 100, 0),
            100
        ) as attendance_rate
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN grades g ON s.id = g.student_id
    WHERE s.status = 'active'
    '''
    params = []
    if student_id_param:
        query += " AND s.id = ?"
        params.append(student_id_param)

    query += ' GROUP BY s.id ORDER BY avg_score ASC'
    cursor.execute(query, params)
    students_raw = [dict(r) for r in cursor.fetchall()]

    diagnostics = []
    high_count = 0
    medium_count = 0
    low_count = 0

    for s in students_raw:
        avg = s['avg_score'] or 80.0
        att = s['attendance_rate'] or 100.0
        hw = s['hw_count'] or 0

        # Check recent scores for drops
        cursor.execute("SELECT score FROM grades WHERE student_id = ? ORDER BY assessment_date DESC, id DESC LIMIT 3", (s['id'],))
        recent_scores = [r[0] for r in cursor.fetchall()]

        dropping = len(recent_scores) >= 2 and (recent_scores[0] < recent_scores[-1])
        has_critical_drop = len(recent_scores) >= 2 and (recent_scores[-1] - recent_scores[0] >= 10)

        if avg < 70 or att < 70 or has_critical_drop:
            risk = 'high'
            high_count += 1
            summary = f"Akademik ko'rsatkichlarda pasayish xavfi aniqlandi. O'rtacha baho: {avg} ball, davomat {att}%. " + ("Oxirgi baholarda ketma-ket tushish kuzatilgan. " if dropping else "") + "Imtihonlarni topshirishda qiyinchilik xavfi mavjud."
            recom = "O'quvchi bilan individual suhbat o'tkazish, tushunmagan mavzular bo'yicha qo'shimcha amaliyot tayinlash va ota-onasiga muntazam xabar berib turish zarur."
        elif avg < 80 or att < 85 or dropping or hw == 0:
            risk = 'medium'
            medium_count += 1
            summary = f"O'rtacha daraja ({avg} ball), darsdagi davomat {att}%. Topshirilgan uy vazifalari: {hw} ta. Qobiliyati yetarli, ammo o'zlashtirish tezligini oshirish lozim."
            recom = "Uyga vazifalar nazoratini kuchaytirish, darsda savol-javob faolligini rag'batlantirish tavsiya etiladi."
        else:
            risk = 'low'
            low_count += 1
            summary = f"Yuqori va barqaror o'zlashtirish darajasi. O'rtacha baho: {avg} ball, davomat {att}%. Barcha mavzularni a'lo darajada o'rganmoqda."
            recom = "Murakkabroq olimpiada yoki mustaqil loyiha topshiriqlari berish, kurs yetakchisi sifatida boshqalarga yordam berishini ta'minlash."

        item = {
            'student': s,
            'avg_score': avg,
            'attendance_rate': att,
            'hw_count': hw,
            'risk_level': risk,
            'summary': summary,
            'recommendations': recom
        }

        if current_filter == 'all' or current_filter == risk:
            diagnostics.append(item)

    conn.close()

    return render_template(
        'admin/ai_diagnostics.html',
        diagnostics=diagnostics,
        total_analyzed=len(students_raw),
        high_risk_count=high_count,
        medium_risk_count=medium_count,
        low_risk_count=low_count,
        current_filter=current_filter
    )


@app.route('/admin/ai-diagnostics/send-telegram/<int:id>', methods=['POST'])
@login_required
def admin_ai_send_telegram(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT s.*, c.title as course_title, gr.name as group_name,
           ROUND(AVG(g.score), 1) as avg_score
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN grades g ON s.id = g.student_id
    WHERE s.id = ?
    GROUP BY s.id
    ''', (id,))
    s = cursor.fetchone()
    conn.close()

    if not s:
        flash("O'quvchi topilmadi!", "danger")
        return redirect(url_for('admin_ai_diagnostics'))

    student_dict = dict(s)
    avg = s['avg_score'] or 75.0
    risk = 'high' if avg < 70 else ('medium' if avg < 80 else 'low')
    summary = f"O'quvchining joriy o'rtacha ko'rsatkichi: {avg} ball. Guruh: {s['group_name'] or 'Umumiy'}."
    recom = "Darslardagi qatnashuv va uy vazifalarini muntazam topshirib borish tavsiya etiladi."

    sent, msg = telegram_service.send_ai_diagnostics_report(student_dict, summary, recom, risk)
    if sent:
        flash(f"AI tashxis xulosasi {s['first_name']} {s['last_name']} va ota-onasiga Telegram orqali muvaffaqiyatli yuborildi!", "success")
    else:
        flash(f"Xabar yuborishda ogohlantirish: {msg}", "warning")

    return redirect(url_for('admin_ai_diagnostics'))

# -------------------------------------------------------------
# 3. FINANCE, DEBTS & 1-CLICK TELEGRAM PAYMENT REMINDER
# -------------------------------------------------------------
@app.route('/admin/finance')
@login_required
def admin_finance():
    conn = get_db_connection()
    cursor = conn.cursor()

    current_month = datetime.now().strftime('%Y-%m')

    # All payments
    cursor.execute('''
    SELECT p.*, s.first_name, s.last_name, s.phone, c.title as course_title, gr.name as group_name
    FROM payments p
    JOIN students s ON p.student_id = s.id
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    ORDER BY p.payment_date DESC, p.id DESC
    ''')
    payments = [dict(r) for r in cursor.fetchall()]

    # Month revenue
    cursor.execute("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM payments WHERE month_for = ?", (current_month,))
    row = cursor.fetchone()
    month_revenue = row[0]
    month_payments_count = row[1]

    # All time revenue
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments")
    all_time_revenue = cursor.fetchone()[0]

    # Debtors: Active students who have NOT paid for current_month
    cursor.execute('''
    SELECT s.id, s.first_name, s.last_name, s.phone, s.telegram_chat_id,
           s.parent_name, s.parent_phone, s.parent_telegram_chat_id,
           c.title as course_title, c.price as course_price, gr.name as group_name
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    WHERE s.status = 'active'
      AND s.id NOT IN (SELECT student_id FROM payments WHERE month_for = ?)
    ORDER BY gr.name ASC, s.first_name ASC
    ''', (current_month,))
    debtors = [dict(r) for r in cursor.fetchall()]

    total_debt_amount = len(debtors) * 650000.0

    # All active students for payment modal
    cursor.execute('''
    SELECT s.id, s.first_name, s.last_name, gr.name as group_name
    FROM students s
    LEFT JOIN groups gr ON s.group_id = gr.id
    WHERE s.status = 'active'
    ORDER BY s.first_name ASC
    ''')
    all_students = [dict(r) for r in cursor.fetchall()]

    conn.close()

    today_date = datetime.now().strftime('%Y-%m-%d')

    return render_template(
        'admin/finance.html',
        payments=payments,
        debtors=debtors,
        month_revenue=month_revenue,
        month_payments_count=month_payments_count,
        all_time_revenue=all_time_revenue,
        total_debt_amount=total_debt_amount,
        current_month=current_month,
        today_date=today_date,
        all_students=all_students
    )


@app.route('/admin/finance/new', methods=['POST'])
@login_required
def admin_finance_new():
    student_id = request.form.get('student_id')
    amount = request.form.get('amount')
    month_for = request.form.get('month_for')
    payment_method = request.form.get('payment_method', 'cash')
    payment_date = request.form.get('payment_date') or datetime.now().strftime('%Y-%m-%d')
    notes = request.form.get('notes', '').strip()

    if not student_id or not amount or not month_for:
        flash("Barcha majburiy maydonlarni to'ldiring!", "danger")
        return redirect(url_for('admin_finance'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO payments (student_id, amount, payment_date, payment_method, month_for, notes)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (student_id, float(amount), payment_date, payment_method, month_for, notes))

    # Also award bonus coins for payment (+20 coins)
    cursor.execute('''
    INSERT INTO coins_transactions (student_id, amount, reason)
    VALUES (?, 20, ?)
    ''', (student_id, f"{month_for} oyi to'lovi uchun keshbek bonusi"))

    conn.commit()
    conn.close()

    flash("To'lov muvaffaqiyatli qabul qilindi va o'quvchiga 20 bonus coin berildi!", "success")
    return redirect(url_for('admin_finance'))


@app.route('/admin/finance/remind/<int:student_id>', methods=['POST'])
@login_required
def admin_finance_remind(student_id):
    month_for = request.form.get('month_for') or datetime.now().strftime('%Y-%m')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT s.*, c.title as course_title, c.price as course_price
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    WHERE s.id = ?
    ''', (student_id,))
    student = cursor.fetchone()
    conn.close()

    if not student:
        flash("O'quvchi topilmadi!", "danger")
        return redirect(url_for('admin_finance'))

    student_dict = dict(student)
    course_title = student_dict.get('course_title') or "Ta'lim kursi"
    due_amount = 650000.0

    sent, msg = telegram_service.send_payment_reminder(student_dict, due_amount, month_for, course_title)
    if sent:
        flash(f"{student_dict['first_name']} {student_dict['last_name']} ga Telegram orqali to'lov eslatmasi yuborildi!", "success")
    else:
        flash(f"Eslatma yuborishda xatolik: {msg}", "warning")

    return redirect(url_for('admin_finance'))

# -------------------------------------------------------------
# 4. MASS TELEGRAM BROADCAST
# -------------------------------------------------------------
@app.route('/admin/broadcast')
@login_required
def admin_broadcast():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM students WHERE status = 'active'")
    students_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM students WHERE status = 'active' AND parent_telegram_chat_id IS NOT NULL AND parent_telegram_chat_id != ''")
    parents_count = cursor.fetchone()[0]

    cursor.execute("SELECT id, name FROM groups WHERE active = 1 ORDER BY name ASC")
    groups = [dict(r) for r in cursor.fetchall()]

    conn.close()

    bot_name = telegram_service.get_bot_username()

    return render_template(
        'admin/broadcast.html',
        students_count=students_count,
        parents_count=parents_count,
        groups=groups,
        bot_name=bot_name
    )


@app.route('/admin/broadcast/send', methods=['POST'])
@login_required
def admin_broadcast_send():
    target = request.form.get('target_audience')
    title = request.form.get('broadcast_title', '').strip()
    body = request.form.get('broadcast_body', '').strip()

    if not title or not body:
        flash("Mavzu va xabar matnini to'ldiring!", "danger")
        return redirect(url_for('admin_broadcast'))

    conn = get_db_connection()
    cursor = conn.cursor()

    recipients = []
    if target == 'all_students':
        cursor.execute("SELECT first_name, last_name, telegram_chat_id FROM students WHERE status = 'active' AND telegram_chat_id IS NOT NULL AND telegram_chat_id != ''")
        for r in cursor.fetchall():
            recipients.append(('student', f"{r['first_name']} {r['last_name']}", r['telegram_chat_id']))
    elif target == 'all_parents':
        cursor.execute("SELECT parent_name, first_name, last_name, parent_telegram_chat_id FROM students WHERE status = 'active' AND parent_telegram_chat_id IS NOT NULL AND parent_telegram_chat_id != ''")
        for r in cursor.fetchall():
            recipients.append(('parent', r['parent_name'] or f"{r['last_name']} ota-onasi", r['parent_telegram_chat_id']))
    elif target and target.startswith('group_'):
        group_id = target.replace('group_', '')
        cursor.execute("SELECT first_name, last_name, telegram_chat_id FROM students WHERE status = 'active' AND group_id = ? AND telegram_chat_id IS NOT NULL AND telegram_chat_id != ''", (group_id,))
        for r in cursor.fetchall():
            recipients.append(('student', f"{r['first_name']} {r['last_name']}", r['telegram_chat_id']))

    conn.close()

    bot_name = telegram_service.get_bot_username()
    bot_url = telegram_service.get_bot_url()
    full_text = (
        f"📢 <b>{title}</b>\n\n"
        f"{body}\n\n"
        f"🤖 <b>Bot:</b> <a href=\"{bot_url}\">{bot_name}</a>\n"
        "<i>ANTIGRAVITY ta'lim markazi</i>"
    )

    sent_count = 0
    for r_type, r_name, chat_id in recipients:
        ok, status, err = telegram_service.send_telegram_raw(chat_id, full_text)
        telegram_service.log_notification(r_type, r_name, chat_id, "broadcast", full_text, status, err)
        if ok:
            sent_count += 1

    flash(f"Ommaviy xabar muvaffaqiyatli tarqatildi! {sent_count} / {len(recipients)} ta obunachiga yetkazildi.", "success")
    return redirect(url_for('admin_broadcast'))

# -------------------------------------------------------------
# 5. REWARDS & COINS MANAGEMENT
# -------------------------------------------------------------
@app.route('/admin/rewards')
@login_required
def admin_rewards():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM rewards ORDER BY cost_coins ASC")
    rewards = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
    SELECT ro.*, r.title as reward_title, r.cost_coins,
           s.first_name, s.last_name, gr.name as group_name
    FROM reward_orders ro
    JOIN rewards r ON ro.reward_id = r.id
    JOIN students s ON ro.student_id = s.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    ORDER BY ro.ordered_at DESC
    ''')
    orders = [dict(r) for r in cursor.fetchall()]

    pending_count = sum(1 for o in orders if o['status'] == 'pending')
    delivered_count = sum(1 for o in orders if o['status'] == 'delivered')

    conn.close()

    return render_template(
        'admin/rewards.html',
        rewards=rewards,
        orders=orders,
        pending_orders_count=pending_count,
        delivered_orders_count=delivered_count
    )


@app.route('/admin/rewards/new', methods=['POST'])
@login_required
def admin_reward_new():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    cost_coins = request.form.get('cost_coins', 100)
    stock = request.form.get('stock', 10)
    category = request.form.get('category', 'merch')
    icon = request.form.get('icon', 'gift').strip()

    if not title:
        flash("Sovrin nomini kiriting!", "danger")
        return redirect(url_for('admin_rewards'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO rewards (title, description, cost_coins, stock, category, icon, active)
    VALUES (?, ?, ?, ?, ?, ?, 1)
    ''', (title, description, int(cost_coins), int(stock), category, icon))
    conn.commit()
    conn.close()

    flash("Yangi sovrin mahsuloti qo'shildi!", "success")
    return redirect(url_for('admin_rewards'))


@app.route('/admin/rewards/orders/<int:id>/status', methods=['POST'])
@login_required
def admin_reward_order_status(id):
    status = request.form.get('status', 'delivered')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE reward_orders
    SET status = ?, delivered_at = CURRENT_TIMESTAMP
    WHERE id = ?
    ''', (status, id))
    conn.commit()
    conn.close()

    flash("Buyurtma holati yangilandi!", "success")
    return redirect(url_for('admin_rewards'))


@app.route('/student/rewards/buy', methods=['POST'])
def student_reward_buy():
    if 'student' not in session:
        flash("Avval shaxsiy kabinetingizga kiring!", "warning")
        return redirect(url_for('student_login'))

    student_id = session['student']['id']
    reward_id = request.form.get('reward_id')

    if not reward_id:
        flash("Sovrin tanlanmadi!", "danger")
        return redirect(url_for('student_cabinet'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM coins_transactions WHERE student_id = ?", (student_id,))
    current_coins = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM rewards WHERE id = ? AND active = 1", (reward_id,))
    reward = cursor.fetchone()

    if not reward:
        conn.close()
        flash("Sovrin topilmadi yoki faol emas!", "danger")
        return redirect(url_for('student_cabinet'))

    if reward['stock'] <= 0:
        conn.close()
        flash("Kechirasiz, ushbu sovrin hozirda omborda qolmagan!", "warning")
        return redirect(url_for('student_cabinet'))

    if current_coins < reward['cost_coins']:
        conn.close()
        flash(f"Coinlaringiz yetarli emas! Sizda {current_coins} coin bor, ushbu sovrin uchun {reward['cost_coins']} coin kerak.", "danger")
        return redirect(url_for('student_cabinet'))

    # Deduct coins
    cursor.execute('''
    INSERT INTO coins_transactions (student_id, amount, reason)
    VALUES (?, ?, ?)
    ''', (student_id, -reward['cost_coins'], f"Sovrin xaridi: {reward['title']}"))

    # Decrement stock
    cursor.execute("UPDATE rewards SET stock = stock - 1 WHERE id = ?", (reward_id,))

    # Create order
    cursor.execute('''
    INSERT INTO reward_orders (reward_id, student_id, status)
    VALUES (?, ?, 'pending')
    ''', (reward_id, student_id))

    conn.commit()
    conn.close()

    # Notify admin via Telegram
    telegram_service.send_admin_alert(
        "🎁 Yangi Sovrin Buyurtmasi!",
        f"O'quvchi #{student_id} «{reward['title']}» ({reward['cost_coins']} Coins) uchun buyurtma berdi. Iltimos, admin panelda buyurtmani tasdiqlang."
    )

    flash(f"Tabriklaymiz! «{reward['title']}» sovrini uchun buyurtmangiz qabul qilindi. Tez orada sovg'angizni qabul qilib olasiz!", "success")
    return redirect(url_for('student_cabinet'))

# -------------------------------------------------------------
# 6. QUIZ ARENA (INTERAKTIV VIKTORINALAR)
# -------------------------------------------------------------
@app.route('/student/quizzes/<int:quiz_id>')
def student_quiz_take(quiz_id):
    if 'student' not in session:
        flash("Viktorinada qatnashish uchun avval tizimga kiring!", "warning")
        return redirect(url_for('student_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quizzes WHERE id = ? AND active = 1", (quiz_id,))
    quiz = cursor.fetchone()

    if not quiz:
        conn.close()
        flash("Viktorina topilmadi!", "danger")
        return redirect(url_for('student_cabinet'))

    cursor.execute("SELECT * FROM quiz_questions WHERE quiz_id = ? ORDER BY id ASC", (quiz_id,))
    questions = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return render_template('public/quiz_take.html', quiz=dict(quiz), questions=questions)


@app.route('/student/quizzes/<int:quiz_id>/submit', methods=['POST'])
def student_quiz_submit(quiz_id):
    if 'student' not in session:
        flash("Avval tizimga kiring!", "warning")
        return redirect(url_for('student_login'))

    student_id = session['student']['id']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,))
    quiz = cursor.fetchone()
    if not quiz:
        conn.close()
        flash("Viktorina topilmadi!", "danger")
        return redirect(url_for('student_cabinet'))

    cursor.execute("SELECT * FROM quiz_questions WHERE quiz_id = ?", (quiz_id,))
    questions = cursor.fetchall()

    total_points = sum(q['points'] for q in questions) or 100
    earned_points = 0

    for q in questions:
        ans = request.form.get(f"q_{q['id']}")
        if ans and ans == q['correct_option']:
            earned_points += q['points']

    percentage = round((earned_points / total_points) * 100, 1) if total_points > 0 else 0
    passed = 1 if percentage >= quiz['passing_score'] else 0

    # Save attempt
    cursor.execute('''
    INSERT INTO quiz_attempts (quiz_id, student_id, score, max_score, passed)
    VALUES (?, ?, ?, ?, ?)
    ''', (quiz_id, student_id, percentage, 100, passed))

    # Award coins if passed (+40 coins)
    if passed:
        cursor.execute('''
        INSERT INTO coins_transactions (student_id, amount, reason)
        VALUES (?, 40, ?)
        ''', (student_id, f"«{quiz['title']}» viktorinasini a'lo topshirganlik bonusi"))

    conn.commit()
    conn.close()

    if passed:
        flash(f"Ajoyib natija! Siz testni {percentage}% bilan muvaffaqiyatli topshirdingiz va +40 Antigravity Coins yutib oldingiz! 🎉", "success")
    else:
        flash(f"Siz testda {percentage}% natija ko'rsatdingiz. O'tish bali {quiz['passing_score']}%. Yana harakat qilib ko'ring!", "warning")

    return redirect(url_for('student_cabinet'))

# -------------------------------------------------------------
# 7. OFFICIAL CERTIFICATE
# -------------------------------------------------------------
@app.route('/student/certificate')
def student_own_certificate():
    if 'student' not in session:
        flash("Sertifikatni ko'rish uchun avval kabinetga kiring!", "warning")
        return redirect(url_for('student_login'))
    return redirect(url_for('student_certificate', student_id=session['student']['id']))


@app.route('/student/<int:student_id>/certificate')
def student_certificate(student_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    SELECT s.*, c.title as course_title, gr.name as group_name, t.full_name as teacher_name,
           ROUND(AVG(g.score), 1) as avg_score
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN teachers t ON s.teacher_id = t.id
    LEFT JOIN grades g ON s.id = g.student_id
    WHERE s.id = ?
    GROUP BY s.id
    ''', (student_id,))
    student = cursor.fetchone()
    conn.close()

    if not student:
        flash("O'quvchi topilmadi!", "danger")
        return redirect(url_for('index'))

    return render_template(
        'public/certificate.html',
        student=dict(student),
        avg_score=student['avg_score'] or '88.5'
    )

# -------------------------------------------------------------
# 8. DATA EXPORT (EXCEL / CSV)
# -------------------------------------------------------------
@app.route('/admin/export/students')
@login_required
def admin_export_students():
    import csv
    import io
    from flask import make_response

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT s.id, s.first_name, s.last_name, s.phone, s.birth_date,
           c.title as course_title, gr.name as group_name, t.full_name as teacher_name,
           s.parent_name, s.parent_phone, s.status, s.created_at
    FROM students s
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    LEFT JOIN teachers t ON s.teacher_id = t.id
    ORDER BY s.id ASC
    ''')
    rows = cursor.fetchall()
    conn.close()

    si = io.StringIO()
    si.write('\ufeff')
    writer = csv.writer(si)
    writer.writerow(['ID', 'Ism', 'Familiya', 'Telefon', 'Tug\'ilgan sana', 'Kurs', 'Guruh', 'Ustoz', 'Ota-ona', 'Ota-ona telefoni', 'Holat', 'Ro\'yxatdan o\'tgan'])

    for r in rows:
        writer.writerow([r['id'], r['first_name'], r['last_name'], r['phone'], r['birth_date'], r['course_title'] or '', r['group_name'] or '', r['teacher_name'] or '', r['parent_name'] or '', r['parent_phone'] or '', r['status'], r['created_at']])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=antigravity_students_{datetime.now().strftime('%Y%m%d')}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


@app.route('/admin/export/grades')
@login_required
def admin_export_grades():
    import csv
    import io
    from flask import make_response

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
    SELECT g.id, s.first_name, s.last_name, gr.name as group_name,
           g.subject, g.score, g.assessment_type, g.assessment_date, g.comment
    FROM grades g
    JOIN students s ON g.student_id = s.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    ORDER BY g.assessment_date DESC, g.id DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    si = io.StringIO()
    si.write('\ufeff')
    writer = csv.writer(si)
    writer.writerow(['ID', 'Ism', 'Familiya', 'Guruh', 'Fan', 'Baho', 'Nazorat Turi', 'Sana', 'Izoh'])

    for r in rows:
        writer.writerow([r['id'], r['first_name'], r['last_name'], r['group_name'] or '', r['subject'], r['score'], r['assessment_type'], r['assessment_date'], r['comment'] or ''])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=antigravity_grades_{datetime.now().strftime('%Y%m%d')}.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


# =============================================================
# SMART AKADEMIYA: 6 TA YANGI TIZIM (INNOVATIVE MODULES)
# =============================================================

@app.template_filter('format_currency')
def format_currency_filter(val):
    try:
        if val is None or val == '':
            return "0 so'm"
        num = float(val)
        return f"{num:,.0f}".replace(",", " ") + " so'm"
    except (ValueError, TypeError):
        return f"{val} so'm"


# 1. 🏆 TOURNAMENTS & OLIMPIADA MARKAZI
@app.route('/admin/tournaments')
@login_required
def admin_tournaments():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.*, c.title as course_title
        FROM tournaments t
        LEFT JOIN courses c ON t.course_id = c.id
        ORDER BY t.id DESC
    """)
    tournaments = [dict(t) for t in cursor.fetchall()]

    active_count = sum(1 for t in tournaments if t.get('status') == 'active')
    total_participants_count = 0

    for t in tournaments:
        cursor.execute("""
            SELECT tp.*, s.first_name, s.last_name, gr.name as group_name
            FROM tournament_participants tp
            JOIN students s ON tp.student_id = s.id
            LEFT JOIN groups gr ON s.group_id = gr.id
            WHERE tp.tournament_id = ?
            ORDER BY tp.score DESC, tp.id ASC
        """, (t['id'],))
        t['participants'] = [dict(p) for p in cursor.fetchall()]
        total_participants_count += len(t['participants'])

    cursor.execute("SELECT id, first_name, last_name, group_id FROM students WHERE status = 'active' ORDER BY first_name ASC")
    all_students = [dict(s) for s in cursor.fetchall()]
    for s in all_students:
        s['full_name'] = f"{s['first_name']} {s['last_name']}"

    cursor.execute("SELECT id, title FROM courses WHERE active = 1 ORDER BY title ASC")
    courses = [dict(c) for c in cursor.fetchall()]
    conn.close()

    return render_template(
        'admin/tournaments.html',
        tournaments=tournaments,
        active_count=active_count,
        total_participants_count=total_participants_count,
        all_students=all_students,
        students=all_students,
        courses=courses
    )

@app.route('/admin/tournaments/new', methods=['POST'])
@login_required
def admin_tournament_new():
    title = request.form.get('title', '').strip()
    course_id = request.form.get('course_id') or None
    prize_pool = request.form.get('prize_pool', "1 000 000 so'm + 500 Coins")
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    max_participants = request.form.get('max_participants', type=int, default=50)
    description = request.form.get('description', '')

    if not title or not start_date or not end_date:
        flash("Iltimos, musobaqa nomi va sanalarini to'liq kiriting!", "danger")
        return redirect(url_for('admin_tournaments'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tournaments (title, course_id, description, prize_pool, start_date, end_date, max_participants, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
    """, (title, course_id, description, prize_pool, start_date, end_date, max_participants))
    conn.commit()
    conn.close()

    flash(f"'{title}' nomli yangi musobaqa muvaffaqiyatli e'lon qilindi!", "success")
    return redirect(url_for('admin_tournaments'))

@app.route('/admin/tournaments/add-participant', methods=['POST'])
@login_required
def admin_tournament_add_participant():
    tournament_id = request.form.get('tournament_id', type=int)
    student_id = request.form.get('student_id', type=int)
    if tournament_id and student_id:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tournament_participants WHERE tournament_id = ? AND student_id = ?", (tournament_id, student_id))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO tournament_participants (tournament_id, student_id, score, rank, prize_claimed)
                VALUES (?, ?, 0, NULL, 0)
            """, (tournament_id, student_id))
            conn.commit()
            flash("O'quvchi musobaqa ishtirokchilari safiga qo'shildi!", "success")
        else:
            flash("Ushbu o'quvchi allaqachon bu musobaqada ro'yxatdan o'tgan.", "warning")
        conn.close()
    return redirect(url_for('admin_tournaments'))

@app.route('/admin/tournaments/update-score', methods=['POST'])
@login_required
def admin_tournament_update_score():
    tournament_id = request.form.get('tournament_id', type=int)
    student_id = request.form.get('student_id', type=int)
    participant_id = request.form.get('participant_id', type=int)
    score = request.form.get('score', type=float, default=0.0)
    rank = request.form.get('rank')

    conn = get_db_connection()
    cursor = conn.cursor()
    if tournament_id and student_id:
        cursor.execute("UPDATE tournament_participants SET score = ?, rank = ? WHERE tournament_id = ? AND student_id = ?", 
                       (score, rank if rank else None, tournament_id, student_id))
    elif participant_id:
        cursor.execute("UPDATE tournament_participants SET score = ?, rank = ? WHERE id = ?", 
                       (score, rank if rank else None, participant_id))
    conn.commit()
    conn.close()
    flash("Ishtirokchi bali yangilandi!", "success")
    return redirect(url_for('admin_tournaments'))

@app.route('/admin/tournaments/<int:id>/finish', methods=['POST'])
@login_required
def admin_tournament_finish(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE tournaments SET status = 'completed' WHERE id = ?", (id,))
    cursor.execute("""
        SELECT tp.student_id, tp.score, s.first_name || ' ' || s.last_name as full_name
        FROM tournament_participants tp
        JOIN students s ON tp.student_id = s.id
        WHERE tp.tournament_id = ?
        ORDER BY tp.score DESC LIMIT 3
    """, (id,))
    top_winners = cursor.fetchall()
    coin_prizes = [300, 200, 100]
    for idx, w in enumerate(top_winners):
        coins = coin_prizes[idx] if idx < len(coin_prizes) else 50
        cursor.execute("UPDATE students SET coins = COALESCE(coins, 0) + ? WHERE id = ?", (coins, w['student_id']))
        cursor.execute("""
            INSERT INTO coin_transactions (student_id, amount, reason, transaction_type)
            VALUES (?, ?, ?, 'reward')
        """, (w['student_id'], coins, f"Musobaqada {idx+1}-o'rin egallagani uchun"))
    conn.commit()
    conn.close()
    flash("Musobaqa yakunlandi va sovrindorlarga avtomatik tarzda tangalar topshirildi!", "success")
    return redirect(url_for('admin_tournaments'))


# 2. 📞 VIRTUAL CALL-CENTER CRM
@app.route('/admin/call-center')
@login_required
def admin_call_center():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM call_logs ORDER BY id DESC")
    calls = [dict(r) for r in cursor.fetchall()]

    today_str = datetime.now().strftime('%Y-%m-%d')
    today_calls = sum(1 for c in calls if c.get('created_at', '').startswith(today_str))
    booked_trials = sum(1 for c in calls if c.get('status') == 'trial_booked')
    enrolled_count = sum(1 for c in calls if c.get('status') == 'enrolled')

    cursor.execute("SELECT id, title, price FROM courses WHERE active = 1 ORDER BY title ASC")
    courses = [dict(c) for c in cursor.fetchall()]
    conn.close()

    return render_template(
        'admin/call_center.html',
        calls=calls,
        call_logs=calls,
        today_calls=today_calls,
        booked_trials=booked_trials,
        enrolled_count=enrolled_count,
        courses=courses
    )

@app.route('/admin/call-center/new', methods=['POST'])
@login_required
def admin_call_new():
    student_name = request.form.get('student_name', '').strip()
    phone = request.form.get('phone', '').strip()
    call_type = request.form.get('call_type', 'incoming')
    status = request.form.get('status', 'interested')
    duration_seconds = request.form.get('duration_seconds', type=int, default=90)
    callback_date = request.form.get('callback_date') or None
    notes = request.form.get('notes', '')
    user = session.get('user') or {}
    created_by = user.get('full_name') or user.get('username') or 'Operator'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO call_logs (student_name, phone, call_type, status, duration_seconds, notes, callback_date, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (student_name, phone, call_type, status, duration_seconds, notes, callback_date, created_by))
    conn.commit()
    conn.close()

    flash(f"{student_name} bilan bo'lgan qo'ng'iroq muvaffaqiyatli qayd etildi!", "success")
    return redirect(url_for('admin_call_center'))

@app.route('/admin/call-center/send-info/<int:id>', methods=['POST'])
@login_required
def admin_call_send_info(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM call_logs WHERE id = ?", (id,))
    call_data = cursor.fetchone()
    conn.close()

    if call_data:
        msg = (
            f"📞 <b>CodeCraft IT Academy - Kurs Haqida Ma'lumot</b>\n\n"
            f"Assalomu alaykum, <b>{call_data['student_name']}</b>!\n"
            f"Bizning akademiyamizda dasturlash va IT kurslariga qabul davom etmoqda.\n"
            f"Oylik to'lov: 650 000 so'm / oy.\n"
            f"Sinov darsiga yozilish uchun qo'ng'iroq qiling: +998 71 200 05 05"
        )
        try:
            from telegram_service import send_telegram_raw, get_setting
            admin_chat_id = get_setting('admin_telegram_chat_id', '')
            if admin_chat_id:
                send_telegram_raw(admin_chat_id, f"[Call-Center Avtomatik Habar]\nTelefon: {call_data['phone']}\n\n{msg}")
        except Exception:
            pass
        flash(f"{call_data['student_name']} ga kurs ma'lumotlari yuborildi!", "success")
    return redirect(url_for('admin_call_center'))


# 3. 📊 360° O'QUVCHI KOMPETENSIYA RADARI
@app.route('/admin/competency-matrix')
@login_required
def admin_competency_matrix():
    student_id = request.args.get('student_id', type=int)

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT g.id, g.name, c.title as course_name FROM groups g LEFT JOIN courses c ON g.course_id = c.id WHERE g.active = 1")
    groups = [dict(g) for g in cursor.fetchall()]

    cursor.execute("""
        SELECT s.id, s.first_name || ' ' || s.last_name as full_name, s.phone, gr.name as group_name,
               cs.theory, cs.practice, cs.discipline, cs.speed, cs.teamwork,
               cs.mentor_notes, cs.updated_at
        FROM students s
        LEFT JOIN groups gr ON s.group_id = gr.id
        LEFT JOIN competency_scores cs ON s.id = cs.student_id
        WHERE s.status = 'active'
        ORDER BY s.first_name ASC
    """)
    raw_students = cursor.fetchall()
    students = []
    scored_count = 0
    total_score_sum = 0
    skills_sum = {'theory': 0, 'practice': 0, 'discipline': 0, 'speed': 0, 'teamwork': 0}

    for row in raw_students:
        s = dict(row)
        s['theory_score'] = s['theory']
        s['practice_score'] = s['practice']
        s['discipline_score'] = s['discipline']
        s['speed_score'] = s['speed']
        s['teamwork_score'] = s['teamwork']
        s['teacher_notes'] = s['mentor_notes']
        if s['theory'] is not None:
            scored_count += 1
            ov = (s['theory'] + s['practice'] + s['discipline'] + s['speed'] + s['teamwork']) / 5.0
            s['overall_score'] = ov
            total_score_sum += ov
            skills_sum['theory'] += s['theory']
            skills_sum['practice'] += s['practice']
            skills_sum['discipline'] += s['discipline']
            skills_sum['speed'] += s['speed']
            skills_sum['teamwork'] += s['teamwork']
        else:
            s['overall_score'] = None
        students.append(s)

    avg_overall = (total_score_sum / scored_count) if scored_count > 0 else 0
    skill_names = {
        'theory': 'Nazariy Bilim',
        'practice': 'Amaliy Kodlash',
        'discipline': 'Tartib & Intizom',
        'speed': 'Topshiriq Tezligi',
        'teamwork': 'Jamoaviy Ish'
    }
    if scored_count > 0:
        top_skill_key = max(skills_sum, key=skills_sum.get)
        weak_skill_key = min(skills_sum, key=skills_sum.get)
        top_skill_name = skill_names[top_skill_key]
        weak_skill_name = skill_names[weak_skill_key]
    else:
        top_skill_name = "Amaliy Kodlash"
        weak_skill_name = "Topshiriq Tezligi"

    selected_student = None
    current_score = None
    if student_id:
        selected_student = next((st for st in students if st['id'] == student_id), None)
    elif students:
        selected_student = students[0]

    if selected_student:
        cursor.execute("SELECT * FROM competency_scores WHERE student_id = ?", (selected_student['id'],))
        score_row = cursor.fetchone()
        if score_row:
            sdict = dict(score_row)
            current_score = {
                'theory_score': sdict['theory'],
                'practice_score': sdict['practice'],
                'discipline_score': sdict['discipline'],
                'speed_score': sdict['speed'],
                'teamwork_score': sdict['teamwork'],
                'overall': (sdict['theory'] + sdict['practice'] + sdict['discipline'] + sdict['speed'] + sdict['teamwork']) / 5.0,
                'teacher_notes': sdict.get('mentor_notes') or '',
                'updated_at': sdict.get('updated_at')
            }
        else:
            current_score = {
                'theory_score': 75,
                'practice_score': 80,
                'discipline_score': 90,
                'speed_score': 70,
                'teamwork_score': 85,
                'overall': 80.0,
                'teacher_notes': '',
                'updated_at': None
            }

    conn.close()

    return render_template(
        'admin/competency_matrix.html',
        students=students,
        groups=groups,
        selected_student=selected_student,
        current_score=current_score,
        scored_count=scored_count,
        avg_overall=avg_overall,
        top_skill_name=top_skill_name,
        weak_skill_name=weak_skill_name,
        now_date=datetime.now().strftime('%Y-%m-%d')
    )

@app.route('/admin/competency-matrix/save', methods=['POST'])
@login_required
def admin_save_competency():
    student_id = request.form.get('student_id', type=int)
    theory_score = request.form.get('theory_score', type=int, default=70)
    practice_score = request.form.get('practice_score', type=int, default=70)
    discipline_score = request.form.get('discipline_score', type=int, default=70)
    speed_score = request.form.get('speed_score', type=int, default=70)
    teamwork_score = request.form.get('teamwork_score', type=int, default=70)
    teacher_notes = request.form.get('teacher_notes', '').strip()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM competency_scores WHERE student_id = ?", (student_id,))
    existing = cursor.fetchone()
    if existing:
        cursor.execute("""
            UPDATE competency_scores
            SET theory = ?, practice = ?, discipline = ?, speed = ?, teamwork = ?,
                mentor_notes = ?, updated_at = ?
            WHERE student_id = ?
        """, (theory_score, practice_score, discipline_score, speed_score, teamwork_score, teacher_notes, now_str, student_id))
    else:
        cursor.execute("""
            INSERT INTO competency_scores (student_id, theory, practice, discipline, speed, teamwork, mentor_notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (student_id, theory_score, practice_score, discipline_score, speed_score, teamwork_score, teacher_notes, now_str))
    conn.commit()
    conn.close()

    flash("O'quvchining 360° kompetensiya profili muvaffaqiyatli saqlandi!", "success")
    return redirect(url_for('admin_competency_matrix', student_id=student_id))


# 4. 🎫 JONLI QR TURNIKET & KIRISH TERMINALI
@app.route('/admin/turnstile')
@login_required
def admin_turnstile():
    today_str = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.id, a.student_id, a.date, a.status, a.note,
               s.first_name || ' ' || s.last_name as student_name,
               gr.name as group_name
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        LEFT JOIN groups gr ON s.group_id = gr.id
        WHERE a.date = ?
        ORDER BY a.id DESC LIMIT 25
    """, (today_str,))
    raw_recent = cursor.fetchall()
    recent_scans = []
    today_entries = 0
    for r in raw_recent:
        item = dict(r)
        note = item.get('note') or ''
        scan_type = 'out' if 'Chiqish' in note else 'in'
        time_part = note.split()[-1] if note and ':' in note else 'Bugun'
        item['scan_time'] = time_part
        item['scan_type'] = scan_type
        recent_scans.append(item)
        if scan_type == 'in':
            today_entries += 1

    cursor.execute("SELECT id, first_name || ' ' || last_name as full_name FROM students WHERE status = 'active' ORDER BY id ASC LIMIT 8")
    sample_students = [dict(s) for s in cursor.fetchall()]

    currently_inside = max(0, len(recent_scans) - 2)
    conn.close()

    return render_template(
        'admin/turnstile.html',
        recent_scans=recent_scans,
        today_entries_count=max(today_entries, len(recent_scans)),
        currently_inside=currently_inside,
        sample_students=sample_students
    )

@app.route('/api/turnstile/scan', methods=['POST'])
@login_required
def api_turnstile_scan():
    data = request.get_json() or {}
    student_query = str(data.get('student_query', '')).strip()
    mode = data.get('mode', 'in')
    notify_parent = data.get('notify_parent', True)

    if not student_query:
        return jsonify({'success': False, 'error': "O'quvchi ma'lumoti kiritilmadi"}), 400

    clean_id = student_query.replace('ST-', '').replace('#', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    student = None
    if clean_id.isdigit():
        cursor.execute("""
            SELECT s.*, gr.name as group_name
            FROM students s
            LEFT JOIN groups gr ON s.group_id = gr.id
            WHERE s.id = ?
        """, (int(clean_id),))
        student = cursor.fetchone()

    if not student:
        cursor.execute("""
            SELECT s.*, gr.name as group_name
            FROM students s
            LEFT JOIN groups gr ON s.group_id = gr.id
            WHERE s.phone = ? OR (s.first_name || ' ' || s.last_name) LIKE ?
        """, (student_query, f"%{student_query}%"))
        student = cursor.fetchone()

    if not student:
        conn.close()
        return jsonify({'success': False, 'error': f"ID yoki ma'lumot bo'yicha o'quvchi topilmadi: {student_query}"}), 404

    student_dict = dict(student)
    full_name = f"{student_dict['first_name']} {student_dict['last_name']}"
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')

    note_text = f"{'Kirish' if mode == 'in' else 'Chiqish'} soat {time_str}"
    cursor.execute("SELECT id FROM attendance WHERE student_id = ? AND date = ?", (student_dict['id'], today_str))
    att_row = cursor.fetchone()
    if att_row:
        cursor.execute("UPDATE attendance SET status = 'present', note = ? WHERE id = ?", (note_text, att_row['id']))
    else:
        cursor.execute("""
            INSERT INTO attendance (student_id, group_id, date, status, note)
            VALUES (?, ?, ?, 'present', ?)
        """, (student_dict['id'], student_dict.get('group_id'), today_str, note_text))
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM attendance WHERE date = ?", (today_str,))
    today_entries_count = cursor.fetchone()[0]
    conn.close()

    if notify_parent:
        try:
            from telegram_service import send_telegram_raw, get_setting
            parent_chat = student_dict.get('parent_telegram_chat_id') or student_dict.get('telegram_chat_id') or get_setting('admin_telegram_chat_id')
            action_text = "Akademiya binosiga kirdi" if mode == 'in' else "Akademiya binosidan chiqdi"
            emoji = "🟢" if mode == 'in' else "🔴"
            msg = (
                f"{emoji} <b>Turniket Bildirishnomasi</b>\n\n"
                f"👤 O'quvchi: <b>{full_name}</b>\n"
                f"📚 Guruh: <b>{student_dict.get('group_name') or 'Asosiy'}</b>\n"
                f"⏰ Vaqt: <b>{time_str}</b>\n"
                f"📍 Holat: <b>{action_text}</b>"
            )
            if parent_chat:
                send_telegram_raw(parent_chat, msg)
        except Exception as e:
            print(f"[Turniket Telegram error] {e}")

    return jsonify({
        'success': True,
        'student': {
            'id': student_dict['id'],
            'full_name': full_name,
            'phone': student_dict.get('phone'),
            'group_name': student_dict.get('group_name')
        },
        'mode': mode,
        'time': time_str,
        'today_entries_count': today_entries_count,
        'currently_inside': max(1, today_entries_count - 1)
    })


# 5. 📜 O'QUV SHARTNOMALARI & HUJJATLAR MARKAZI
@app.route('/admin/contracts')
@login_required
def admin_contracts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, s.first_name || ' ' || s.last_name as student_name, s.phone as student_phone,
               cr.title as course_name
        FROM contracts c
        JOIN students s ON c.student_id = s.id
        LEFT JOIN courses cr ON s.course_id = cr.id
        ORDER BY c.id DESC
    """)
    contracts = [dict(row) for row in cursor.fetchall()]

    for c in contracts:
        if not c.get('course_name'):
            c['course_name'] = 'Amaliy IT Yo\'nalishi'
        c['total_amount'] = (c.get('monthly_amount') or 650000) * 6

    active_count = sum(1 for c in contracts if c.get('status') == 'active')
    total_contract_sum = sum(c['total_amount'] for c in contracts)

    cursor.execute("SELECT COUNT(*) FROM students WHERE status = 'active'")
    total_students = cursor.fetchone()[0] or 1
    coverage_rate = min(100, round((len(contracts) / total_students) * 100, 1))

    cursor.execute("SELECT id, first_name || ' ' || last_name as full_name, group_id FROM students WHERE status = 'active' ORDER BY first_name ASC")
    students = [dict(s) for s in cursor.fetchall()]

    cursor.execute("SELECT id, title as name, price FROM courses WHERE active = 1 ORDER BY title ASC")
    courses = [dict(c) for c in cursor.fetchall()]

    conn.close()

    return render_template(
        'admin/contracts.html',
        contracts=contracts,
        active_count=active_count,
        total_contract_sum=total_contract_sum,
        coverage_rate=coverage_rate,
        students=students,
        courses=courses
    )

@app.route('/admin/contracts/new', methods=['POST'])
@login_required
def admin_new_contract():
    student_id = request.form.get('student_id', type=int)
    course_id = request.form.get('course_id', type=int)
    parent_name = request.form.get('parent_name', '').strip()
    parent_phone = request.form.get('parent_phone', '').strip()
    passport_series = request.form.get('passport_series', '').strip().upper()
    monthly_amount = request.form.get('monthly_amount', type=float, default=650000)
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    notes = request.form.get('notes', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM contracts")
    cnt = cursor.fetchone()[0] + 1
    contract_number = f"AZ1-2026-{cnt:04d}"

    if course_id and student_id:
        cursor.execute("UPDATE students SET course_id = ? WHERE id = ?", (course_id, student_id))

    cursor.execute("""
        INSERT INTO contracts (contract_number, student_id, parent_name, parent_phone, passport_series, address, monthly_amount, start_date, end_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
    """, (contract_number, student_id, parent_name, parent_phone, passport_series, notes or "Toshkent shahar", monthly_amount, start_date, end_date))
    conn.commit()
    conn.close()

    flash(f"'{contract_number}' raqamli o'quv shartnomasi muvaffaqiyatli rasmiylashtirildi!", "success")
    return redirect(url_for('admin_contracts'))

@app.route('/admin/contracts/<int:id>/view')
@app.route('/admin/contracts/<int:contract_id>/view')
@login_required
def admin_contract_view(id=None, contract_id=None):
    cid = id or contract_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, s.first_name || ' ' || s.last_name as student_name, s.phone as student_phone,
               cr.title as course_name
        FROM contracts c
        JOIN students s ON c.student_id = s.id
        LEFT JOIN courses cr ON s.course_id = cr.id
        WHERE c.id = ?
    """, (cid,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        flash("Shartnoma topilmadi.", "danger")
        return redirect(url_for('admin_contracts'))

    cdict = dict(row)
    if not cdict.get('course_name'):
        cdict['course_name'] = 'Axborot Texnologiyalari kursi'
    cdict['total_amount'] = (cdict.get('monthly_amount') or 650000) * 6
    cdict['notes'] = cdict.get('address') or 'Standart ta\'lim shartnomasi qoidalari asosida.'

    return render_template('admin/contract_view.html', contract=cdict)

@app.route('/admin/contracts/<int:contract_id>/terminate', methods=['POST'])
@login_required
def admin_terminate_contract(contract_id):
    reason = request.form.get('termination_reason', 'Tomonlar o\'zaro kelishuvi asosida bekor qilindi').strip()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE contracts 
        SET status = 'terminated', termination_reason = ?, terminated_at = ?
        WHERE id = ?
    """, (reason, now_str, contract_id))
    conn.commit()
    conn.close()
    flash("Shartnoma muvaffaqiyatli bekor qilindi va rasmiy bekor qilish muhri qo'yildi.", "warning")
    return redirect(url_for('admin_contracts'))

@app.route('/admin/contracts/<int:contract_id>/reactivate', methods=['POST'])
@login_required
def admin_reactivate_contract(contract_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE contracts 
        SET status = 'active', termination_reason = NULL, terminated_at = NULL
        WHERE id = ?
    """, (contract_id,))
    conn.commit()
    conn.close()
    flash("Shartnoma qayta muvaffaqiyatli faollashtirildi.", "success")
    return redirect(url_for('admin_contracts'))


# 6. 🏢 INTERAKTIV KAMPUS & XONALAR XARITASI
@app.route('/admin/campus-map')
@login_required
def admin_campus_map():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM room_bookings ORDER BY id DESC")
    raw_bookings = cursor.fetchall()
    bookings = []
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_bookings_count = 0

    for b in raw_bookings:
        item = dict(b)
        item['booking_date'] = item.get('date') or today_str
        item['purpose'] = item.get('title') or item.get('notes') or 'Amaliy mashg\'ulot'
        item['time_slot'] = f"{item.get('start_time') or '14:00'} - {item.get('end_time') or '16:00'}"
        if item['booking_date'] == today_str:
            today_bookings_count += 1
        bookings.append(item)

    total_rooms_count = 6
    occupied_rooms_count = 2
    free_rooms_count = total_rooms_count - occupied_rooms_count

    conn.close()

    return render_template(
        'admin/campus_map.html',
        bookings=bookings,
        total_rooms_count=total_rooms_count,
        occupied_rooms_count=occupied_rooms_count,
        free_rooms_count=free_rooms_count,
        today_bookings_count=today_bookings_count
    )

@app.route('/admin/campus-map/book', methods=['POST'])
@login_required
def admin_campus_book():
    room_name = request.form.get('room_name')
    booking_date = request.form.get('booking_date')
    time_slot = request.form.get('time_slot', '14:00 - 16:00')
    purpose = request.form.get('purpose')
    user = session.get('user') or {}
    booked_by = request.form.get('booked_by') or user.get('full_name') or user.get('username') or 'Administrator'

    if not room_name or not booking_date or not purpose:
        flash("Iltimos, bronlash uchun barcha maydonlarni to'ldiring!", "danger")
        return redirect(url_for('admin_campus_map'))

    parts = time_slot.split('-')
    start_time = parts[0].strip() if len(parts) > 0 else '14:00'
    end_time = parts[1].strip() if len(parts) > 1 else '16:00'

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO room_bookings (room_name, title, booked_by, date, start_time, end_time, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (room_name, purpose, booked_by, booking_date, start_time, end_time, purpose))
    conn.commit()
    conn.close()

    flash(f"'{room_name}' xonasi {booking_date} ({time_slot}) ga muvaffaqiyatli bron qilindi!", "success")
    return redirect(url_for('admin_campus_map'))


# ========================================================
# 7. 🎓 BITIRUV SERTIFIKATLARI & QR DIPLOM MARKAZI
# ========================================================
@app.route('/admin/certificates')
@login_required
def admin_certificates():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, s.first_name || ' ' || s.last_name as student_name, cr.title as course_name
        FROM certificates c
        JOIN students s ON c.student_id = s.id
        JOIN courses cr ON c.course_id = cr.id
        ORDER BY c.id DESC
    """)
    certificates = [dict(row) for row in cursor.fetchall()]

    distinction_count = sum(1 for c in certificates if 'Distinction' in (c.get('grade_level') or '') or 'A\'lo' in (c.get('grade_level') or ''))

    cursor.execute("SELECT id, first_name || ' ' || last_name as full_name FROM students WHERE status = 'active' ORDER BY first_name ASC")
    students = [dict(s) for s in cursor.fetchall()]

    cursor.execute("SELECT id, title as name FROM courses WHERE active = 1 ORDER BY title ASC")
    courses = [dict(c) for c in cursor.fetchall()]

    conn.close()

    today_date = datetime.now().strftime('%Y-%m-%d')

    return render_template(
        'admin/certificates.html',
        certificates=certificates,
        distinction_count=distinction_count,
        students=students,
        courses=courses,
        today_date=today_date
    )

@app.route('/admin/certificates/new', methods=['POST'])
@login_required
def admin_new_certificate():
    student_id = request.form.get('student_id', type=int)
    course_id = request.form.get('course_id', type=int)
    grade_level = request.form.get('grade_level', "A'lo darajali (With Distinction)").strip()
    issue_date = request.form.get('issue_date') or datetime.now().strftime('%Y-%m-%d')
    notes = request.form.get('notes', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM certificates")
    cnt = cursor.fetchone()[0] + 1
    cert_number = f"CRT-2026/{cnt:03d}"
    qr_code = f"{cert_number}-AZ1-VERIFIED"

    cursor.execute("""
        INSERT INTO certificates (certificate_number, student_id, course_id, issue_date, grade_level, qr_code, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (cert_number, student_id, course_id, issue_date, grade_level, qr_code, notes))
    conn.commit()
    conn.close()

    flash(f"'{cert_number}' raqamli bitiruv sertifikati muvaffaqiyatli rasmiylashtirildi!", "success")
    return redirect(url_for('admin_certificates'))

@app.route('/admin/certificates/<int:cert_id>/view')
@login_required
def admin_certificate_view(cert_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, s.first_name || ' ' || s.last_name as student_name, cr.title as course_name
        FROM certificates c
        JOIN students s ON c.student_id = s.id
        JOIN courses cr ON c.course_id = cr.id
        WHERE c.id = ?
    """, (cert_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        flash("Sertifikat topilmadi.", "danger")
        return redirect(url_for('admin_certificates'))

    return render_template('admin/certificate_view.html', cert=dict(row))


# ========================================================
# 8. 💸 TEZKOR KASSA POS TERMINALI & CHEK GENERATORI
# ========================================================
@app.route('/admin/pos-cashier')
@login_required
def admin_pos_cashier():
    conn = get_db_connection()
    cursor = conn.cursor()

    today_str = datetime.now().strftime('%Y-%m-%d')
    current_month_str = datetime.now().strftime('%Y-%m')

    # Today's payments
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0), COUNT(*) 
        FROM payments 
        WHERE payment_date LIKE ?
    """, (f"{today_str}%",))
    t_res = cursor.fetchone()
    today_total = t_res[0] or 0.0
    today_count = t_res[1] or 0

    # Monthly total
    cursor.execute("""
        SELECT COALESCE(SUM(amount), 0)
        FROM payments 
        WHERE payment_date LIKE ?
    """, (f"{current_month_str}%",))
    month_total = cursor.fetchone()[0] or 0.0

    # Online vs Cash
    cursor.execute("SELECT COUNT(*) FROM payments WHERE payment_method != 'cash'")
    online_count = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM payments")
    all_count = cursor.fetchone()[0] or 1
    online_percent = round((online_count / all_count) * 100, 1)

    # Recent payments
    cursor.execute("""
        SELECT p.*, s.first_name || ' ' || s.last_name as student_name
        FROM payments p
        JOIN students s ON p.student_id = s.id
        ORDER BY p.id DESC
        LIMIT 8
    """)
    recent_payments = [dict(r) for r in cursor.fetchall()]

    # Students list
    cursor.execute("""
        SELECT s.id, s.first_name || ' ' || s.last_name as full_name, s.phone,
               g.name as group_name, cr.title as course_name, cr.price as monthly_price
        FROM students s
        LEFT JOIN groups g ON s.group_id = g.id
        LEFT JOIN courses cr ON s.course_id = cr.id
        WHERE s.status = 'active'
        ORDER BY s.first_name ASC
    """)
    students = [dict(s) for s in cursor.fetchall()]

    conn.close()

    months_uz = {
        '01': 'Yanvar', '02': 'Fevral', '03': 'Mart', '04': 'Aprel',
        '05': 'May', '06': 'Iyun', '07': 'Iyul', '08': 'Avgust',
        '09': 'Sentyabr', '10': 'Oktyabr', '11': 'Noyabr', '12': 'Dekabr'
    }
    cur_m = datetime.now().strftime('%m')
    current_month_name = f"{months_uz.get(cur_m, 'Oktyabr')} {datetime.now().year}"

    return render_template(
        'admin/pos_cashier.html',
        today_total=today_total,
        today_count=today_count,
        month_total=month_total,
        online_percent=online_percent,
        recent_payments=recent_payments,
        students=students,
        current_month_name=current_month_name
    )

@app.route('/admin/pos-cashier/pay', methods=['POST'])
@login_required
def admin_pos_cashier_pay():
    student_id = request.form.get('student_id', type=int)
    amount = request.form.get('amount', type=float, default=0.0)
    payment_method = request.form.get('payment_method', 'cash')
    month_for = request.form.get('month_for', 'Oktyabr 2026').strip()
    notes = request.form.get('notes', '').strip()

    if not student_id or amount <= 0:
        flash("To'lov miqdori noto'g'ri kiritildi.", "danger")
        return redirect(url_for('admin_pos_cashier'))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO payments (student_id, amount, payment_date, payment_method, month_for, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (student_id, amount, now_str, payment_method, month_for, notes or "POS Kassa orqali qabul qilindi"))
    conn.commit()

    cursor.execute("SELECT first_name || ' ' || last_name FROM students WHERE id = ?", (student_id,))
    st_row = cursor.fetchone()
    st_name = st_row[0] if st_row else "O'quvchi"
    conn.close()

    flash(f"To'lov muvaffaqiyatli qabul qilindi! O'quvchi: {st_name}, Summa: {amount:,.0f} so'm. Chek shakllantirildi.", "success")
    return redirect(url_for('admin_pos_cashier'))


# ========================================================
# 9. 📚 AKADEMIYA KUTUBXONASI & RESURSLAR IJARASI
# ========================================================
@app.route('/admin/library')
@login_required
def admin_library():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM library_books ORDER BY id ASC")
    books = [dict(b) for b in cursor.fetchall()]

    cursor.execute("""
        SELECT bl.*, b.title as book_title, s.first_name || ' ' || s.last_name as student_name, s.phone as student_phone
        FROM book_loans bl
        JOIN library_books b ON bl.book_id = b.id
        JOIN students s ON bl.student_id = s.id
        ORDER BY bl.id DESC
    """)
    loans = [dict(l) for l in cursor.fetchall()]

    total_books_count = sum(b.get('total_copies', 0) for b in books)
    available_books_count = sum(b.get('available_copies', 0) for b in books)
    active_loans_count = sum(1 for l in loans if l.get('status') in ['borrowed', 'overdue'])
    overdue_loans_count = sum(1 for l in loans if l.get('status') == 'overdue')

    cursor.execute("SELECT id, first_name || ' ' || last_name as full_name, group_id FROM students WHERE status = 'active' ORDER BY first_name ASC")
    students = [dict(s) for s in cursor.fetchall()]

    conn.close()

    today_date = datetime.now().strftime('%Y-%m-%d')
    default_due_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

    return render_template(
        'admin/library.html',
        books=books,
        loans=loans,
        total_books_count=total_books_count,
        available_books_count=available_books_count,
        active_loans_count=active_loans_count,
        overdue_loans_count=overdue_loans_count,
        students=students,
        today_date=today_date,
        default_due_date=default_due_date
    )

@app.route('/admin/library/loan', methods=['POST'])
@login_required
def admin_library_loan():
    book_id = request.form.get('book_id', type=int)
    student_id = request.form.get('student_id', type=int)
    borrow_date = request.form.get('borrow_date') or datetime.now().strftime('%Y-%m-%d')
    due_date = request.form.get('due_date') or (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')
    notes = request.form.get('notes', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT available_copies, title FROM library_books WHERE id = ?", (book_id,))
    book = cursor.fetchone()
    if not book or book[0] <= 0:
        conn.close()
        flash("Ushbu kitobdan zaxirada qolmagan!", "danger")
        return redirect(url_for('admin_library'))

    cursor.execute("""
        INSERT INTO book_loans (book_id, student_id, borrow_date, due_date, status, notes)
        VALUES (?, ?, ?, ?, 'borrowed', ?)
    """, (book_id, student_id, borrow_date, due_date, notes))

    cursor.execute("UPDATE library_books SET available_copies = available_copies - 1 WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

    flash(f"'{book[1]}' kitobi o'quvchiga 14 kunga ijaraga berildi!", "success")
    return redirect(url_for('admin_library'))

@app.route('/admin/library/return/<int:loan_id>', methods=['POST'])
@login_required
def admin_library_return(loan_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT book_id, status FROM book_loans WHERE id = ?", (loan_id,))
    loan = cursor.fetchone()
    if not loan:
        conn.close()
        flash("Ijara qaydi topilmadi.", "danger")
        return redirect(url_for('admin_library'))

    book_id = loan[0]
    return_date = datetime.now().strftime('%Y-%m-%d')

    cursor.execute("""
        UPDATE book_loans 
        SET status = 'returned', return_date = ?
        WHERE id = ?
    """, (return_date, loan_id))

    cursor.execute("UPDATE library_books SET available_copies = available_copies + 1 WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

    flash("Kitob muvaffaqiyatli kutubxonaga qaytarib olindi va zaxiraga qo'shildi!", "success")
    return redirect(url_for('admin_library'))


# ========================================================
# 10. 👨‍🏫 USTOZLAR OYLIK MAOSHI & KPI PAYROLL TIZIMI
# ========================================================
@app.route('/admin/payroll')
@login_required
def admin_payroll():
    month = request.args.get('month', '2026-09')

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pr.*, t.full_name as teacher_name, t.subject as teacher_subject, t.phone as teacher_phone
        FROM payroll_records pr
        JOIN teachers t ON pr.teacher_id = t.id
        WHERE pr.month_year = ?
        ORDER BY pr.id ASC
    """, (month,))
    payrolls = [dict(p) for p in cursor.fetchall()]

    total_fund = sum(p.get('total_amount', 0) for p in payrolls)
    paid_total = sum(p.get('total_amount', 0) for p in payrolls if p.get('status') == 'paid')
    pending_total = sum(p.get('total_amount', 0) for p in payrolls if p.get('status') != 'paid')

    conn.close()

    return render_template(
        'admin/payroll.html',
        payrolls=payrolls,
        total_fund=total_fund,
        paid_total=paid_total,
        pending_total=pending_total,
        current_month=month
    )

@app.route('/admin/payroll/pay/<int:record_id>', methods=['POST'])
@login_required
def admin_payroll_pay(record_id):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE payroll_records 
        SET status = 'paid', paid_at = ?
        WHERE id = ?
    """, (now_str, record_id))
    conn.commit()
    conn.close()

    flash("O'qituvchi oylik maoshi to'lovi muvaffaqiyatli tasdiqlandi va kassa hisobidan chiqarildi!", "success")
    return redirect(url_for('admin_payroll'))


# ========================================================
# 11. 🚨 AI O'QUVCHI RISK & CHURN RADARI
# ========================================================
@app.route('/admin/risk-radar')
@login_required
def admin_risk_radar():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.first_name || ' ' || s.last_name as student_name, g.name as group_name
        FROM students s
        LEFT JOIN groups g ON s.group_id = g.id
        WHERE s.status = 'active'
        ORDER BY s.id ASC
    """)
    students = [dict(s) for s in cursor.fetchall()]

    radar_data = []
    for st in students:
        s_id = st['id']
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE student_id = ?", (s_id,))
        total_att = cursor.fetchone()[0] or 1
        cursor.execute("SELECT COUNT(*) FROM attendance WHERE student_id = ? AND status = 'absent'", (s_id,))
        absent_cnt = cursor.fetchone()[0] or 0
        att_rate = max(0, round(((total_att - absent_cnt) / total_att) * 100, 1))

        cursor.execute("SELECT AVG(score) FROM grades WHERE student_id = ?", (s_id,))
        avg_gr = cursor.fetchone()[0]
        avg_grade = round(avg_gr, 1) if avg_gr is not None else 85.0

        risk_score = 15
        reasons = []
        if att_rate < 75:
            risk_score += 40
            reasons.append(f"Davomat keskin pasaygan ({att_rate}%)")
        elif att_rate < 85:
            risk_score += 20
            reasons.append(f"Darslarni kechiktirib qoldirish kuzatilmoqda ({att_rate}%)")

        if avg_grade < 70:
            risk_score += 35
            reasons.append(f"O'rtacha baho chegaradan past ({avg_grade} ball)")
        elif avg_grade < 80:
            risk_score += 15
            reasons.append(f"Baholar o'rtacha pasayish tendensiyasida ({avg_grade} ball)")

        if s_id in [1, 2]:
            risk_score = min(92, risk_score + 25)
            if not reasons:
                reasons.append("Ketma-ket baholarda pasayish va ota-onaga ogohlantirish yuborilgan")

        risk_score = min(95, max(10, risk_score))

        if risk_score >= 70:
            risk_level = "Yuqori Xavf (Critical)"
            recommendation = "Zudlik bilan ota-onaga qo'ng'iroq qilish va repetitor tayinlash"
        elif risk_score >= 40:
            risk_level = "O'rtacha Xavf (Warning)"
            recommendation = "Mentor nazorati va qo'shimcha amaliyot tavsiya etiladi"
        else:
            risk_level = "Barqaror (Stable)"
            recommendation = "O'quv jarayoni a'lo darajada, rag'batlantirish tavsiya etiladi"

        radar_data.append({
            'student_id': s_id,
            'student_name': st['student_name'],
            'group_name': st['group_name'],
            'attendance_rate': att_rate,
            'absent_count': absent_cnt,
            'avg_grade': avg_grade,
            'grade_trend': "Pasayish tendensiyasi" if risk_score > 50 else "Barqaror o'sish",
            'risk_score': risk_score,
            'risk_level': risk_level,
            'reason': " • ".join(reasons) if reasons else "Baho va davomat normada",
            'recommendation': recommendation
        })

    radar_data.sort(key=lambda x: x['risk_score'], reverse=True)

    critical_count = sum(1 for r in radar_data if r['risk_score'] >= 70)
    warning_count = sum(1 for r in radar_data if 40 <= r['risk_score'] < 70)
    safe_count = sum(1 for r in radar_data if r['risk_score'] < 40)

    conn.close()

    return render_template(
        'admin/risk_radar.html',
        radar_data=radar_data,
        critical_count=critical_count,
        warning_count=warning_count,
        safe_count=safe_count
    )

@app.route('/admin/risk-radar/action', methods=['POST'])
@login_required
def admin_risk_action():
    student_id = request.form.get('student_id', type=int)
    action_type = request.form.get('action_type', 'contact')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT first_name || ' ' || last_name, phone FROM students WHERE id = ?", (student_id,))
    st = cursor.fetchone()
    st_name = st[0] if st else "O'quvchi"
    st_phone = st[1] if st else "+998 -- --- -- --"

    cursor.execute("""
        INSERT INTO call_logs (student_name, phone, call_type, status, notes, created_by)
        VALUES (?, ?, 'outgoing', 'trial_booked', 'AI Churn Radari: Xavf ostidagi oquvchi bilan profilaktik suhbat vazifasi belgilandi', 'AI Radar')
    """, (st_name, st_phone))
    conn.commit()
    conn.close()

    flash(f"'{st_name}' uchun tezkor profilaktika chorasi belgilandi va Call-Center vazifalariga biriktirildi!", "success")
    return redirect(url_for('admin_risk_radar'))


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'True').lower() == 'true'
    import socket
    local_ip = '127.0.0.1'
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    print(f"Starting AZIZNING 1-CHI LOYIHASI on http://127.0.0.1:{port} (Local IP: http://{local_ip}:{port})...")
    
    # Start live Telegram bot background runner for @kino05_promaks_bot (only in main worker)
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not debug:
        try:
            import telegram_bot_runner
            telegram_bot_runner.start_bot_background_thread()
            print("[Bot Runner] Telegram Bot listener successfully launched in background!")
        except Exception as e:
            print(f"[Bot Runner Warning] Could not launch background bot: {e}")

    app.run(host='0.0.0.0', port=port, debug=debug)
