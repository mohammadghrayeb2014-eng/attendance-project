// js/teacher.js
// Phase 2-ready teacher dashboard: select assignment -> open class.html

const API = "/api";
const ACTIVE_KEY = "active_assignment";

let allItems = [];     // all assignments for this teacher (decorated)
let selected = null;   // currently selected assignment

async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function el(tag, className, text) {
  const x = document.createElement(tag);
  if (className) x.className = className;
  if (text !== undefined) x.textContent = text;
  return x;
}

function setSelectedUI(item) {
  const box = document.getElementById("selectedBox");
  box.innerHTML = "";
  box.style.display = "flex";
  box.style.flexDirection = "column";
  box.style.gap = "0.5rem";

  const title = el("div", "", "");
  title.style.fontSize = "1.25rem";
  title.style.fontWeight = "800";
  title.style.color = "var(--p-600)";
  title.innerHTML = `<i class="fa-solid fa-graduation-cap" style="margin-right: 0.5rem;"></i>${item.class_name}`;

  const subtitle = el("div", "", "");
  subtitle.style.fontSize = "1rem";
  subtitle.style.fontWeight = "600";
  subtitle.style.color = "var(--text-main)";
  subtitle.textContent = item.subject_name;

  const meta = el("div", "pillrow", "");
  meta.style.marginTop = "0.5rem";
  meta.innerHTML = `
    <div class="pill"><i class="fa-solid fa-chair"></i> ${item.rows}x${item.cols}</div>
    <div class="pill"><i class="fa-solid fa-hashtag"></i> ID: ${item.class_id}</div>
  `;

  box.appendChild(title);
  box.appendChild(subtitle);
  box.appendChild(meta);

  document.getElementById("openBtn").disabled = false;
  document.getElementById("status").textContent = "";
}

function renderList(items) {
  const list = document.getElementById("list");
  const emptyMsg = document.getElementById("emptyMsg");

  list.innerHTML = "";
  emptyMsg.style.display = items.length === 0 ? "block" : "none";

  items.forEach((item) => {
    const row = el("div", "item");

    const left = el("div", "meta");
    const title = el("div", "title", `${item.class_name} — ${item.subject_name}`);
    const sub = el("div", "sub", `Class ID: ${item.class_id} • Subject ID: ${item.subject_id}`);

    const pillrow = el("div", "pillrow");
    const p1 = el("div", "pill", `${item.rows} x ${item.cols} seats`);
    const p2 = el("div", "pill", `Teacher: ${item.teacher_username}`);

    pillrow.appendChild(p1);
    pillrow.appendChild(p2);

    left.appendChild(title);
    left.appendChild(sub);
    left.appendChild(pillrow);

    const right = el("div");
    const btn = el("button", "btn-premium-sm", "Select");
    btn.addEventListener("click", () => {
      selected = item;
      setSelectedUI(item);
      loadAcademicData(); // Load academic tools data for selected class
    });
    right.appendChild(btn);

    row.appendChild(left);
    row.appendChild(right);

    list.appendChild(row);
  });
}

function applySearch() {
  const q = document.getElementById("searchInput").value.trim().toLowerCase();
  if (!q) {
    renderList(allItems);
    return;
  }

  const filtered = allItems.filter((i) =>
    i.class_name.toLowerCase().includes(q) ||
    i.subject_name.toLowerCase().includes(q)
  );

  renderList(filtered);
}

async function loadTeacherAssignments() {
  const user = getCurrentUser(); // from auth.js
  const username = user.username;

  const [assignments, classes, subjects] = await Promise.all([
    fetchJSON(`${API}/assignments`),
    fetchJSON(`${API}/classes`),
    fetchJSON(`${API}/subjects`)
  ]);

  const classById = new Map(classes.map((c) => [c.id, c]));
  const subjectById = new Map(subjects.map((s) => [s.id, s]));

  // Only assignments belonging to this teacher
  const mine = assignments.filter((a) => a.teacher_username === username);

  // Decorate with names + seat sizes
  allItems = mine.map((a) => {
    const c = classById.get(a.class_id);
    const s = subjectById.get(a.subject_id);

    return {
      teacher_username: a.teacher_username,
      class_id: a.class_id,
      subject_id: a.subject_id,
      class_name: c?.name ?? "Unknown class",
      subject_name: s?.name ?? "Unknown subject",
      rows: c?.rows ?? 0,
      cols: c?.cols ?? 0
    };
  });

  // Reset selection each load
  selected = null;
  document.getElementById("selectedBox").textContent = "Nothing selected yet.";
  document.getElementById("openBtn").disabled = true;

  renderList(allItems);
}

