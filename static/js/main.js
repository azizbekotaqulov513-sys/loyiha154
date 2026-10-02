// ANTIGRAVITY Public Website Interactions

document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Menu Toggle
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    const mobileMenu = document.getElementById('mobile-menu');
    if (mobileMenuBtn && mobileMenu) {
        mobileMenuBtn.addEventListener('click', () => {
            mobileMenu.classList.toggle('hidden');
        });
    }

    // 2. Animated Stats Counters
    const statCounters = document.querySelectorAll('.stat-counter');
    let animated = false;

    const runCounters = () => {
        statCounters.forEach(counter => {
            const target = parseInt(counter.getAttribute('data-target') || '0', 10);
            const duration = 1600;
            const stepTime = 20;
            const steps = duration / stepTime;
            const increment = target / steps;
            let current = 0;

            const timer = setInterval(() => {
                current += increment;
                if (current >= target) {
                    current = target;
                    clearInterval(timer);
                }
                counter.innerText = Math.floor(current).toLocaleString();
            }, stepTime);
        });
    };

    const statsSection = document.getElementById('stats-section');
    if (statsSection) {
        const observer = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting && !animated) {
                animated = true;
                runCounters();
            }
        }, { threshold: 0.3 });
        observer.observe(statsSection);
    } else {
        runCounters();
    }

    // 3. FAQ Accordion
    const faqToggles = document.querySelectorAll('.faq-toggle');
    faqToggles.forEach(toggle => {
        toggle.addEventListener('click', () => {
            const answer = toggle.nextElementSibling;
            const icon = toggle.querySelector('.faq-icon');
            const isOpen = !answer.classList.contains('hidden');

            // Close all
            document.querySelectorAll('.faq-answer').forEach(el => el.classList.add('hidden'));
            document.querySelectorAll('.faq-icon').forEach(el => el.style.transform = 'rotate(0deg)');

            if (!isOpen) {
                answer.classList.remove('hidden');
                if (icon) icon.style.transform = 'rotate(180deg)';
            }
        });
    });

    // 4. Enroll Modal Handlers
    const enrollModal = document.getElementById('enroll-modal');
    const enrollCourseInput = document.getElementById('enroll-course-name');
    const enrollButtons = document.querySelectorAll('.btn-open-enroll');
    const closeEnrollBtn = document.getElementById('close-enroll-modal');

    window.openEnrollModal = (courseName = '') => {
        if (enrollCourseInput) {
            enrollCourseInput.value = courseName;
        }
        if (enrollModal) {
            enrollModal.classList.remove('hidden');
            enrollModal.classList.add('flex');
            document.body.style.overflow = 'hidden';
        }
    };

    window.closeEnrollModal = () => {
        if (enrollModal) {
            enrollModal.classList.add('hidden');
            enrollModal.classList.remove('flex');
            document.body.style.overflow = '';
        }
    };

    enrollButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const course = btn.getAttribute('data-course') || '';
            window.openEnrollModal(course);
        });
    });

    if (closeEnrollBtn) {
        closeEnrollBtn.addEventListener('click', window.closeEnrollModal);
    }

    if (enrollModal) {
        enrollModal.addEventListener('click', (e) => {
            if (e.target === enrollModal) {
                window.closeEnrollModal();
            }
        });
    }

    // 5. Course Details Modal Handlers
    const courseDetailsModal = document.getElementById('course-details-modal');
    window.openCourseDetails = (title, level, duration, price, desc) => {
        document.getElementById('modal-course-title').innerText = title;
        document.getElementById('modal-course-level').innerText = level;
        document.getElementById('modal-course-duration').innerText = duration;
        document.getElementById('modal-course-price').innerText = price;
        document.getElementById('modal-course-desc').innerText = desc;
        
        const enrollActionBtn = document.getElementById('modal-course-enroll-btn');
        if (enrollActionBtn) {
            enrollActionBtn.onclick = () => {
                window.closeCourseDetails();
                window.openEnrollModal(title);
            };
        }

        if (courseDetailsModal) {
            courseDetailsModal.classList.remove('hidden');
            courseDetailsModal.classList.add('flex');
            document.body.style.overflow = 'hidden';
        }
    };

    window.closeCourseDetails = () => {
        if (courseDetailsModal) {
            courseDetailsModal.classList.add('hidden');
            courseDetailsModal.classList.remove('flex');
            document.body.style.overflow = '';
        }
    };

    // 6. Lead Form Submissions (AJAX)
    const handleLeadSubmit = async (formElement, statusElId) => {
        const statusEl = document.getElementById(statusElId);
        const submitBtn = formElement.querySelector('button[type="submit"]');
        const originalBtnText = submitBtn ? submitBtn.innerHTML : 'Yuborish';

        const formData = new FormData(formElement);
        const jsonData = Object.fromEntries(formData.entries());

        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Yuborilmoqda...';
        }

        try {
            const res = await fetch('/api/enroll', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(jsonData)
            });
            const data = await res.json();

            if (data.success) {
                if (statusEl) {
                    statusEl.className = 'mt-4 p-3 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-sm';
                    statusEl.innerText = data.message;
                    statusEl.classList.remove('hidden');
                }
                formElement.reset();
                setTimeout(() => {
                    if (window.closeEnrollModal) window.closeEnrollModal();
                    if (statusEl) statusEl.classList.add('hidden');
                }, 3000);
            } else {
                if (statusEl) {
                    statusEl.className = 'mt-4 p-3 rounded-lg bg-red-500/20 border border-red-500/40 text-red-300 text-sm';
                    statusEl.innerText = data.message || 'Xatolik yuz berdi!';
                    statusEl.classList.remove('hidden');
                }
            }
        } catch (err) {
            if (statusEl) {
                statusEl.className = 'mt-4 p-3 rounded-lg bg-red-500/20 border border-red-500/40 text-red-300 text-sm';
                statusEl.innerText = "Ulanishda xatolik yuz berdi. Iltimos qaytadan urinib ko'ring.";
                statusEl.classList.remove('hidden');
            }
        } finally {
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
        }
    };

    const modalEnrollForm = document.getElementById('enroll-form');
    if (modalEnrollForm) {
        modalEnrollForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleLeadSubmit(modalEnrollForm, 'enroll-modal-status');
        });
    }

    const contactForm = document.getElementById('contact-form');
    if (contactForm) {
        contactForm.addEventListener('submit', (e) => {
            e.preventDefault();
            handleLeadSubmit(contactForm, 'contact-form-status');
        });
    }
});
