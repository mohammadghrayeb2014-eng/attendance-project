const API = "/api";

/* =========================================================
   Utilities
   ========================================================= */

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function option(select, value, text) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = text;
  select.appendChild(o);
}

function setMsg(text, isError = false) {
  const el = document.getElementById("adminMsg");
  if (!el) return;
  el.className = isError ? "tag tag-absent" : "tag tag-present";
  el.textContent = text || "";
  el.style.display = text ? "inline-block" : "none";
}

function showPanel(panelId) {
  // In this version, we show all cards but scroll to them.
  if (panelId === "all") {
    window.scrollTo({ top: 0, behavior: "smooth" });
  } else {
    const target = document.getElementById(panelId);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
}

/* =========================================================
   Load Select Dropdowns
   ========================================================= */

async function loadAllSelects() {
  try {
    const [teachers, classes, subjects] = await Promise.all([
      fetchJSON(`${API}/teachers`),
      fetchJSON(`${API}/classes`),
      fetchJSON(`${API}/subjects`)
    ]);

    const tSel = document.getElementById("teacherSelect");
    const cSel = document.getElementById("classSelect");
    const sSel = document.getElementById("subjectSelect");

    if (!tSel || !cSel || !sSel) return;

    tSel.innerHTML = '<option value="">-- Choose Teacher --</option>';
    cSel.innerHTML = '<option value="">-- Choose Class --</option>';
    sSel.innerHTML = '<option value="">-- Choose Subject --</option>';

    teachers.forEach(t => option(tSel, t.username, `${t.name} (${t.username})`));
    classes.forEach(c => option(cSel, c.id, `${c.name} [${c.rows}x${c.cols}]`));
    subjects.forEach(s => option(sSel, s.id, s.name));
  } catch (e) {
    console.error("Failed to load selects:", e);
  }
}

/* =========================================================
   Create Teacher
   ========================================================= */

async function createTeacher() {
  const msg = document.getElementById("teacherCreatedMsg");
  try {
    msg.textContent = "";
    msg.className = "";

    const username = document.getElementById("newTeacherUsername").value.trim();
    const name = document.getElementById("newTeacherName").value.trim();

    if (!username) {
      msg.textContent = "Username is required.";
      msg.className = "tag tag-absent";
      return;
    }

    const data = await fetchJSON(`${API}/admin/create_teacher`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, name })
    });

    msg.innerHTML = `✅ Created ${data.username}. Password: <span class="tag tag-late">${data.password}</span> (copy it now)`;
    msg.className = "tag tag-present";

    document.getElementById("newTeacherUsername").value = "";
    document.getElementById("newTeacherName").value = "";

    await loadAllSelects();
  } catch (e) {
    msg.textContent = e.message;
    msg.className = "tag tag-absent";
  }
}

/* =========================================================
   Create Student
   ========================================================= */

async function createStudent() {
  const msg = document.getElementById("studentCreatedMsg");
  try {
    msg.textContent = "";
    msg.className = "";

    const username = document.getElementById("newStudentUsername").value.trim();
    const name = document.getElementById("newStudentName").value.trim();

    if (!username) {
      msg.textContent = "Username is required.";
      msg.className = "tag tag-absent";
      return;
    }

    const data = await fetchJSON(`${API}/admin/create_student`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, name })
    });

    msg.innerHTML = `✅ Created ${data.username}. Password: <span class="tag tag-late">${data.password}</span> (copy it now)`;
    msg.className = "tag tag-present";

    document.getElementById("newStudentUsername").value = "";
    document.getElementById("newStudentName").value = "";
  } catch (e) {
    msg.textContent = e.message;
    msg.className = "tag tag-absent";
  }
}

/* =========================================================
   Add Class
   ========================================================= */

