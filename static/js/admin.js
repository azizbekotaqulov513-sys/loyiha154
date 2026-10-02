// ANTIGRAVITY Admin Dashboard & Management Scripts

document.addEventListener('DOMContentLoaded', () => {
    // 1. Mobile Sidebar Toggle
    const sidebarToggleBtn = document.getElementById('admin-sidebar-toggle');
    const sidebar = document.getElementById('admin-sidebar');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    if (sidebarToggleBtn && sidebar) {
        sidebarToggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('-translate-x-full');
            if (sidebarOverlay) sidebarOverlay.classList.toggle('hidden');
        });
    }
    if (sidebarOverlay && sidebar) {
        sidebarOverlay.addEventListener('click', () => {
            sidebar.classList.add('-translate-x-full');
            sidebarOverlay.classList.add('hidden');
        });
    }

    // 2. Modal Helper Functions
    window.openModal = (modalId) => {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
            modal.classList.add('flex');
            document.body.style.overflow = 'hidden';
        }
    };

    window.closeModal = (modalId) => {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.add('hidden');
            modal.classList.remove('flex');
            document.body.style.overflow = '';
        }
    };

    // Auto-close modal when clicking backdrop
    document.querySelectorAll('.modal-container').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
                document.body.style.overflow = '';
            }
        });
    });

    // 3. Auto dismiss toasts after 5 seconds
    document.querySelectorAll('.alert-toast').forEach(toast => {
        setTimeout(() => {
            toast.style.transition = 'opacity 0.5s ease';
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 500);
        }, 5000);
    });

    // 4. Initialize Dashboard Charts if on Dashboard page
    if (typeof window.dashboardChartData !== 'undefined') {
        const data = window.dashboardChartData;

        // Chart 1: Baholar statistikasi (Distribution)
        const ctxDist = document.getElementById('chart-distribution');
        if (ctxDist) {
            new Chart(ctxDist, {
                type: 'bar',
                data: {
                    labels: data.grade_distribution.labels,
                    datasets: [{
                        label: "Baholar soni",
                        data: data.grade_distribution.data,
                        backgroundColor: [
                            'rgba(239, 68, 68, 0.7)',
                            'rgba(245, 158, 11, 0.7)',
                            'rgba(59, 130, 246, 0.7)',
                            'rgba(16, 185, 129, 0.7)',
                            'rgba(6, 182, 212, 0.8)'
                        ],
                        borderColor: [
                            '#ef4444',
                            '#f59e0b',
                            '#3b82f6',
                            '#10b981',
                            '#06b6d4'
                        ],
                        borderWidth: 1.5,
                        borderRadius: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(255, 255, 255, 0.06)' },
                            ticks: { color: '#94a3b8', stepSize: 1 }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#94a3b8' }
                        }
                    }
                }
            });
        }

        // Chart 2: O‘quvchilar natijalari (Categories)
        const ctxCat = document.getElementById('chart-categories');
        if (ctxCat) {
            new Chart(ctxCat, {
                type: 'doughnut',
                data: {
                    labels: data.student_categories.labels,
                    datasets: [{
                        data: data.student_categories.data,
                        backgroundColor: [
                            '#10b981',
                            '#3b82f6',
                            '#f59e0b',
                            '#ef4444'
                        ],
                        borderColor: '#0f172a',
                        borderWidth: 3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '70%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: { color: '#cbd5e1', boxWidth: 12, padding: 14 }
                        }
                    }
                }
            });
        }

        // Chart 3: Guruhlar bo‘yicha o‘rtacha natija
        const ctxGroups = document.getElementById('chart-groups');
        if (ctxGroups) {
            new Chart(ctxGroups, {
                type: 'bar',
                data: {
                    labels: data.group_averages.labels,
                    datasets: [{
                        label: "O'rtacha ball",
                        data: data.group_averages.data,
                        backgroundColor: 'rgba(56, 189, 248, 0.65)',
                        borderColor: '#38bdf8',
                        borderWidth: 1.5,
                        borderRadius: 6
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        x: {
                            min: 0,
                            max: 100,
                            grid: { color: 'rgba(255, 255, 255, 0.06)' },
                            ticks: { color: '#94a3b8' }
                        },
                        y: {
                            grid: { display: false },
                            ticks: { color: '#cbd5e1' }
                        }
                    }
                }
            });
        }

        // Chart 4: Baholarning vaqt bo‘yicha o‘zgarishi (Timeline)
        const ctxTimeline = document.getElementById('chart-timeline');
        if (ctxTimeline) {
            new Chart(ctxTimeline, {
                type: 'line',
                data: {
                    labels: data.timeline.labels,
                    datasets: [{
                        label: "O'rtacha ball dinamikasi",
                        data: data.timeline.data,
                        borderColor: '#00F0FF',
                        backgroundColor: 'rgba(0, 240, 255, 0.12)',
                        tension: 0.35,
                        fill: true,
                        pointBackgroundColor: '#0066FF',
                        pointBorderColor: '#00F0FF',
                        pointBorderWidth: 2,
                        pointRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            min: 50,
                            max: 100,
                            grid: { color: 'rgba(255, 255, 255, 0.06)' },
                            ticks: { color: '#94a3b8' }
                        },
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.04)' },
                            ticks: { color: '#94a3b8' }
                        }
                    }
                }
            });
        }
    }

    // 5. Initialize Student Profile Performance Chart
    if (typeof window.studentChartLabels !== 'undefined' && typeof window.studentChartScores !== 'undefined') {
        const ctxStudent = document.getElementById('student-performance-chart');
        if (ctxStudent) {
            new Chart(ctxStudent, {
                type: 'line',
                data: {
                    labels: window.studentChartLabels,
                    datasets: [{
                        label: "O'quvchi baholari",
                        data: window.studentChartScores,
                        borderColor: '#38BDF8',
                        backgroundColor: 'rgba(56, 189, 248, 0.15)',
                        tension: 0.3,
                        fill: true,
                        pointBackgroundColor: '#0284C7',
                        pointBorderColor: '#38BDF8',
                        pointRadius: 6,
                        pointHoverRadius: 8
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            min: 40,
                            max: 100,
                            grid: { color: 'rgba(255, 255, 255, 0.06)' },
                            ticks: { color: '#94a3b8' }
                        },
                        x: {
                            grid: { color: 'rgba(255, 255, 255, 0.04)' },
                            ticks: { color: '#94a3b8' }
                        }
                    }
                }
            });
        }
    }
});