function showPanel(panelId) {
  const panels = ["panelClasses", "panelAcademic"];
  // Note: academic tools are inside cards, so we mostly scroll or show/hide specific containers
}

function wireUI() {
  // Sidebar navigation (Teacher)
  document.getElementById("navMyClasses")?.addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("panelClasses")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  document.getElementById("navLiveSession")?.addEventListener("click", (e) => {
    e.preventDefault();
    if (selected) {
      document.getElementById("openBtn")?.click();
    } else {
      alert("Please select a class first.");
      document.getElementById("panelClasses")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  document.getElementById("navAttendance")?.addEventListener("click", (e) => {
    e.preventDefault();
    document.getElementById("tabReports")?.click();
    document.getElementById("reportsContainer")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // Main UI Buttons
  document.getElementById("clearBtn")?.addEventListener("click", () => {
    document.getElementById("searchInput").value = "";
    applySearch();
  });

  document.getElementById("searchInput")?.addEventListener("input", applySearch);

  document.getElementById("openBtn").addEventListener("click", () => {
    if (!selected) return;
    localStorage.setItem(ACTIVE_KEY, JSON.stringify(selected));
    window.location.href = "class.html";
  });

  // Logout buttons
  ["logoutBtn", "headerLogoutBtn"].forEach(id => {
    document.getElementById(id)?.addEventListener("click", (e) => {
      e.preventDefault();
      logout();
    });
  });

  // Tab switching
  const tabs = ["tabExam", "tabHomework", "tabGrading", "tabGradebook", "tabReports"];
  const containers = ["examContainer", "homeworkContainer", "gradingContainer", "gradebookContainer", "reportsContainer"];

  tabs.forEach((tabId, idx) => {
    document.getElementById(tabId)?.addEventListener("click", () => {
      // Deactivate all tabs
      tabs.forEach(t => document.getElementById(t)?.classList.remove("active-tab"));
      // Hide all containers
      containers.forEach(c => {
        const el = document.getElementById(c);
        if (el) el.style.display = "none";
      });

      // Activate current
      document.getElementById(tabId).classList.add("active-tab");
      const targetContainer = document.getElementById(containers[idx]);
      if (targetContainer) targetContainer.style.display = "block";

      // Clear academic message on tab switch
      document.getElementById("academicMsg").textContent = "";
      document.getElementById("academicMsg").className = "ok text-center mt-4";

      // Load specific data
      if (tabId === "tabGrading") loadGradingItems();
      else if (tabId === "tabGradebook") loadGradebook();
      else if (tabId === "tabReports") loadTeacherReports();
      else loadAcademicData();
    });
  });

  // Grading & Reports Actions
  document.getElementById("gradeItemSelect")?.addEventListener("change", loadGradingList);
  document.getElementById("saveGradesBtn")?.addEventListener("click", saveGrades);
  document.getElementById("exportGradesBtn")?.addEventListener("click", exportToCSV);
  document.getElementById("exportReportsBtn")?.addEventListener("click", exportReportToCSV);

  // Creation logic
  document.getElementById("createExamBtn")?.addEventListener("click", async () => {
    if (!selected) {
      alert("Please select a class first.");
      return;
    }
    const title = document.getElementById("examTitle").value.trim();
    const kind = document.getElementById("examKind").value;
    const date = document.getElementById("examDate").value;
    const msgEl = document.getElementById("academicMsg");

    if (!title || !date) {
      msgEl.textContent = "Please fill in all fields.";
      msgEl.className = "tag tag-absent";
      return;
    }

    try {
      const user = getCurrentUser();
      await fetchJSON(`${API}/exams`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_username: user.username,
          class_id: selected.class_id,
          subject_id: selected.subject_id,
          title, kind, date
        })
      });
      msgEl.textContent = "✅ Exam created successfully!";
      msgEl.className = "tag tag-present";
      document.getElementById("examTitle").value = "";
      loadAcademicData();
    } catch (err) {
      msgEl.textContent = "Failed: " + err.message;
      msgEl.className = "tag tag-absent";
    }
  });

  document.getElementById("createHwBtn")?.addEventListener("click", async () => {
    if (!selected) {
      alert("Please select a class first.");
      return;
    }
    const title = document.getElementById("hwTitle").value.trim();
    const due_date = document.getElementById("hwDueDate").value;
    const description = document.getElementById("hwDesc").value.trim();
    const msgEl = document.getElementById("academicMsg");

    if (!title || !due_date) {
      msgEl.textContent = "Please fill in title and due date.";
      msgEl.className = "tag tag-absent";
      return;
    }

    try {
      const user = getCurrentUser();
      await fetchJSON(`${API}/homework`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          teacher_username: user.username,
          class_id: selected.class_id,
          subject_id: selected.subject_id,
          title, due_date, description
        })
      });
      msgEl.textContent = "✅ Homework posted successfully!";
      msgEl.className = "tag tag-present";
      document.getElementById("hwTitle").value = "";
      document.getElementById("hwDesc").value = "";
      loadAcademicData();
    } catch (err) {
      msgEl.textContent = "Failed: " + err.message;
      msgEl.className = "tag tag-absent";
    }
  });
}

