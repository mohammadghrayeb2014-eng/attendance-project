/**
 * web/static/js/admin.js
 * Admin dashboard logic for real-time data population
 */

const API = "http://127.0.0.1:5001/api";
const STORAGE_KEY = "user";

let currentUser = null;

async function fetchJSON(url, options = {}) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Request failed");
    return data;
}

function checkAuth() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
        window.location.href = "/login";
        return;
    }
    currentUser = JSON.parse(raw);
    if (currentUser.role !== 'admin') {
        window.location.href = "/login";
        return;
    }

    document.getElementById('adminName').textContent = currentUser.name;
    document.getElementById('adminAvatar').textContent = currentUser.name[0];
    document.getElementById('todayDate').textContent = new Date().toLocaleDateString('en-US', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
    });
}

async function loadData() {
    try {
        const [teachers, students, classes, attendance, attendTrend, gradeDist] = await Promise.all([
            fetchJSON(`${API}/teachers`),
            fetchJSON(`${API}/students`),
            fetchJSON(`${API}/classes`),
            fetchJSON(`${API}/attendance/records`).catch(() => []),
            fetchJSON(`${API}/analytics/attendance_trend`).catch(() => []),
            fetchJSON(`${API}/analytics/grade_distribution`).catch(() => [])
        ]);

        document.getElementById('statTeachers').textContent = teachers.length;
        document.getElementById('statStudents').textContent = students.length;
        document.getElementById('statClasses').textContent = classes.length;

        // Calculate Average Attendance
        let totalRecords = 0;
        let presentCount = 0;
        attendance.forEach(session => {
            (session.records || []).forEach(r => {
                totalRecords++;
                if (r.status === "Present") presentCount++;
            });
        });

        const avgAttend = totalRecords ? Math.round((presentCount / totalRecords) * 100) : 0;
        document.getElementById('statAttendance').textContent = `${avgAttend}%`;

        renderCharts(attendTrend, gradeDist);
        renderActivity(attendance, teachers);
    } catch (err) {
        console.error("Admin Load Error:", err);
    }
}

function renderCharts(attendTrend, gradeDist) {
    // Attendance Chart
    const attCtx = document.getElementById('attendanceChart').getContext('2d');
    new Chart(attCtx, {
        type: 'line',
        data: {
            labels: attendTrend.map(d => d.date),
            datasets: [{
                label: 'Attendance %',
                data: attendTrend.map(d => d.percentage),
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37, 99, 235, 0.1)',
                fill: true,
                tension: 0.4,
                borderWidth: 3,
                pointRadius: 4,
                pointBackgroundColor: '#fff',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { min: 0, max: 100, grid: { borderDash: [5, 5] } },
                x: { grid: { display: false } }
            }
        }
    });

    // Grade Chart
    const grdCtx = document.getElementById('gradeChart').getContext('2d');
    new Chart(grdCtx, {
        type: 'doughnut',
        data: {
            labels: gradeDist.map(d => d.label),
            datasets: [{
                data: gradeDist.map(d => d.count),
                backgroundColor: ['#2563eb', '#3b82f6', '#60a5fa', '#93c5fd', '#d1d5db'],
                borderWidth: 0,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { usePointStyle: true, padding: 20 } }
            },
            cutout: '70%'
        }
    });
}

function renderActivity(attendance, teachers) {
    const tbody = document.getElementById('activityBody');
    tbody.innerHTML = "";

    const recent = attendance.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp)).slice(0, 5);

    if (recent.length === 0) {
        tbody.innerHTML = "<tr><td colspan='5' class='text-center muted'>No recent activity found.</td></tr>";
        return;
    }

    recent.forEach(s => {
        const teacher = teachers.find(t => t.username === s.teacher_username) || { name: s.teacher_username };
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>
                <div style="display: flex; align-items: center; gap: 0.75rem;">
                    <div class="avatar" style="width: 2rem; height: 2rem; font-size: 0.8rem;">${teacher.name[0]}</div>
                    <b>${teacher.name}</b>
                </div>
            </td>
            <td>Attendance Session</td>
            <td>Class ${s.class_id}</td>
            <td>${s.date}</td>
            <td><span class="status status-active">Done</span></td>
        `;
        tbody.appendChild(tr);
    });
}

document.getElementById('logoutBtn').addEventListener('click', (e) => {
    e.preventDefault();
    localStorage.removeItem(STORAGE_KEY);
    window.location.href = "/login";
});

window.addEventListener('load', () => {
    checkAuth();
    loadData();
});