async function addClass() {
  try {
    setMsg("");
    const name = document.getElementById("className").value.trim();
    const rows = document.getElementById("classRows").value.trim() || "4";
    const cols = document.getElementById("classCols").value.trim() || "6";

    if (!name) {
      setMsg("Class name required.", true);
      return;
    }

    await fetchJSON(`${API}/classes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, rows, cols })
    });

    setMsg("✅ Class added.");
    document.getElementById("className").value = "";
    await loadAllSelects();
  } catch (e) {
    setMsg(e.message, true);
  }
}

/* =========================================================
   Add Subject
   ========================================================= */

async function addSubject() {
  try {
    setMsg("");
    const name = document.getElementById("subjectName").value.trim();

    if (!name) {
      setMsg("Subject name required.", true);
      return;
    }

    await fetchJSON(`${API}/subjects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name })
    });

    setMsg("✅ Subject added.");
    document.getElementById("subjectName").value = "";
    await loadAllSelects();
  } catch (e) {
    setMsg(e.message, true);
  }
}

/* =========================================================
   Assign Teacher
   ========================================================= */

async function createAssignment() {
  try {
    setMsg("");

    const teacher_username = document.getElementById("teacherSelect").value;
    const class_id = document.getElementById("classSelect").value;
    const subject_id = document.getElementById("subjectSelect").value;

    if (!teacher_username || !class_id || !subject_id) {
      setMsg("Please select teacher, class, and subject.", true);
      return;
    }

    await fetchJSON(`${API}/assignments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ teacher_username, class_id, subject_id })
    });

    setMsg("✅ Assignment created.");
  } catch (e) {
    setMsg(e.message, true);
  }
}

/* =========================================================
   Reports
   ========================================================= */

function str(v) {
  return v === undefined || v === null ? "" : String(v);
}

async function loadSystemReports() {
  const viewEl = document.getElementById("adminReportsView");
  if (!viewEl) return;

  try {
    viewEl.innerHTML = "Loading system reports...";

    const [classes, attendance] = await Promise.all([
      fetchJSON(`${API}/classes`),
      fetchJSON(`${API}/attendance/records`).catch(() => [])
    ]);

    if (!attendance.length) {
      viewEl.innerHTML = '<div class="tag tag-late">No attendance records found yet.</div>';
      return;
    }

    let html = `<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">`;
    html += `<thead><tr style="text-align:left; border-bottom:1px solid var(--border-color);">
      <th style="padding:0.5rem;">Class</th>
      <th style="padding:0.5rem;text-align:center;">Sessions</th>
      <th style="padding:0.5rem;text-align:center;">Avg Attendance</th>
    </tr></thead><tbody>`;

    classes.forEach(c => {
      const sessions = attendance.filter(s => str(s.class_id) === str(c.id));

      let total = 0;
      let present = 0;

      sessions.forEach(s => {
        (s.records || []).forEach(r => {
          total++;
          if (r.status === "Present") present++;
        });
      });

      const avg = total ? Math.round((present / total) * 100) : 0;
      const statusClass = avg < 75 ? "tag tag-absent" : "tag tag-present";

      html += `<tr style="border-bottom:1px solid rgba(0,0,0,0.05);">
        <td style="padding:0.75rem;">${c.name}</td>
        <td style="padding:0.75rem;text-align:center;">${sessions.length}</td>
        <td style="padding:0.75rem;text-align:center;"><span class="${statusClass}">${avg}%</span></td>
      </tr>`;
    });

    html += `</tbody></table>`;
    viewEl.innerHTML = html;

  } catch (err) {
    console.error(err);
    viewEl.innerHTML = '<div class="tag tag-absent">Error loading reports.</div>';
  }
}

/* =========================================================
   Event Wiring
   ========================================================= */

function wireEvents() {
  document.getElementById("createTeacherBtn")?.addEventListener("click", createTeacher);
  document.getElementById("createStudentBtn")?.addEventListener("click", createStudent);
  document.getElementById("addClassBtn")?.addEventListener("click", addClass);
  document.getElementById("addSubjectBtn")?.addEventListener("click", addSubject);
  document.getElementById("assignBtn")?.addEventListener("click", createAssignment);

  // Navigation logic
  const navMap = {
    "navDashboard": "all",
    "navTeachers": "cardTeachers",
    "navClasses": "cardClasses",
    "navSubjects": "cardSubjects",
    "navAssignments": "cardAssignments",
    "navReports": "adminReportsPanel"
  };

  Object.entries(navMap).forEach(([navId, panelId]) => {
    const link = document.getElementById(navId);
    if (!link) return;

    link.addEventListener("click", (e) => {
      e.preventDefault();

      // Update active link
      document.querySelectorAll(".nav-links .nav-link").forEach(l => l.classList.remove("active"));
      link.classList.add("active");

      if (panelId === "adminReportsPanel") {
        document.getElementById("adminReportsPanel").style.display = "block";
        loadSystemReports();
        document.getElementById("adminReportsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
      } else {

        if (panelId === "all") {
          window.scrollTo({ top: 0, behavior: "smooth" });
        } else {
          document.getElementById(panelId)?.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    });
  });

  // Logout buttons
  ["logoutBtn", "headerLogoutBtn"].forEach(id => {
    document.getElementById(id)?.addEventListener("click", (e) => {
      e.preventDefault();
      logout();
    });
  });
}

/* =========================================================
   Dashboard Stats
   ========================================================= */

async function loadDashboardStats() {
  try {
    const [teachers, students, classes, attendance, attendTrend, gradeDist] = await Promise.all([
      fetchJSON(`${API}/teachers`),
      fetchJSON(`${API}/students`).catch(() => []),
      fetchJSON(`${API}/classes`),
      fetchJSON(`${API}/attendance/records`).catch(() => []),
      fetchJSON(`${API}/analytics/attendance_trend`).catch(() => []),
      fetchJSON(`${API}/analytics/grade_distribution`).catch(() => [])
    ]);

    document.getElementById("statTeachers").textContent = teachers.length;
    document.getElementById("statStudents").textContent = students.length;
    document.getElementById("statClasses").textContent = classes.length;

    // Attendance calculation
    let totalRecords = 0;
    let presentRecords = 0;
    attendance.forEach(session => {
      (session.records || []).forEach(r => {
        totalRecords++;
        if (r.status === "Present") presentRecords++;
      });
    });
    const avgAttendance = totalRecords ? Math.round((presentRecords / totalRecords) * 100) : 0;
    document.getElementById("statAttendance").textContent = `${avgAttendance}%`;

    renderAdminCharts(attendTrend, gradeDist);
  } catch (e) {
    console.error("Failed to load dashboard stats:", e);
  }
}

function renderAdminCharts(attendTrend, gradeDist) {
  // Line Chart for Trends
  const trendCtx = document.getElementById('attendanceChart').getContext('2d');
  new Chart(trendCtx, {
    type: 'line',
    data: {
      labels: attendTrend.map(d => d.date),
      datasets: [{
        label: 'Presence Rate',
        data: attendTrend.map(d => d.percentage),
        borderColor: '#2563eb',
        backgroundColor: 'rgba(37, 99, 235, 0.05)',
        fill: true,
        tension: 0.4,
        borderWidth: 4,
        pointRadius: 5,
        pointHoverRadius: 8
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { min: 0, max: 100, grid: { color: 'rgba(0,0,0,0.03)' } },
        x: { grid: { display: false } }
      }
    }
  });

  // Doughnut Chart for Grades
  const gradeCtx = document.getElementById('gradeChart').getContext('2d');
  new Chart(gradeCtx, {
    type: 'doughnut',
    data: {
      labels: gradeDist.map(d => d.label),
      datasets: [{
        data: gradeDist.map(d => d.count),
        backgroundColor: ['#1e3a8a', '#2563eb', '#60a5fa', '#93c5fd', '#e2e8f0'],
        borderWidth: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '75%',
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, padding: 20 } } }
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  wireEvents();
  await Promise.all([
    loadAllSelects().catch(err => setMsg(err.message, true)),
    loadDashboardStats()
  ]);
});
