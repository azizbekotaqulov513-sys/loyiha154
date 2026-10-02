import unittest
import json
from app import app
from database import get_db_connection, init_db, seed_db
import analytics_service

class AntigravityPlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_db()
        cls.client = app.test_client()

    def test_01_public_landing_page(self):
        """Test public website renders all mandatory sections and content in Uzbek."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Brand and Hero
        self.assertIn("ANTIGRAVITY", html)
        self.assertIn("Kelajagingizni", html)
        self.assertIn("bugundan boshlang!", html)
        self.assertIn("zamonaviy bilim, kuchli ustozlar va yuqori natijalar maskani", html)
        self.assertIn("Kurslarni ko‘rish", html)
        self.assertIn("Kursga yozilish", html)

        # Counters
        self.assertIn("1000", html)
        self.assertIn("30", html)
        self.assertIn("95", html)

        # Courses
        self.assertIn("Ingliz tili", html)
        self.assertIn("Matematika", html)
        self.assertIn("IELTS", html)
        self.assertIn("CEFR", html)
        self.assertIn("IT / Dasturlash", html)
        self.assertIn("Robototexnika", html)

        # Teachers, FAQ, Contact
        self.assertIn("Ustozlar", html)
        self.assertIn("FAQ", html)
        self.assertIn("Biz bilan Bog'laning", html)

    def test_02_public_enroll_api(self):
        """Test course lead registration API."""
        payload = {
            'full_name': 'Test O\'quvchi',
            'phone': '+998 90 999 00 11',
            'course_name': 'IELTS',
            'message': 'Sinov darsiga yozilmoqchiman'
        }
        res = self.client.post('/api/enroll', json=payload)
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])

        # Verify in DB
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM leads WHERE full_name = ?", ('Test O\'quvchi',))
        lead = c.fetchone()
        conn.close()
        self.assertIsNotNone(lead)
        self.assertEqual(lead['phone'], '+998 90 999 00 11')

    def test_03_admin_authentication_and_dashboard(self):
        """Test admin login and dashboard access."""
        # Unauthenticated access to dashboard should redirect to /login
        res = self.client.get('/admin/dashboard')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

        # Login with valid superadmin credentials
        login_res = self.client.post('/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)
        html = login_res.data.decode('utf-8')
        self.assertIn("Dashboard", html)
        self.assertIn("Jami O‘quvchilar", html)
        self.assertIn("Baholar Statistikasi", html)

    def test_04_student_management_crud(self):
        """Test student listing, profile, and CRUD."""
        # Student list
        res = self.client.get('/admin/students')
        self.assertEqual(res.status_code, 200)
        self.assertIn("O‘quvchilarni Boshqarish", res.data.decode('utf-8'))

        # Student detail profile
        res_detail = self.client.get('/admin/students/1')
        self.assertEqual(res_detail.status_code, 200)
        detail_html = res_detail.data.decode('utf-8')
        self.assertIn("O‘quvchi Profili", detail_html)
        self.assertIn("Baholar Tarixi", detail_html)
        self.assertIn("Telegram Chat ID", detail_html)

    def test_05_automatic_warning_and_grade_analysis(self):
        """Test automatic drop detection when scores decrease."""
        # Add a student for test
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
        INSERT INTO students (first_name, last_name, phone, status)
        VALUES ('Sinaov', 'Pasayuvchi', '+998 90 000 00 00', 'active')
        ''')
        student_id = c.lastrowid
        conn.commit()
        conn.close()

        # Record 4 consecutive dropping grades: 92 -> 85 -> 74 -> 60
        g1, w1 = analytics_service.record_new_grade(student_id, 'Fizika', '2026-09-01', 'Test', 92.0, 'Yaxshi', 1)
        g2, w2 = analytics_service.record_new_grade(student_id, 'Fizika', '2026-09-02', 'Test', 85.0, 'O\'rtacha', 1)
        g3, w3 = analytics_service.record_new_grade(student_id, 'Fizika', '2026-09-03', 'Test', 74.0, 'Pasaydi', 1)
        g4, w4 = analytics_service.record_new_grade(student_id, 'Fizika', '2026-09-04', 'Test', 60.0, 'Yomon', 1)

        # Verify warning was triggered!
        self.assertIsNotNone(w4, "Automatic warning must be triggered on consecutive drop and threshold dip!")
        self.assertIn('consecutive_drop', [w4.get('warning_type')] if w4 else [])

        # Check in DB warnings
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM warnings WHERE student_id = ? AND resolved = 0", (student_id,))
        warning_row = c.fetchone()
        conn.close()
        self.assertIsNotNone(warning_row)
        self.assertGreater(warning_row['drop_amount'], 0)

    def test_06_role_based_security_for_teachers(self):
        """Verify that teachers cannot access superadmin settings."""
        # Logout superadmin
        self.client.get('/logout')

        # Login as teacher
        self.client.post('/login', data={
            'username': 'ustoz',
            'password': 'ustoz123'
        }, follow_redirects=True)

        # Attempt to access sensitive settings
        res = self.client.get('/admin/settings', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.request.path, '/admin/dashboard')
        html = res.data.decode('utf-8')
        # Should be redirected to dashboard with warning flash
        self.assertIn("huquq", html)

    def test_07_courses_and_groups_crud(self):
        """Test courses and groups management."""
        self.client.get('/logout')
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'})

        # Create Course
        res = self.client.post('/admin/courses/create', data={
            'title': 'Koreys Tili',
            'slug': 'koreys-tili',
            'description': 'Topik I va II darajalariga tayyorlov',
            'level': 'Beginner - Topik',
            'duration': '6 oy',
            'price': '700,000 so\'m',
            'icon': 'language',
            'color': 'teal'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Koreys Tili", res.data.decode('utf-8'))

        # Create Group
        res_g = self.client.post('/admin/groups/create', data={
            'name': 'Korean-Starter-1',
            'course_id': '1',
            'teacher_id': '1',
            'room': 'Xona 104',
            'schedule': 'Sesh-Pay-Shan 10:00'
        }, follow_redirects=True)
        self.assertEqual(res_g.status_code, 200)
        self.assertIn("Korean-Starter-1", res_g.data.decode('utf-8'))

    def test_08_attendance_and_warnings_resolution(self):
        """Test attendance submission and warning resolution."""
        self.client.get('/logout')
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'})

        # Save Attendance
        res_att = self.client.post('/admin/attendance/save', data={
            'group_id': '1',
            'date': '2026-09-04',
            'status_3': 'present',
            'note_3': 'Darsda faol',
            'status_5': 'present',
            'note_5': 'Uyga vazifa a\'lo'
        }, follow_redirects=True)
        self.assertEqual(res_att.status_code, 200)

        # Resolve Warning
        res_warn = self.client.post('/admin/warnings/1/resolve', follow_redirects=True)
        self.assertEqual(res_warn.status_code, 200)
        
        # Check resolved list
        res_resolved = self.client.get('/admin/warnings?status=resolved')
        self.assertIn("Hal Qilindi", res_resolved.data.decode('utf-8'))

    def test_09_settings_threshold_update(self):
        """Test configuring warning threshold and bot token in Settings."""
        self.client.get('/logout')
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'})

        res = self.client.post('/admin/settings', data={
            'telegram_bot_token': '8968202615:AAECQov89mhX1UFIL_GaDRP2FGqE6cxstwM',
            'telegram_bot_name': '@kino05_promaks_bot',
            'telegram_bot_url': 'https://t.me/kino05_promaks_bot',
            'notification_grade_enabled': 'true',
            'notification_parent_grade_enabled': 'true',
            'notification_warning_enabled': 'true',
            'notification_parent_warning_enabled': 'true',
            'warning_threshold': '72',
            'warning_drop_percent': '12',
            'warning_consecutive_drops': '3',
            'center_name': 'ANTIGRAVITY Ta\'lim Markazi',
            'center_phone': '+998 71 200 45 45',
            'center_telegram': '@kino05_promaks_bot',
            'center_instagram': '@antigravity.uz',
            'center_address': 'Toshkent sh., Yunusobod tumani',
            'center_work_hours': '08:00 - 20:00'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Verify DB updated
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'warning_threshold'")
        self.assertEqual(c.fetchone()[0], '72')
        conn.close()

    def test_10_lead_conversion_to_student(self):
        """Test accepting a lead and enrolling them directly into classes and group."""
        # 1. Create a fresh lead
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''
        INSERT INTO leads (full_name, phone, course_name, message, status)
        VALUES ('Javlon Bekmurodov', '+998 90 555 44 33', 'IELTS', 'Kechki guruhga yozilmoqchiman', 'new')
        ''')
        lead_id = c.lastrowid
        conn.commit()
        conn.close()

        # 2. Login as admin and convert lead
        self.client.get('/logout')
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'})

        res_convert = self.client.post(f'/admin/leads/{lead_id}/convert', data={
            'first_name': 'Javlon',
            'last_name': 'Bekmurodov',
            'phone': '+998 90 555 44 33',
            'birth_date': '2007-06-15',
            'course_id': '3',
            'group_id': '1',
            'teacher_id': '1',
            'telegram_chat_id': '555444333',
            'parent_name': 'Sobir Bekmurodov',
            'parent_phone': '+998 90 555 00 11',
            'parent_telegram_chat_id': '999888777'
        }, follow_redirects=True)
        self.assertEqual(res_convert.status_code, 200)

        # 3. Verify lead is marked 'enrolled'
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT status FROM leads WHERE id = ?", (lead_id,))
        self.assertEqual(c.fetchone()[0], 'enrolled')

        # 4. Verify student is created in students table with group 1
        c.execute("SELECT id, course_id, group_id, telegram_chat_id FROM students WHERE phone = '+998 90 555 44 33'")
        student = c.fetchone()
        self.assertIsNotNone(student)
        self.assertEqual(student['group_id'], 1)
        self.assertEqual(student['telegram_chat_id'], '555444333')

        # 5. Verify student appears in group 1 attendance query
        c.execute("SELECT id FROM students WHERE group_id = 1 AND phone = '+998 90 555 44 33'")
        self.assertIsNotNone(c.fetchone())
        conn.close()

    def test_11_telegram_bot_token_and_kino05_promaks_bot(self):
        """Test that @kino05_promaks_bot token is active, valid, and configured."""
        import telegram_service
        token = telegram_service.get_bot_token()
        self.assertTrue(len(token) > 20)
        self.assertIn("8968202615", token)
        self.assertEqual(telegram_service.get_bot_username(), '@kino05_promaks_bot')

        # Check settings table
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'telegram_bot_name'")
        self.assertEqual(c.fetchone()[0], '@kino05_promaks_bot')
        conn.close()

    def test_12_student_teacher_messaging_and_admin_chat(self):
        """Test student can send message to teacher and teacher can reply."""
        # 1. Login as Student 1 (Aziz Karimov)
        self.client.get('/student/logout')
        res_login = self.client.post('/student/login', data={'student_identifier': '1'}, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)

        # 2. Student sends message to teacher
        send_res = self.client.post('/api/chat/teacher/send', data={
            'message': 'Assalomu alaykum ustoz, uy vazifasi yuborildi!'
        })
        self.assertEqual(send_res.status_code, 200)
        data = json.loads(send_res.data)
        self.assertTrue(data['success'])

        # 3. Retrieve student's conversation
        msg_res = self.client.get('/api/chat/teacher/messages')
        self.assertEqual(msg_res.status_code, 200)
        msg_data = json.loads(msg_res.data)
        self.assertTrue(msg_data['success'])
        self.assertTrue(any("Assalomu alaykum ustoz" in m['message'] for m in msg_data['messages']))

        # 4. Login as admin/teacher and view teacher chat
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'})
        chat_page = self.client.get('/admin/teacher-chat?student_id=1')
        self.assertEqual(chat_page.status_code, 200)
        self.assertIn("O‘quvchilar Savol-Javoblari", chat_page.data.decode('utf-8'))

        # 5. Teacher replies to student
        reply_res = self.client.post('/api/admin/teacher-chat/send', data={
            'student_id': '1',
            'message': 'Va alaykum assalom Aziz! Vazifangni ko\'rib chiqdim, yaxshi bajarilgan.'
        })
        self.assertEqual(reply_res.status_code, 200)
        reply_data = json.loads(reply_res.data)
        self.assertTrue(reply_data['success'])

        # 6. Verify teacher message is in DB
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM teacher_messages WHERE student_id = 1 AND sender_type = 'teacher' ORDER BY id DESC LIMIT 1")
        last_reply = c.fetchone()
        self.assertIsNotNone(last_reply)
        self.assertIn("Va alaykum assalom", last_reply['message'])
        conn.close()

    def test_13_classmates_group_chat(self):
        """Test classmates group discussion sending and receiving."""
        # 1. Login as Student 1 (group 2: Math-Olimpiada-1)
        self.client.get('/student/logout')
        self.client.post('/student/login', data={'student_identifier': '1'})

        # 2. Send group message
        grp_send = self.client.post('/api/chat/group/send', data={
            'message': 'Hammaga salom! Ertangi dars soat nechada?'
        })
        self.assertEqual(grp_send.status_code, 200)
        grp_data = json.loads(grp_send.data)
        self.assertTrue(grp_data['success'])

        # 3. Retrieve group messages
        grp_msgs = self.client.get('/api/chat/group/messages')
        self.assertEqual(grp_msgs.status_code, 200)
        msgs_data = json.loads(grp_msgs.data)
        self.assertTrue(msgs_data['success'])
        self.assertTrue(any("Ertangi dars soat nechada" in m['message'] for m in msgs_data['messages']))

        # 4. Admin accesses group chat
        self.client.post('/login', data={'username': 'admin', 'password': 'admin123'})
        admin_grp = self.client.get('/admin/groups/2/chat')
        self.assertEqual(admin_grp.status_code, 200)
        self.assertIn("Guruh Chati", admin_grp.data.decode('utf-8'))

        # 5. Admin posts announcement to group
        admin_grp_send = self.client.post('/api/admin/groups/2/chat/send', data={
            'message': 'Ertangi dars soat 14:00 da 105-xonada bo\'lib o\'tadi.'
        })
        self.assertEqual(admin_grp_send.status_code, 200)
        admin_grp_data = json.loads(admin_grp_send.data)
        self.assertTrue(admin_grp_data['success'])

    def test_14_student_update_telegram_chat_id(self):
        """Test student can update their Telegram Chat ID from cabinet."""
        self.client.get('/student/logout')
        self.client.post('/student/login', data={'student_identifier': '1'})

        res = self.client.post('/api/student/update-telegram', data={
            'telegram_chat_id': '777888999'
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(data['success'])

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT telegram_chat_id FROM students WHERE id = 1")
        self.assertEqual(c.fetchone()[0], '777888999')
        conn.close()

if __name__ == '__main__':
    unittest.main()