async function loadGradingItems() {
  if (!selected) {
    document.getElementById("gradeItemSelect").innerHTML = '<option value="">-- Select a class first --</option>';
    return;
  }

  try {
    const [exams, homework] = await Promise.all([
      fetchJSON(`${API}/exams?class_id=${selected.class_id}&subject_id=${selected.subject_id}`),
      fetchJSON(`${API}/homework?class_id=${selected.class_id}&subject_id=${selected.subject_id}`)
    ]);

    const select = document.getElementById("gradeItemSelect");
    select.innerHTML = '<option value="">-- Choose Exam or Homework --</option>';

    exams.forEach(ex => {
      const opt = el("option", null, `[EXAM] ${ex.title} (${ex.date})`);
      opt.value = `exam_${ex.id}`;
      select.appendChild(opt);
    });

    homework.forEach(hw => {
      const opt = el("option", null, `[HW] ${hw.title} (Due: ${hw.due_date})`);
      opt.value = `homework_${hw.id}`;
      select.appendChild(opt);
    });

  } catch (err) {
    console.error("Failed to load items for grading:", err);
  }
}

async function loadGradingList() {
  const val = document.getElementById("gradeItemSelect").value;
  const listEl = document.getElementById("gradingList");
  const saveBtn = document.getElementById("saveGradesBtn");

  if (!val || !selected) {
    listEl.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-secondary);">Select an item to grade.</div>';
    saveBtn.style.display = "none";
    return;
  }

  const [type, id] = val.split("_");

  try {
    listEl.innerHTML = "Loading students...";

    // 1. Get students from class seating
    const classes = await fetchJSON(`${API}/classes`);
    const currentClass = classes.find(c => c.id === selected.class_id);
    const seating = currentClass ? (currentClass.seating || {}) : {};
    const students = Object.values(seating);

    if (students.length === 0) {
      listEl.innerHTML = '<div style="padding: 1rem; text-align: center;">No students found in this class seating chart.</div>';
      saveBtn.style.display = "none";
      return;
    }

    // 2. Get existing grades
    const existingGrades = await fetchJSON(`${API}/grades?item_id=${id}&item_type=${type}`);

    listEl.innerHTML = `
      <table style="width: 100%; border-collapse: collapse; font-size: 0.85rem;">
        <thead>
          <tr style="text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1);">
            <th style="padding: 0.5rem;">Student</th>
            <th style="padding: 0.5rem; width: 80px;">Score</th>
            <th style="padding: 0.5rem;">Comment</th>
          </tr>
        </thead>
        <tbody id="gradingTableBody"></tbody>
      </table>
    `;

    const tbody = document.getElementById("gradingTableBody");
    students.sort().forEach(name => {
      const g = existingGrades.find(x => x.student_name === name) || {};
      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
      tr.innerHTML = `
        <td style="padding: 0.75rem;">${name}</td>
        <td style="padding: 0.75rem;">
          <input type="number" class="grade-score" data-student="${name}" value="${g.score || ""}" 
                 style="margin-bottom:0; padding: 0.3rem; font-size: 0.8rem; width: 60px;">
        </td>
        <td style="padding: 0.75rem;">
          <input type="text" class="grade-comment" data-student="${name}" value="${g.comment || ""}" 
                 style="margin-bottom:0; padding: 0.3rem; font-size: 0.8rem;" placeholder="Note...">
        </td>
      `;
      tbody.appendChild(tr);
    });

    saveBtn.style.display = "block";

  } catch (err) {
    console.error("Failed to load grading list:", err);
    listEl.innerHTML = "Error loading students.";
  }
}

