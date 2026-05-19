const API = "/api";

/* =========================================================
   Utilities
   ========================================================= */

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(data.error || "Request failed");
  }

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

function setElementMsg(id, text, isError = false) {
  const el = document.getElementById(id);
  if (!el) return;

  el.className = isError ? "tag tag-absent" : "tag tag-present";
  el.innerHTML = text || "";
  el.style.display = text ? "inline-block" : "none";
}

function clearInput(id) {
  const el = document.getElementById(id);
  if (el) el.value = "";
}

function showPanel(panelId) {
  if (panelId === "all") {
    window.scrollTo({ top: 0, behavior: "smooth" });
    return;
  }

  const target = document.getElementById(panelId);
  if (target) {
    target.scrollIntoView({ behavior: "smooth", block: "start" });
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

    teachers.forEach(t => {
      option(tSel, t.username, `${t.name || t.username} (${t.username})`);
    });

    classes.forEach(c => {
      option(cSel, c.id, `${c.name} [${c.rows}x${c.cols}]`);
    });

    subjects.forEach(s => {
      option(sSel, s.id, s.name);
    });

  } catch (e) {
    console.error("Failed to load selects:", e);
    setMsg("Failed to load dropdown data: " + e.message, true);
  }
}

/* =========================================================
   Create Teacher
   ========================================================= */

async function createTeacher() {
  const username = document.getElementById("newTeacherUsername")?.value.trim().toLowerCase();
  const name = document.getElementById("newTeacherName")?.value.trim();

  try {
    setElementMsg("teacherCreatedMsg", "");

    if (!username) {
      setElementMsg("teacherCreatedMsg", "Username is required.", true);
      return;
    }

    const data = await fetchJSON(`${API}/admin/create_teacher`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        username,
        name
      })
    });

    setElementMsg(
      "teacherCreatedMsg",
      `✅ Created ${data.username}. Password: <span class="tag tag-late">${data.password}</span> (copy it now)`,
      false
    );

    clearInput("newTeacherUsername");
    clearInput("newTeacherName");

    await Promise.all([
      loadAllSelects(),
      loadDashboardStats()
    ]);

  } catch (e) {
    setElementMsg("teacherCreatedMsg", e.message, true);
  }
}

/* =========================================================
   Create Student
   ========================================================= */

async function createStudent() {
  const username = document.getElementById("newStudentUsername")?.value.trim().toLowerCase();
  const name = document.getElementById("newStudentName")?.value.trim();

  try {
    setElementMsg("studentCreatedMsg", "");

    if (!username) {
      setElementMsg("studentCreatedMsg", "Username is required.", true);
      return;
    }

    const data = await fetchJSON(`${API}/admin/create_student`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        username,
        name
      })
    });

    setElementMsg(
      "studentCreatedMsg",
      `✅ Created ${data.username}. Password: <span class="tag tag-late">${data.password}</span> (copy it now)`,
      false
    );

    clearInput("newStudentUsername");
    clearInput("newStudentName");

    await Promise.all([
      loadAllSelects(),
      loadDashboardStats()
    ]);

  } catch (e) {
    setElementMsg("studentCreatedMsg", e.message, true);
  }
}

/* =========================================================
   Add Class
   ========================================================= */

