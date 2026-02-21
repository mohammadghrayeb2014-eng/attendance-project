/**
 * web/static/js/teacher.js
 * Frontend logic for the premium Teacher Dashboard
 */

const API = "http://127.0.0.1:5001/api";
const STORAGE_KEY = "user";
const ACTIVE_KEY = "active_assignment";

let currentUser = null;
let myAssignments = [];
let allAttendance = [];
let allGrades = [];

// --- Helper Functions ---
async function fetchJSON(url, options = {}) {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Request failed");
    return data;
}

function getInitials(name) {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().substring(0, 2);
}

// --- Protection & Auth ---
function checkAuth() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
        window.location.href = "/login";
        return;
    }
    currentUser = JSON.parse(raw);
    if (currentUser.role !== 'teacher' && currentUser.role !== 'admin') {
        window.location.href = "/login";
        return;
    }

    document.getElementById('teacherName').textContent = currentUser.name;
    document.getElementById('teacherAvatar').textContent = getInitials(currentUser.name);
    document.getElementById('todayDate').textContent = new Date().toLocaleDateString('en-US', {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
    });
}

// --- Data Loading ---
async function loadData() {
    try {
        const [assignments, classes, subjects, attendance, grades] = await Promise.all([
            fetchJSON(`${API}/assignments`),
            fetchJSON(`${API}/classes`),
            fetchJSON(`${API}/subjects`),
            fetchJSON(`${API}/attendance/records`).catch(() => []),
            fetchJSON(`${API}/grades`).catch(() => [])
        ]);

        const classById = new Map(classes.map(c => [c.id, c]));
        const subjectById = new Map(subjects.map(s => [s.id, s]));

        // Filter and decorate assignments
        myAssignments = assignments
            .filter(a => a.teacher_username === currentUser.username)
            .map(a => {
                const c = classById.get(a.class_id);
                const s = subjectById.get(a.subject_id);
                return {
                    ...a,
                    class_name: c?.name || "Unknown Class",
                    subject_name: s?.name || "Unknown Subject",
                    rows: c?.rows || 0,
                    cols: c?.cols || 0,
                    seating: c?.seating || {}
                };
            });

        allAttendance = attendance;
        allGrades = grades;

        updateStats();
        renderDashboard();
    } catch (err) {
        console.error("Dashboard Load Error:", err);
    }
}

function updateStats() {
    const classCount = myAssignments.length;

    // Calculate total unique students in all my classes
    const uniqueStudents = new Set();
    myAssignments.forEach(a => {
        const seating = a.seating || {};
        Object.values(seating).forEach(name => uniqueStudents.add(name));
    });

    // Calculate attendance avg for this teacher's sessions
    const mySessions = allAttendance.filter(s => s.teacher_username === currentUser.username);
    let totalR = 0;
    let presentR = 0;
    mySessions.forEach(s => {
        (s.records || []).forEach(r => {
            totalR++;
            if (r.status === "Present") presentR++;
        });
    });
    const attendPct = totalR ? Math.round((presentR / totalR) * 100) : 0;

    // Grades for my classes
    const myClassIds = new Set(myAssignments.map(a => a.class_id));
    const myGradesCount = allGrades.filter(g => myClassIds.has(Number(g.class_id))).length;

    document.getElementById('statClasses').textContent = classCount;
    document.getElementById('statStudents').textContent = uniqueStudents.size;
    document.getElementById('statAttendance').textContent = `${attendPct}%`;
    document.getElementById('statGraded').textContent = myGradesCount;
}

// --- Rendering ---
function renderDashboard() {
    const grid = document.getElementById('activeSessionsGrid');
    grid.innerHTML = "";

    if (myAssignments.length === 0) {
        grid.innerHTML = "<p class='muted'>No classes assigned yet.</p>";
    }

    // Show first 3 assignments as "active" cards
    myAssignments.slice(0, 3).forEach(a => {
        const card = document.createElement('div');
        card.className = "card stat-card";
        card.style.borderLeft = "4px solid var(--accent-primary)";
        card.innerHTML = `
            <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                <span class="status status-active">Active</span>
                <i class="fa-solid fa-users" style="color: var(--text-secondary);"></i>
            </div>
            <h3 style="margin-bottom: 0.25rem;">${a.class_name}</h3>
            <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 1.5rem;">${a.subject_name}</p>
            <button class="btn btn-primary w-full" onclick="openSession(${JSON.stringify(a).replace(/"/g, '&quot;')})">
                <i class="fa-solid fa-play"></i> Start Session
            </button>
        `;
        grid.appendChild(card);
    });

    // Render Attendance Logs
    const tbody = document.getElementById('attendanceLogsBody');
    tbody.innerHTML = "";

    const myHistory = allAttendance
        .filter(s => s.teacher_username === currentUser.username)
        .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
        .slice(0, 5);

    if (myHistory.length === 0) {
        tbody.innerHTML = "<tr><td colspan='6' class='text-center muted'>No session history yet.</td></tr>";
    }

    myHistory.forEach(s => {
        const present = (s.records || []).filter(r => r.status === "Present").length;
        const absent = (s.records || []).length - present;
        const aObj = myAssignments.find(a => a.class_id === s.class_id && a.subject_id === s.subject_id) || {};

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${s.date} <br/><small class="muted">${s.timestamp.split(' ')[1]}</small></td>
            <td><b>${aObj.class_name || 'Class ' + s.class_id}</b><br/><small>${aObj.subject_name || '-'}</small></td>
            <td style="color: #10b981; font-weight: 700;">${present}</td>
            <td style="color: #ef4444; font-weight: 700;">${absent}</td>
            <td><span class="status status-active">Success</span></td>
            <td><button class="btn btn-outline" style="padding: 0.4rem 0.8rem; font-size: 0.8rem;">View</button></td>
        `;
        tbody.appendChild(tr);
    });
}

function openSession(assignment) {
    localStorage.setItem(ACTIVE_KEY, JSON.stringify(assignment));
    window.location.href = "/session";
}

// --- Navigation ---
function switchSection(sectionId) {
    ['dashboardSection', 'classesSection', 'academicSection'].forEach(id => {
        document.getElementById(id).style.display = (id === sectionId) ? 'block' : 'none';
    });

    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    // Map sectionId to navId...
}

document.getElementById('navDashboard').addEventListener('click', (e) => {
    e.preventDefault();
    switchSection('dashboardSection');
    e.target.closest('.nav-link').classList.add('active');
});

document.getElementById('navMyClasses').addEventListener('click', (e) => {
    e.preventDefault();
    switchSection('classesSection');
    e.target.closest('.nav-link').classList.add('active');
    renderClassList();
});

document.getElementById('navAcademic').addEventListener('click', (e) => {
    e.preventDefault();
    switchSection('academicSection');
    e.target.closest('.nav-link').classList.add('active');
});

document.getElementById('logoutBtn').addEventListener('click', (e) => {
    e.preventDefault();
    localStorage.removeItem(STORAGE_KEY);
    window.location.href = "/login";
});

// --- Class List Rendering ---
function renderClassList() {
    const tbody = document.getElementById('fullClassListBody');
    tbody.innerHTML = "";

    myAssignments.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><b>${a.class_name}</b></td>
            <td>${a.subject_name}</td>
            <td>${a.rows}x${a.cols}</td>
            <td>
                <button class="btn btn-outline" onclick="openSession(${JSON.stringify(a).replace(/"/g, '&quot;')})">Open</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// --- Initialization ---
window.addEventListener('load', () => {
    checkAuth();
    loadData();
});