async function saveGrades() {
  const val = document.getElementById("gradeItemSelect").value;
  if (!val || !selected) return;

  const [type, id] = val.split("_");
  const scores = document.querySelectorAll(".grade-score");
  const comments = document.querySelectorAll(".grade-comment");

  const grades = [];
  scores.forEach((input, i) => {
    const student_name = input.dataset.student;
    const score = input.value;
    const comment = comments[i].value;
    if (score !== "") {
      grades.push({ student_name, score, comment });
    }
  });

  const btn = document.getElementById("saveGradesBtn");
  btn.disabled = true;
  btn.textContent = "Saving...";

  try {
    await fetchJSON(`${API}/grades`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        item_id: id,
        item_type: type,
        class_id: selected.class_id,
        grades: grades
      })
    });
    const msgEl = document.getElementById("academicMsg");
    msgEl.textContent = "✅ Grades saved successfully!";
    msgEl.className = "tag tag-present";
  } catch (err) {
    const msgEl = document.getElementById("academicMsg");
    msgEl.textContent = "Failed: " + err.message;
    msgEl.className = "tag tag-absent";
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-save"></i> Save All Grades';
  }
}

async function loadGradebook() {
  const viewEl = document.getElementById("gradebookView");
  if (!selected) return;

  try {
    viewEl.innerHTML = "Loading full gradebook...";

    const [exams, homework, allGrades, classes] = await Promise.all([
      fetchJSON(`${API}/exams?class_id=${selected.class_id}&subject_id=${selected.subject_id}`),
      fetchJSON(`${API}/homework?class_id=${selected.class_id}&subject_id=${selected.subject_id}`),
      fetchJSON(`${API}/grades`),
      fetchJSON(`${API}/classes`)
    ]);

    const currentClass = classes.find(c => c.id === selected.class_id);
    const seating = currentClass ? (currentClass.seating || {}) : {};
    const students = Object.values(seating).sort();

    if (students.length === 0) {
      viewEl.innerHTML = '<div style="padding: 1rem; text-align: center;">No students in seating chart.</div>';
      return;
    }

    const items = [
      ...exams.map(e => ({ ...e, type: 'exam' })),
      ...homework.map(h => ({ ...h, type: 'homework' }))
    ];

    let html = `<table style="width: 100%; border-collapse: collapse; font-size: 0.75rem;">
      <thead>
        <tr style="text-align: left; border-bottom: 2px solid rgba(255,255,255,0.1);">
          <th style="padding: 0.5rem; min-width: 120px; position: sticky; left: 0; background: var(--card-bg);">Student</th>`;

    items.forEach(item => {
      html += `<th style="padding: 0.5rem; text-align: center;">${item.title}<br/><span style="font-size: 0.6rem; opacity: 0.6;">${item.type}</span></th>`;
    });
    html += `</tr></thead><tbody>`;

    students.forEach(name => {
      html += `<tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
        <td style="padding: 0.5rem; font-weight: 600; position: sticky; left: 0; background: var(--card-bg);">${name}</td>`;

      items.forEach(item => {
        const grade = allGrades.find(g =>
          g.student_name === name &&
          g.item_type === item.type &&
          String(g.item_id) === String(item.id)
        );
        const score = grade && grade.score !== undefined ? grade.score : "-";
        html += `<td style="padding: 0.5rem; text-align: center;">${score}</td>`;
      });
      html += `</tr>`;
    });

    html += `</tbody></table>`;
    viewEl.innerHTML = html;

  } catch (err) {
    console.error("Failed to load gradebook:", err);
    viewEl.innerHTML = "Error loading gradebook.";
  }
}