async function addClass() {
  try {
    setMsg("");

    const name = document.getElementById("className")?.value.trim();
    const rows = Number(document.getElementById("classRows")?.value.trim() || 4);
    const cols = Number(document.getElementById("classCols")?.value.trim() || 6);

    if (!name) {
      setMsg("Class name required.", true);
      return;
    }

    if (!Number.isInteger(rows) || rows <= 0 || !Number.isInteger(cols) || cols <= 0) {
      setMsg("Rows and columns must be positive numbers.", true);
      return;
    }

    await fetchJSON(`${API}/classes`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name,
        rows,
        cols
      })
    });

    setMsg("✅ Class added.");

    clearInput("className");
    clearInput("classRows");
    clearInput("classCols");

    await Promise.all([
      loadAllSelects(),
      loadDashboardStats()
    ]);

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

    const name = document.getElementById("subjectName")?.value.trim();

    if (!name) {
      setMsg("Subject name required.", true);
      return;
    }

    await fetchJSON(`${API}/subjects`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        name
      })
    });

    setMsg("✅ Subject added.");

    clearInput("subjectName");

    await Promise.all([
      loadAllSelects(),
      loadDashboardStats()
    ]);

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

    const teacher_username = document.getElementById("teacherSelect")?.value;
    const class_id = Number(document.getElementById("classSelect")?.value);
    const subject_id = Number(document.getElementById("subjectSelect")?.value);

    if (!teacher_username || !class_id || !subject_id) {
      setMsg("Please select teacher, class, and subject.", true);
      return;
    }

    await fetchJSON(`${API}/assignments`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        teacher_username,
        class_id,
        subject_id
      })
    });

    setMsg("✅ Assignment created.");

    await Promise.all([
      loadAllSelects(),
      loadDashboardStats()
    ]);

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

    let html = `
      <table style="width:100%; border-collapse:collapse; font-size:0.85rem;">
        <thead>
          <tr style="text-align:left; border-bottom:1px solid var(--border-color);">
            <th style="padding:0.5rem;">Class</th>
            <th style="padding:0.5rem; text-align:center;">Sessions</th>
            <th style="padding:0.5rem; text-align:center;">Avg Attendance</th>
          </tr>
        </thead>
        <tbody>
    `;

    classes.forEach(c => {
      const sessions = attendance.filter(s => str(s.class_id) === str(c.id));

      let total = 0;
      let present = 0;

      sessions.forEach(s => {
        (s.records || []).forEach(r => {
          total++;

          if (r.status === "Present") {
            present++;
          }
        });
      });

      const avg = total ? Math.round((present / total) * 100) : 0;
      const statusClass = avg < 75 ? "tag tag-absent" : "tag tag-present";

      html += `
        <tr style="border-bottom:1px solid rgba(0,0,0,0.05);">
          <td style="padding:0.75rem;">${c.name}</td>
          <td style="padding:0.75rem; text-align:center;">${sessions.length}</td>
          <td style="padding:0.75rem; text-align:center;">
            <span class="${statusClass}">${avg}%</span>
          </td>
        </tr>
      `;
    });

    html += `
        </tbody>
      </table>
    `;

    viewEl.innerHTML = html;

  } catch (err) {
    console.error(err);
    viewEl.innerHTML = '<div class="tag tag-absent">Error loading reports.</div>';
  }
}

/* =========================================================
   Dashboard Stats
   ========================================================= */

async function loadDashboardStats() {
  try {
    const [teachers, students, classes, attendance] = await Promise.all([
      fetchJSON(`${API}/teachers`).catch(() => []),
      fetchJSON(`${API}/students`).catch(() => []),
      fetchJSON(`${API}/classes`).catch(() => []),
      fetchJSON(`${API}/attendance/records`).catch(() => [])
    ]);

    const statTeachers = document.getElementById("statTeachers");
    const statStudents = document.getElementById("statStudents");
    const statClasses = document.getElementById("statClasses");
    const statAttendance = document.getElementById("statAttendance");

    if (statTeachers) statTeachers.textContent = teachers.length;
    if (statStudents) statStudents.textContent = students.length;
    if (statClasses) statClasses.textContent = classes.length;

    let totalRecords = 0;
    let presentRecords = 0;

    attendance.forEach(session => {
      (session.records || []).forEach(r => {
        totalRecords++;

        if (r.status === "Present") {
          presentRecords++;
        }
      });
    });

    const avgAttendance = totalRecords
      ? Math.round((presentRecords / totalRecords) * 100)
      : 0;

    if (statAttendance) {
      statAttendance.textContent = `${avgAttendance}%`;
    }

  } catch (e) {
    console.error("Failed to load dashboard stats:", e);
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

  const navMap = {
    navDashboard: "all",
    navTeachers: "cardTeachers",
    navStudents: "cardStudents",
    navClasses: "cardClasses",
    navSubjects: "cardSubjects",
    navAssignments: "cardAssignments",
    navReports: "adminReportsPanel"
  };

  Object.entries(navMap).forEach(([navId, panelId]) => {
    const link = document.getElementById(navId);
    if (!link) return;

    link.addEventListener("click", (e) => {
      e.preventDefault();

      document.querySelectorAll(".nav-links .nav-link").forEach(l => {
        l.classList.remove("active");
      });

      link.classList.add("active");

      if (panelId === "adminReportsPanel") {
        const reportsPanel = document.getElementById("adminReportsPanel");

        if (reportsPanel) {
          reportsPanel.style.display = "block";
          loadSystemReports();
          reportsPanel.scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }

        return;
      }

      showPanel(panelId);
    });
  });

  ["logoutBtn", "headerLogoutBtn"].forEach(id => {
    document.getElementById(id)?.addEventListener("click", (e) => {
      e.preventDefault();
      logout();
    });
  });
}

/* =========================================================
   Init
   ========================================================= */

document.addEventListener("DOMContentLoaded", async () => {
  wireEvents();

  await Promise.all([
    loadAllSelects(),
    loadDashboardStats()
  ]);
});