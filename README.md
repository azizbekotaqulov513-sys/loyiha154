# 🚀 ANTIGRAVITY — Zamonaviy Ta'lim Markazi Platformasi

ANTIGRAVITY ta'lim markazining to'laqonli, zamonaviy va xavfsiz boshqaruv ekotizimi: **Public Website + Admin Panel + Student Management System + Telegram Bot Integratsiyasi + Avtomatik Baho Pasayishini Aniqlash Tizimi**.

Platforma to'liq **O'zbek (Lotin)** tilida yaratilgan bo'lib, eng so'nggi zamonaviy dizayn (Dark Navy, Electric Blue neon, Glassmorphism, Chart.js grafiklar) va yuqori xavfsizlik standartlariga javob beradi.

---

## 🌟 Asosiy Imkoniyatlar

### 1. Jamoat Sayti (Public Website)
- **Header**: ANTIGRAVITY logotipi, asosiy menyu, "Kursga yozilish" tugmasi, sticky navbar, mobil qurilmalar uchun responsive menyu.
- **Hero**: *"Kelajagingizni bugundan boshlang!"*, animatsiyali statistika ko'rsatkichlari (*1000+ O‘quvchi, 30+ Ustoz, 95% Natija*).
- **Kurslar**: *Ingliz tili, Matematika, IELTS, CEFR, IT / Dasturlash, Robototexnika* kurslari, darajasi, narxlari va "Batafsil" hamda "Yozilish" interaktiv modallari.
- **Ustozlar**: Kuchli pedagoglar jamoasi, tajribasi, fanlari va bio ma'lumotlari.
- **Natijalar & Yutuqlar**: IELTS 8.5+, Respublika olimpiada sovrindorlari, IT loyihalar.
- **Afzalliklar**: 24/7 Telegram monitoring, AI tahlil, mini-guruhlar, zamonaviy laboratoriya.
- **O'quvchilar fikrlari**: Haqiqiy o'quvchilar va ota-onalar tavsiyalari.
- **FAQ**: Kurslar, sinov darslari va to'lovlar bo'yicha tez-tez beriladigan savollar akkordeoni.
- **Kontakt & Ariza**: Telefon, Telegram, Instagram, manzil, ish vaqti hamda saytdan to'g'ridan-to'g'ri ariza qoldirish formasi.

