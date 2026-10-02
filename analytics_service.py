from datetime import datetime, timedelta
from database import get_db_connection
from telegram_service import (
    get_setting,
    send_student_grade_notification,
    send_parent_grade_notification,
    send_student_warning_notification,
    send_parent_warning_notification,
    send_student_expulsion_notification
)

def get_student_stats(student_id):
    """
    Returns comprehensive stats for a single student:
    overall_avg, today_avg, weekly_avg, monthly_avg, total_grades, attendance_rate, active_warnings
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Total and overall average
    cursor.execute('''
    SELECT COUNT(*), AVG(score), MAX(score), MIN(score)
    FROM grades
    WHERE student_id = ?
    ''', (student_id,))
    row = cursor.fetchone()
    total_grades = row[0] or 0
    overall_avg = round(row[1], 1) if row[1] is not None else None
    max_score = round(row[2], 1) if row[2] is not None else None
    min_score = round(row[3], 1) if row[3] is not None else None

    # Today's average
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute('''
    SELECT AVG(score) FROM grades
    WHERE student_id = ? AND assessment_date = ?
    ''', (student_id, today_str))
    today_row = cursor.fetchone()
    today_avg = round(today_row[0], 1) if today_row and today_row[0] is not None else None

    # Weekly average (last 7 days)
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    cursor.execute('''
    SELECT AVG(score) FROM grades
    WHERE student_id = ? AND assessment_date >= ?
    ''', (student_id, week_ago))
    week_row = cursor.fetchone()
    weekly_avg = round(week_row[0], 1) if week_row and week_row[0] is not None else None

    # Monthly average (last 30 days)
    month_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    cursor.execute('''
    SELECT AVG(score) FROM grades
    WHERE student_id = ? AND assessment_date >= ?
    ''', (student_id, month_ago))
    month_row = cursor.fetchone()
    monthly_avg = round(month_row[0], 1) if month_row and month_row[0] is not None else None

    # Attendance rate
    cursor.execute('''
    SELECT status, COUNT(*) FROM attendance
    WHERE student_id = ?
    GROUP BY status
    ''', (student_id,))
    att_rows = cursor.fetchall()
    total_att = 0
    present_pts = 0
    for r in att_rows:
        count = r[1]
        total_att += count
        if r[0] == 'present':
            present_pts += count
        elif r[0] == 'late':
            present_pts += count * 0.8
        elif r[0] == 'excused':
            present_pts += count * 0.9

    attendance_rate = round((present_pts / total_att) * 100, 1) if total_att > 0 else 100.0

    # Active warnings
    cursor.execute('''
    SELECT COUNT(*) FROM warnings
    WHERE student_id = ? AND resolved = 0
    ''', (student_id,))
    active_warnings = cursor.fetchone()[0]

    conn.close()

    return {
        'total_grades': total_grades,
        'overall_avg': overall_avg if overall_avg is not None else 0.0,
        'today_avg': today_avg,
        'weekly_avg': weekly_avg,
        'monthly_avg': monthly_avg,
        'max_score': max_score,
        'min_score': min_score,
        'attendance_rate': attendance_rate,
        'active_warnings': active_warnings
    }

def analyze_student_performance(student_id):
    """
    Evaluates student performance according to warning criteria:
    1. Consecutive decreasing grades (e.g. 3 in a row)
    2. Overall average falls below threshold (e.g. < 70)
    3. Drop percentage (e.g. > 10% decline)
    
    If triggered, logs warning and sends Telegram notification.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get student info
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    if not student:
        conn.close()
        return None

    # Get settings
    warning_threshold = float(get_setting('warning_threshold', '70'))
    warning_drop_percent = float(get_setting('warning_drop_percent', '10'))
    consecutive_threshold = int(get_setting('warning_consecutive_drops', '3'))

    # Fetch all grades in chronological order
    cursor.execute('''
    SELECT id, score, assessment_date, subject, assessment_type, comment
    FROM grades
    WHERE student_id = ?
    ORDER BY assessment_date ASC, id ASC
    ''', (student_id,))
    grades = cursor.fetchall()

    if len(grades) < 2:
        conn.close()
        return None

    scores = [g['score'] for g in grades]
    subjects_set = list(set(g['subject'] for g in grades))
    subjects_str = ", ".join(subjects_set)

    current_avg = sum(scores) / len(scores)
    # Previous average (excluding the very latest grade)
    previous_avg = sum(scores[:-1]) / len(scores[:-1])
    drop_amount = previous_avg - current_avg

    warning_triggered = False
    warning_type = None
    trigger_reason = None

    # Check 1: Consecutive drop check
    if len(scores) >= consecutive_threshold:
        last_n = scores[-consecutive_threshold:]
        # Check if strictly decreasing: last_n[0] > last_n[1] > last_n[2]...
        is_consecutive_drop = all(last_n[i] < last_n[i-1] for i in range(1, len(last_n)))
        if is_consecutive_drop:
            warning_triggered = True
            warning_type = 'consecutive_drop'
            scores_str = " -> ".join(str(int(s) if s.is_integer() else s) for s in last_n)
            trigger_reason = f"Baholar {consecutive_threshold} marta ketma-ket pasaydi ({scores_str})."

    # Check 2: Average below threshold
    if not warning_triggered and current_avg < warning_threshold:
        warning_triggered = True
        warning_type = 'threshold_below'
        trigger_reason = f"O'rtacha baho belgilangan chegara ({warning_threshold} ball)dan pastga tushdi ({round(current_avg, 1)} ball)."

    # Check 3: Percentage drop
    if not warning_triggered and previous_avg > 0 and (drop_amount / previous_avg * 100) >= warning_drop_percent:
        warning_triggered = True
        warning_type = 'percent_drop'
        percent_val = round((drop_amount / previous_avg * 100), 1)
        trigger_reason = f"Natija oldingi o'rtachaga nisbatan {percent_val}% ga keskin pasaydi."

    warning_record = None
    if warning_triggered:
        # Check if unresolved warning already exists
        cursor.execute('''
        SELECT id FROM warnings 
        WHERE student_id = ? AND resolved = 0 AND warning_type = ?
        ''', (student_id, warning_type))
        existing = cursor.fetchone()

        if existing:
            cursor.execute('''
            UPDATE warnings SET
                previous_avg = ?, current_avg = ?, drop_amount = ?, subjects = ?, trigger_reason = ?, created_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (round(previous_avg, 1), round(current_avg, 1), round(drop_amount, 1), subjects_str, trigger_reason, existing['id']))
            conn.commit()

            warning_record = {
                'id': existing['id'],
                'student_id': student_id,
                'warning_type': warning_type,
                'previous_avg': round(previous_avg, 1),
                'current_avg': round(current_avg, 1),
                'drop_amount': round(drop_amount, 1),
                'subjects': subjects_str,
                'trigger_reason': trigger_reason
            }
        else:
            cursor.execute('''
            INSERT INTO warnings (student_id, warning_type, previous_avg, current_avg, drop_amount, subjects, trigger_reason, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ''', (student_id, warning_type, round(previous_avg, 1), round(current_avg, 1), round(drop_amount, 1), subjects_str, trigger_reason))
            conn.commit()

            warning_id = cursor.lastrowid
            warning_record = {
                'id': warning_id,
                'student_id': student_id,
                'warning_type': warning_type,
                'previous_avg': round(previous_avg, 1),
                'current_avg': round(current_avg, 1),
                'drop_amount': round(drop_amount, 1),
                'subjects': subjects_str,
                'trigger_reason': trigger_reason
            }

        # Send Telegram alerts to student and parent
        student_dict = dict(student)
        send_student_warning_notification(student_dict, previous_avg, current_avg, drop_amount)
        send_parent_warning_notification(student_dict, previous_avg, current_avg, drop_amount)

    conn.close()
    return warning_record

def record_new_grade(student_id, subject, assessment_date, assessment_type, score, comment, created_by=None):
    """
    Records a new grade in DB, notifies student & parent via Telegram,
    and runs the automated grade drop analysis.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
    INSERT INTO grades (student_id, subject, assessment_date, assessment_type, score, comment, created_by)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (student_id, subject, assessment_date, assessment_type, float(score), comment, created_by))
    conn.commit()
    grade_id = cursor.lastrowid

    # Fetch student
    cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cursor.fetchone()
    conn.close()

    if not student:
        return grade_id, None

    student_dict = dict(student)
    grade_dict = {
        'id': grade_id,
        'subject': subject,
        'assessment_date': assessment_date,
        'assessment_type': assessment_type,
        'score': float(score),
        'comment': comment
    }

    # Calculate current average for student
    stats = get_student_stats(student_id)
    current_avg = stats['overall_avg']

    # 1. Check for automatic expulsion if score < 10
    is_expelled = False
    if float(score) < 10:
        is_expelled = True
        conn_exp = get_db_connection()
        cur_exp = conn_exp.cursor()
        cur_exp.execute("UPDATE students SET status = 'inactive' WHERE id = ?", (student_id,))
        cur_exp.execute('''
        INSERT INTO warnings (student_id, warning_type, previous_avg, current_avg, drop_amount, subjects, trigger_reason, resolved)
        VALUES (?, 'low_score_expulsion', ?, ?, ?, ?, ?, 0)
        ''', (student_id, current_avg or 0, float(score), (current_avg or 10) - float(score), subject, f"O'quvchi 10 balldan past ({score} ball) to'plagani sababli avtomatik chetlashtirildi."))
        conn_exp.commit()
        conn_exp.close()

        # Send urgent expulsion Telegram alerts to student & parent
        send_student_expulsion_notification(student_dict, float(score), subject, assessment_date)

    # 2. Dispatch Telegram Notifications for new grade
    send_student_grade_notification(student_dict, grade_dict)
    send_parent_grade_notification(student_dict, grade_dict, current_avg)

    # 3. Run automated grade drop analysis
    warning = analyze_student_performance(student_id)

    return grade_id, warning, is_expelled

def get_dashboard_data():
    """
    Calculates summary data and Chart.js datasets for the main dashboard:
    - 6 KPI numbers
    - Baholar statistikasi (Distribution)
    - O‘quvchilar natijalari (Categories)
    - Guruhlar bo‘yicha o‘rtacha natija
    - Baholarning vaqt bo‘yicha o‘zgarishi (Timeline)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # KPI 1: Total students
    cursor.execute("SELECT COUNT(*) FROM students")
    total_students = cursor.fetchone()[0]

    # KPI 2: Active students
    cursor.execute("SELECT COUNT(*) FROM students WHERE status = 'active'")
    active_students = cursor.fetchone()[0]

    # KPI 3: Groups
    cursor.execute("SELECT COUNT(*) FROM groups WHERE active = 1")
    total_groups = cursor.fetchone()[0]

    # KPI 4: Teachers
    cursor.execute("SELECT COUNT(*) FROM teachers WHERE active = 1")
    total_teachers = cursor.fetchone()[0]

    # KPI 5: Overall average grade
    cursor.execute("SELECT AVG(score) FROM grades")
    avg_grade_row = cursor.fetchone()
    overall_avg_grade = round(avg_grade_row[0], 1) if avg_grade_row and avg_grade_row[0] else 0.0

    # KPI 6: Warned students count (unresolved warnings)
    cursor.execute("SELECT COUNT(DISTINCT student_id) FROM warnings WHERE resolved = 0")
    warned_students_count = cursor.fetchone()[0]

    # Chart 1: Baholar statistikasi (Distribution across buckets: <60, 60-69, 70-79, 80-89, 90-100)
    cursor.execute('''
    SELECT 
        SUM(CASE WHEN score < 60 THEN 1 ELSE 0 END) as b1,
        SUM(CASE WHEN score >= 60 AND score < 70 THEN 1 ELSE 0 END) as b2,
        SUM(CASE WHEN score >= 70 AND score < 80 THEN 1 ELSE 0 END) as b3,
        SUM(CASE WHEN score >= 80 AND score < 90 THEN 1 ELSE 0 END) as b4,
        SUM(CASE WHEN score >= 90 THEN 1 ELSE 0 END) as b5
    FROM grades
    ''')
    dist_row = cursor.fetchone()
    grade_distribution = [
        dist_row[0] or 0,
        dist_row[1] or 0,
        dist_row[2] or 0,
        dist_row[3] or 0,
        dist_row[4] or 0
    ]

    # Chart 2: O'quvchilar natijalari kategoriyalari
    # A'lo (>=85), Yaxshi (70-84), Qoniqarli (60-69), Yordam kerak (<60)
    cursor.execute('''
    SELECT 
        s.id,
        AVG(g.score) as avg_score
    FROM students s
    JOIN grades g ON s.id = g.student_id
    GROUP BY s.id
    ''')
    student_avgs = cursor.fetchall()
    cat_excellent = 0 # >= 85
    cat_good = 0      # 70 - 84
    cat_satisfactory = 0 # 60 - 69
    cat_need_help = 0    # < 60
    for row in student_avgs:
        sc = row['avg_score']
        if sc >= 85:
            cat_excellent += 1
        elif sc >= 70:
            cat_good += 1
        elif sc >= 60:
            cat_satisfactory += 1
        else:
            cat_need_help += 1

    student_categories = [cat_excellent, cat_good, cat_satisfactory, cat_need_help]

    # Chart 3: Guruhlar bo‘yicha o‘rtacha natija
    cursor.execute('''
    SELECT 
        gr.name as group_name,
        ROUND(AVG(g.score), 1) as avg_score,
        COUNT(DISTINCT s.id) as student_count
    FROM groups gr
    LEFT JOIN students s ON gr.id = s.group_id
    LEFT JOIN grades g ON s.id = g.student_id
    GROUP BY gr.id
    ORDER BY avg_score DESC
    ''')
    group_stats = cursor.fetchall()
    group_names = [r['group_name'] for r in group_stats]
    group_averages = [r['avg_score'] or 0 for r in group_stats]

    # Chart 4: Baholarning vaqt bo‘yicha o‘zgarishi (Historical dates)
    cursor.execute('''
    SELECT 
        assessment_date,
        ROUND(AVG(score), 1) as avg_score,
        COUNT(*) as count
    FROM grades
    GROUP BY assessment_date
    ORDER BY assessment_date ASC
    LIMIT 10
    ''')
    timeline_rows = cursor.fetchall()
    timeline_dates = [r['assessment_date'] for r in timeline_rows]
    timeline_scores = [r['avg_score'] for r in timeline_rows]

    # Recent warnings
    cursor.execute('''
    SELECT 
        w.*,
        s.first_name,
        s.last_name,
        s.phone,
        c.title as course_title,
        gr.name as group_name
    FROM warnings w
    JOIN students s ON w.student_id = s.id
    LEFT JOIN courses c ON s.course_id = c.id
    LEFT JOIN groups gr ON s.group_id = gr.id
    WHERE w.resolved = 0
    ORDER BY w.created_at DESC
    LIMIT 5
    ''')
    recent_warnings = [dict(r) for r in cursor.fetchall()]

    # Recent grades
    cursor.execute('''
    SELECT 
        g.*,
        s.first_name,
        s.last_name,
        c.title as course_title
    FROM grades g
    JOIN students s ON g.student_id = s.id
    LEFT JOIN courses c ON s.course_id = c.id
    ORDER BY g.created_at DESC, g.id DESC
    LIMIT 6
    ''')
    recent_grades = [dict(r) for r in cursor.fetchall()]

    conn.close()

    return {
        'kpi': {
            'total_students': total_students,
            'active_students': active_students,
            'total_groups': total_groups,
            'total_teachers': total_teachers,
            'overall_avg_grade': overall_avg_grade,
            'warned_students_count': warned_students_count
        },
        'charts': {
            'grade_distribution': {
                'labels': ["< 60 ball", "60 - 69 ball", "70 - 79 ball", "80 - 89 ball", "90 - 100 ball"],
                'data': grade_distribution
            },
            'student_categories': {
                'labels': ["A'lo (85-100)", "Yaxshi (70-84)", "Qoniqarli (60-69)", "Nazoratda (<60)"],
                'data': student_categories
            },
            'group_averages': {
                'labels': group_names,
                'data': group_averages
            },
            'timeline': {
                'labels': timeline_dates,
                'data': timeline_scores
            }
        },
        'recent_warnings': recent_warnings,
        'recent_grades': recent_grades
    }