function exportToCSV() {
  const table = document.querySelector("#gradebookView table");
  if (!table) {
    alert("No data to export.");
    return;
  }

  let csv = [];
  const rows = table.querySelectorAll("tr");
  for (const row of rows) {
    const cols = row.querySelectorAll("th, td");
    const data = [];
    for (const col of cols) {
      // Remove line breaks for CSV
      data.push('"' + col.innerText.replace(/\n/g, " ") + '"');
    }
    csv.push(data.join(","));
  }

  const csvString = csv.join("\n");
  const blob = new Blob([csvString], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `gradebook_${selected.class_name}_${selected.subject_name}.csv`;
  a.click();
}

async function loadTeacherReports() {
  const viewEl = document.getElementById("reportsView");
  if (!selected) return;

  try {
    viewEl.innerHTML = "Loading reports...";
    const stats = await fetchJSON(`${API}/reports/attendance?class_id=${selected.class_id}`);

    if (stats.length === 0) {
      viewEl.innerHTML = '<div style="padding: 1rem; text-align: center;">No attendance data found for this class.</div>';
      return;
    }

    let html = `
      <div style="margin-bottom: 1.5rem;">
        <h4 style="font-size: 0.9rem; margin-bottom: 0.5rem;"><i class="fa-solid fa-chart-line"></i> Class Attendance Summary</h4>
        <table style="width: 100%; border-collapse: collapse; font-size: 0.8rem;">
          <thead>
            <tr style="text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1);">
              <th style="padding: 0.5rem;">Student</th>
              <th style="padding: 0.5rem; text-align: center;">Sessions</th>
              <th style="padding: 0.5rem; text-align: center;">Present</th>
              <th style="padding: 0.5rem; text-align: center;">Absent</th>
              <th style="padding: 0.5rem; text-align: center;">Attendance %</th>
            </tr>
          </thead>
          <tbody>
    `;

    stats.forEach(s => {
      const color = s.percentage < 75 ? 'var(--accent-secondary)' : 'var(--accent-primary)';
      html += `
        <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
          <td style="padding: 0.6rem;">${s.name}</td>
          <td style="padding: 0.6rem; text-align: center;">${s.total}</td>
          <td style="padding: 0.6rem; text-align: center; color: var(--accent-primary);">${s.present}</td>
          <td style="padding: 0.6rem; text-align: center; color: var(--accent-secondary);">${s.absent}</td>
          <td style="padding: 0.6rem; text-align: center; font-weight: 700; color: ${color};">${s.percentage}%</td>
        </tr>
      `;
    });

    html += `</tbody></table></div>`;
    viewEl.innerHTML = html;

  } catch (err) {
    console.error("Failed to load reports:", err);
    viewEl.innerHTML = "Error loading reports.";
  }
}

function exportReportToCSV() {
  const table = document.querySelector("#reportsView table");
  if (!table) {
    alert("No data to export.");
    return;
  }

  let csv = [];
  const rows = table.querySelectorAll("tr");
  for (const row of rows) {
    const cols = row.querySelectorAll("th, td");
    const data = [];
    for (const col of cols) {
      data.push('"' + col.innerText.replace(/\n/g, " ") + '"');
    }
    csv.push(data.join(","));
  }

  const csvString = csv.join("\n");
  const blob = new Blob([csvString], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `report_${selected.class_name}_${selected.subject_name}.csv`;
  a.click();
}

async function loadAcademicData() {
  if (!selected) return;
  const isHomework = document.getElementById("homeworkContainer").style.display === "block";
  const msgEl = document.getElementById("academicMsg");

  try {
    const endpoint = isHomework ? "homework" : "exams";
    const data = await fetchJSON(`${API}/${endpoint}?class_id=${selected.class_id}&subject_id=${selected.subject_id}`);

    if (data.length > 0) {
      msgEl.innerHTML = `<div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 1rem;">
        Existing ${endpoint}: ${data.length} found.
      </div>`;
    } else {
      msgEl.textContent = `No ${endpoint} found for this class.`;
    }
  } catch (err) {
    console.error("Failed to load academic data:", err);
  }
}

async function loadTeacherStats() {
  try {
    const user = getCurrentUser();
    const [assignments, attendance, grades] = await Promise.all([
      fetchJSON(`${API}/assignments`),
      fetchJSON(`${API}/attendance/records`).catch(() => []),
      fetchJSON(`${API}/grades`).catch(() => [])
    ]);

    const myAssignments = assignments.filter(a => a.teacher_username === user.username);
    const myClassesCount = myAssignments.length;

    // Attendance
    const mySessions = attendance.filter(s => s.teacher_username === user.username);
    let totalRecords = 0;
    let presentRecords = 0;
    mySessions.forEach(s => {
      (s.records || []).forEach(r => {
        totalRecords++;
        if (r.status === "Present") presentRecords++;
      });
    });
    const avgAttendance = totalRecords ? Math.round((presentRecords / totalRecords) * 100) : 0;

    // Graded items (unique student+item_id pairs for this teacher's assignments)
    // We can filter grades by looking at the assignments class_ids
    const myClassIds = new Set(myAssignments.map(a => a.class_id));
    const myGrades = grades.filter(g => myClassIds.has(Number(g.class_id)));
    const gradedCount = myGrades.length;

    if (document.getElementById("statMyClasses")) document.getElementById("statMyClasses").textContent = myClassesCount;
    if (document.getElementById("statMyAttendance")) document.getElementById("statMyAttendance").textContent = `${avgAttendance}%`;
    if (document.getElementById("statMyGraded")) document.getElementById("statMyGraded").textContent = gradedCount;

  } catch (err) {
    console.error("Failed to load teacher stats:", err);
  }
}

(function init() {
  wireUI();
  loadTeacherStats();
  loadTeacherAssignments().catch((err) => {
    console.error(err);
    document.getElementById("status").textContent = "Failed to load assignments: " + err.message;
  });
})();