### 2. Admin Panel & SaaS Dashboard
- **6 ta Asosiy KPI Ko'rsatkich**: Jami o'quvchilar, Faol o'quvchilar, Guruhlar, Ustozlar, O'rtacha baho, Ogohlantirilgan o'quvchilar.
- **4 ta Interaktiv Chart.js Diagrammasi**:
  1. *Baholar statistikasi* (ballar taqsimoti)
  2. *O‘quvchilar natijalari* (kategoriyalar: A'lo, Yaxshi, Qoniqarli, Nazoratda)
  3. *Guruhlar bo‘yicha o‘rtacha natija* (guruhlar reytingi)
  4. *Baholarning vaqt bo‘yicha o‘zgarishi* (o'rtacha ball dinamikasi)
- **Tezkor Natijasi Pasayganlar va So'nggi Baholar ro'yxati**.

### 3. O‘quvchilarni Boshqarish (Student Management)
- O'quvchi qo'shish, tahrirlash, o'chirish, qidirish, kurs/guruh/holat bo'yicha filtrlash.
- **To'laqonli O'quvchi Profili**:
  - Shaxsiy ma'lumotlar, Kurs, Guruh, Ustoz
  - O'quvchi Telegram Chat ID, Ota-onasi ismi, telefoni va ota-onasi Telegram Chat ID
  - O'rtacha baho, Bugungi, Haftalik va Oylik o'zlashtirish, Davomat foizi
  - O'quvchining shaxsiy baholari dinamikasi grafigi
  - To'liq baholar tarixi, Davomat tarixi, Ogohlantirishlar tarixi
  - Profil ichida barcha ma'lumotlarni tahrirlash va tezkor baho qo'yish.

### 4. Baholash Tizimi
- O'quvchi, Fan, Sana, Nazorat turi (*Test, Nazorat ishi, Uyga vazifa, Og'zaki so'rov, Mock Exam*), Baho (0-100), Izoh.
- Har bir baho tarixda saqlanadi va real vaqt rejimida statistikani yangilaydi.

### 5. Baho Pasayishini Avtomatik Aniqlash (AI Warning Engine)
- Har bir yangi baho qo'yilganda tizim avtomatik tahlil qiladi:
  - Baholar ketma-ket pasaysa (masalan: 3 marta ketma-ket pasayish)
  - O'rtacha baho belgilangan chegaradan pastga tushsa (masalan: < 70 ball)
  - Natija oldingisiga nisbatan keskin foizga pasaysa (masalan: 10% dan ortiq)
- Avtomatik ravishda **⚠️ Ogohlantirish** yaratiladi va ko'rsatiladi:
  - Oldingi o'rtacha baho
  - Hozirgi o'rtacha baho
  - Qancha pasaygani
  - Qaysi fanlarda pasayish borligi
  - Oxirgi baholar
- Admin panelda alohida **⚠️ Ogohlantirishlar** bo'limi orqali holatni nazorat qilish, "Hal qilindi" deb belgilash va Telegram orqali qayta ogohlantirish imkoniyati.

### 6. Telegram Bot Integratsiyasi
- Xavfsiz server tomoni integratsiyasi (`TELEGRAM_BOT_TOKEN`).
- O'quvchiga yangi baho qo'yilganda Telegram orqali xabar:
  ```
  📚 ANTIGRAVITY
  Salom, Aziz!
  Sizga yangi baho qo‘yildi.
  Fan: Matematika
  Baho: 86
  Sana: 12.09.2026
  Izoh: Yaxshi natija.
  ANTIGRAVITY ta'lim markazi
  ```
- O'quvchi natijasi pasayganda avtomatik ogohlantirish:
  ```
  ⚠️ ANTIGRAVITY OGOHLANTIRISH
  Sizning o‘quv natijangiz pasaymoqda.
  Oldingi o‘rtacha baho: 89
  Hozirgi o‘rtacha baho: 76
  Iltimos, keyingi darslarda natijangizni yaxshilashga harakat qiling.
  ```
- Ota-onaga farzandining yangi bahosi va natijasi pasayganda qat'iy ogohlantirish:
  ```
  👨‍👩‍👦 ANTIGRAVITY
  Farzandingizga yangi baho qo‘yildi.
  O‘quvchi: Aziz Karimov
  Fan: Ingliz tili
  Baho: 78
  Sana: 12.09.2026
  Joriy o‘rtacha natija: 82
  ```
- **Xabarlar Jurnali (Notification Logs)**: Kimga, qachon, xabar turi, holati (*Sent / Failed*), xatolik matni.
- **Admin Test Xabar Yuborish Konsoli**.

### 7. Guruhlar, Kurslar, Ustozlar va Davomat Boshqaruvi
- Har bir yo'nalish uchun alohida to'liq CRUD imkoniyatlari.
- Guruhlar bo'yicha kunlik interaktiv davomat varaqasi (*Bor, Yo'q, Kechikdi, Sababli*).

### 8. Xavfsizlik va Rollar
- **Super Admin**: Barcha tizim huquqlari, tizim va bot sozlamalari, tokenni boshqarish.
- **Admin**: O'quvchilar, guruhlar, kurslar, baholar, hisobotlar.
- **Ustoz**: Biriktirilgan guruhlar va o'quvchilar, baho qo'yish, davomat.
- Maxfiy parollar `werkzeug.security` orqali xeshlangan (SHA-256).

---

## 🔑 Sinov Uchun Foydalanuvchi Hisoblari

| Foydalanuvchi | Login | Parol | Roli |
|---|---|---|---|
| **Super Admin** | `admin` | `admin123` | Barcha huquqlar, Sozlamalar, Bot tokeni |
| **Menejer** | `menejer` | `admin123` | Admin huquqi (O'quvchilar, guruhlar, baholar) |
| **Ustoz (Teacher)** | `ustoz` | `ustoz123` | Ustoz huquqi (Faqat o'z o'quvchilari va baholash) |

---

## ⚙️ O'rnatish va Ishga Tushirish

1. **Repozitoriy papkasiga kiring**:
   ```bash
   cd "c:\Users\SONY\Desktop\Новая папка (10)"
   ```

2. **Serverni ishga tushiring**:
   ```bash
   python app.py
   ```

3. **Brauzerda oching**:
   - Asosiy jamoat sayti: `http://127.0.0.1:5000/`
   - Admin panelga kirish: `http://127.0.0.1:5000/login`

4. **Avtomatlashtirilgan testlarni ishga tushirish**:
   ```bash
   python -m unittest test_suite.py
   ```

---

## 📱 Telegram Botni Ulash

1. Telegramda [@BotFather](https://t.me/BotFather) botiga `/newbot` buyrug'ini yuborib yangi bot yarating.
2. Bot bergan tokenni nusxalang.
3. ANTIGRAVITY Admin paneliga kiring (`http://127.0.0.1:5000/login`).
4. Chap menyudan **Sozlamalar** bo'limiga o'ting.
5. **Telegram Bot Token** maydoniga tokenni joylashtiring va **Saqlash** tugmasini bosing.
6. O'quvchi yoki ota-onaga baho qo'yilganda, ularning Telegram Chat ID raqamiga bildirishnomalar avtomatik yuboriladi.
