// teacher.js
const API = "/api";
const ACTIVE_KEY = "active_assignment";

let allItems = [];
let selected = null;

async function fetchJSON(url, options = {}) {
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

function normalize(v) {
  return String(v || "").trim().toLowerCase();
}

function sameId(a, b) {
  return String(a) === String(b);
}

function showMsg(text, isError = false) {
  const msgEl = document.getElementById("academicMsg");
  if (!msgEl) return;

  msgEl.textContent = text || "";
  msgEl.className = isError ? "tag tag-absent" : "tag tag-present";
  msgEl.style.display = text ? "inline-block" : "none";
}

function getSelectedOrAlert() {
  if (!selected) {
    alert("Please select a class first.");
    document.getElementById("panelClasses")?.scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
    return null;
  }
  return selected;
}

function setSelectedUI(item) {
  const box = document.getElementById("selectedBox");
  if (!box) return;

  box.innerHTML = "";
  box.style.display = "flex";
  box.style.flexDirection = "column";
  box.style.gap = "0.5rem";

  box.innerHTML = `
    <div style="font-size:1.25rem;font-weight:800;color:var(--p-600);">
      <i class="fa-solid fa-graduation-cap" style="margin-right:0.5rem;"></i>
      ${item.class_name}
    </div>
    <div style="font-size:1rem;font-weight:600;color:var(--text-main);">
      ${item.subject_name}
    </div>
    <div class="pillrow" style="margin-top:0.5rem;">
      <div class="pill"><i class="fa-solid fa-chair"></i> ${item.rows}x${item.cols}</div>
      <div class="pill"><i class="fa-solid fa-hashtag"></i> Class ID: ${item.class_id}</div>
      <div class="pill"><i class="fa-solid fa-book"></i> Subject ID: ${item.subject_id}</div>
    </div>
  `;

  const openBtn = document.getElementById("openBtn");
  if (openBtn) openBtn.disabled = false;

  const status = document.getElementById("status");
  if (status) status.textContent = "";
}

async function loadTeacherAssignments() {
  const user = getCurrentUser();

  if (!user) {
    window.location.href = "login.html";
    return;
  }

  const username = normalize(user.username);

  const [assignments, classes, subjects] = await Promise.all([
    fetchJSON(`${API}/assignments`),
    fetchJSON(`${API}/classes`),
    fetchJSON(`${API}/subjects`)
  ]);

  const classById = new Map(classes.map(c => [String(c.id), c]));
  const subjectById = new Map(subjects.map(s => [String(s.id), s]));

  const teacher_username =
  normalize(getCurrentUser()?.username);

  const mine = assignments.filter(
    a => normalize(a.teacher_username) === teacher_username);

  allItems = mine.map(a => {
    const c = classById.get(String(a.class_id));
    const s = subjectById.get(String(a.subject_id));

    return {
      teacher_username: a.teacher_username,
      class_id: Number(a.class_id),
      subject_id: Number(a.subject_id),
      class_name: c?.name || "Unknown class",
      subject_name: s?.name || "Unknown subject",
      rows: c?.rows || 0,
      cols: c?.cols || 0,
      seating: c?.seating || {}
    };
  });

  selected = null;

  const selectedBox = document.getElementById("selectedBox");
  if (selectedBox) {
    selectedBox.textContent = "Select a classroom from the left to initialize a live session.";
  }

  const openBtn = document.getElementById("openBtn");
  if (openBtn) openBtn.disabled = true;

  renderList(allItems);
}

function renderList(items) {
  const list = document.getElementById("list");
  const emptyMsg = document.getElementById("emptyMsg");

  if (!list) return;

  list.innerHTML = "";

  if (emptyMsg) {
    emptyMsg.style.display = items.length === 0 ? "block" : "none";
  }

  items.forEach(item => {
    const row = el("div", "item");
    const left = el("div", "meta");

    left.innerHTML = `
      <div class="title">${item.class_name} — ${item.subject_name}</div>
      <div class="sub">Class ID: ${item.class_id} • Subject ID: ${item.subject_id}</div>
      <div class="pillrow">
        <div class="pill">${item.rows} x ${item.cols} seats</div>
        <div class="pill">Teacher: ${item.teacher_username}</div>
      </div>
    `;

    const right = el("div");
    const btn = el("button", "btn-premium-sm", "Select");

    btn.addEventListener("click", () => {
      selected = item;
      setSelectedUI(item);
      loadAcademicData();
    });

    right.appendChild(btn);
    row.appendChild(left);
    row.appendChild(right);
    list.appendChild(row);
  });
}

function applySearch() {
  const q = normalize(document.getElementById("searchInput")?.value);

  if (!q) {
    renderList(allItems);
    return;
  }

  renderList(
    allItems.filter(i =>
      normalize(i.class_name).includes(q) ||
      normalize(i.subject_name).includes(q)
    )
  );
}

async function loadAcademicData() {
  if (!selected) return;

  try {
    const [exams, homework] = await Promise.all([
      fetchJSON(`${API}/exams?class_id=${selected.class_id}&subject_id=${selected.subject_id}`).catch(() => []),
      fetchJSON(`${API}/homework?class_id=${selected.class_id}&subject_id=${selected.subject_id}`).catch(() => [])
    ]);

    showMsg(`Loaded ${exams.length} exam(s) and ${homework.length} homework item(s) for this class.`);
  } catch (err) {
    console.error("Failed to load academic data:", err);
    showMsg("Failed to load academic data.", true);
  }
}

async function createExam() {
  const item = getSelectedOrAlert();
  if (!item) return;

  const title = document.getElementById("examTitle")?.value.trim();
  const date = document.getElementById("examDate")?.value;
  const kind = document.getElementById("examKind")?.value || "exam";

  if (!title || !date) {
    showMsg("Please fill exam title and date.", true);
    return;
  }

  try {
    const user = getCurrentUser();

    await fetchJSON(`${API}/exams`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_username: user.username,
        class_id: item.class_id,
        subject_id: item.subject_id,
        title,
        kind,
        date
      })
    });

    document.getElementById("examTitle").value = "";
    document.getElementById("examDate").value = "";

    showMsg("✅ Exam created successfully.");
    await loadAcademicData();
  } catch (err) {
    console.error("Create exam failed:", err);
    showMsg("Failed to create exam: " + err.message, true);
  }
}

async function createHomework() {
  const item = getSelectedOrAlert();
  if (!item) return;

  const title = document.getElementById("hwTitle")?.value.trim();
  const due_date = document.getElementById("hwDueDate")?.value;
  const description = document.getElementById("hwDesc")?.value.trim() || "";

  if (!title || !due_date) {
    showMsg("Please fill homework title and due date.", true);
    return;
  }

  try {
    const user = getCurrentUser();

    await fetchJSON(`${API}/homework`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        teacher_username: user.username,
        class_id: item.class_id,
        subject_id: item.subject_id,
        title,
        description,
        due_date
      })
    });

    document.getElementById("hwTitle").value = "";
    document.getElementById("hwDueDate").value = "";
    if (document.getElementById("hwDesc")) document.getElementById("hwDesc").value = "";

    showMsg("✅ Homework posted successfully.");
    await loadAcademicData();
  } catch (err) {
    console.error("Create homework failed:", err);
    showMsg("Failed to create homework: " + err.message, true);
  }
}

async function loadGradingItems() {
  const select = document.getElementById("gradeItemSelect");
  const listEl = document.getElementById("gradingList");
  const saveBtn = document.getElementById("saveGradesBtn");

  if (!select) return;

  if (!selected) {
    select.innerHTML = '<option value="">-- Select a class first --</option>';
    if (listEl) listEl.innerHTML = '<div style="padding:1rem;">Select a class first.</div>';
    if (saveBtn) saveBtn.style.display = "none";
    return;
  }

  try {
    const [exams, homework] = await Promise.all([
      fetchJSON(`${API}/exams?class_id=${selected.class_id}&subject_id=${selected.subject_id}`).catch(() => []),
      fetchJSON(`${API}/homework?class_id=${selected.class_id}&subject_id=${selected.subject_id}`).catch(() => [])
    ]);

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

    if (listEl) listEl.innerHTML = '<div style="padding:1rem;text-align:center;">Choose an item to grade.</div>';
    if (saveBtn) saveBtn.style.display = "none";
  } catch (err) {
    console.error("Failed to load grading items:", err);
    if (listEl) listEl.innerHTML = "Failed to load grading items.";
  }
}

async function getStudentsInSelectedClass() {
  if (!selected) return [];

  const classes = await fetchJSON(`${API}/classes`);
  const currentClass = classes.find(c => sameId(c.id, selected.class_id));
  if (!currentClass) return [];

  const seating = currentClass.seating || {};

  const students = Object.values(seating)
    .map(v => {
      if (typeof v === "string") {
        return { name: v, username: normalize(v) };
      }

      if (v && typeof v === "object") {
        return {
          name: v.name || v.username || "",
          username: v.username || normalize(v.name)
        };
      }

      return null;
    })
    .filter(s => s && s.name);

  const unique = new Map();

  students.forEach(s => {
    unique.set(normalize(s.username || s.name), s);
  });

  return Array.from(unique.values()).sort((a, b) =>
    a.name.localeCompare(b.name)
  );
}

async function loadGradingList() {
  const val = document.getElementById("gradeItemSelect")?.value;
  const listEl = document.getElementById("gradingList");
  const saveBtn = document.getElementById("saveGradesBtn");

  if (!listEl || !saveBtn) return;

  if (!val || !selected) {
    listEl.innerHTML = '<div style="padding:1rem;text-align:center;">Select an item to grade.</div>';
    saveBtn.style.display = "none";
    return;
  }

  const [type, id] = val.split("_");

  try {
    listEl.innerHTML = "Loading students...";

    const students = await getStudentsInSelectedClass();

    if (students.length === 0) {
      listEl.innerHTML = `
        <div style="padding:1rem;text-align:center;">
          No students found in this class seating chart. Add students to seats first.
        </div>
      `;
      saveBtn.style.display = "none";
      return;
    }

    const existingGrades = await fetchJSON(
      `${API}/grades?item_id=${id}&item_type=${type}&class_id=${selected.class_id}`
    ).catch(() => []);

    listEl.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
        <thead>
          <tr style="text-align:left;border-bottom:1px solid rgba(255,255,255,0.1);">
            <th style="padding:0.5rem;">Student</th>
            <th style="padding:0.5rem;width:90px;">Score</th>
            <th style="padding:0.5rem;">Comment</th>
          </tr>
        </thead>
        <tbody id="gradingTableBody"></tbody>
      </table>
    `;

    const tbody = document.getElementById("gradingTableBody");

    students.forEach(student => {
      const g = existingGrades.find(x =>
        normalize(x.student_name) === normalize(student.name) ||
        normalize(x.student_username) === normalize(student.username)
      ) || {};

      const tr = document.createElement("tr");
      tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";

      tr.innerHTML = `
        <td style="padding:0.75rem;">${student.name}</td>

        <td style="padding:0.75rem;">
          <input
            type="number"
            min="0"
            max="100"
            class="grade-score input-field"
            data-student-name="${student.name}"
            data-student-username="${student.username}"
            value="${g.score || ""}"
            style="margin-bottom:0;padding:0.35rem;font-size:0.8rem;width:75px;"
          >
        </td>

        <td style="padding:0.75rem;">
          <input
            type="text"
            class="grade-comment input-field"
            data-student-name="${student.name}"
            data-student-username="${student.username}"
            value="${g.comment || ""}"
            style="margin-bottom:0;padding:0.35rem;font-size:0.8rem;"
            placeholder="Note..."
          >
        </td>
      `;

      tbody.appendChild(tr);
    });

    saveBtn.style.display = "block";
  } catch (err) {
    console.error("Failed to load grading list:", err);
    listEl.innerHTML = "Error loading students.";
    saveBtn.style.display = "none";
  }
}

async function saveGrades() {
  const val = document.getElementById("gradeItemSelect")?.value;

  if (!val || !selected) {
    alert("Select a class and grading item first.");
    return;
  }

  const [type, id] = val.split("_");
  const scores = document.querySelectorAll(".grade-score");
  const comments = document.querySelectorAll(".grade-comment");

  const grades = [];

  scores.forEach((input, i) => {
    const student_name = input.dataset.studentName;
    const student_username = input.dataset.studentUsername;
    const score = input.value;
    const comment = comments[i]?.value || "";

    if (score !== "") {
      grades.push({
        student_name,
        student_username,
        score,
        comment
      });
    }
  });

  const btn = document.getElementById("saveGradesBtn");

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Saving...";
  }

  try {
    const result = await fetchJSON(`${API}/grades`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        item_id: id,
        item_type: type,
        class_id: selected.class_id,
        grades
      })
    });

    showMsg(`✅ Grades saved successfully. Saved: ${result.saved}`);

    await loadGradingList();
    await loadGradebook();
    await loadTeacherStats();
  } catch (err) {
    console.error("Save grades failed:", err);
    showMsg("Failed to save grades: " + err.message, true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-save"></i> Save All Grades';
    }
  }
}

async function loadGradebook() {
  const viewEl = document.getElementById("gradebookView");
  if (!viewEl) return;

  if (!selected) {
    viewEl.innerHTML = '<div style="padding:1rem;">Select a class first.</div>';
    return;
  }

  try {
    viewEl.innerHTML = "Loading full gradebook...";

    const [exams, homework, allGrades] = await Promise.all([
      fetchJSON(`${API}/exams?class_id=${selected.class_id}&subject_id=${selected.subject_id}`).catch(() => []),
      fetchJSON(`${API}/homework?class_id=${selected.class_id}&subject_id=${selected.subject_id}`).catch(() => []),
      fetchJSON(`${API}/grades?class_id=${selected.class_id}`).catch(() => [])
    ]);

    const students = await getStudentsInSelectedClass();

    if (students.length === 0) {
      viewEl.innerHTML = '<div style="padding:1rem;text-align:center;">No students in seating chart.</div>';
      return;
    }

    const items = [
      ...exams.map(e => ({ ...e, type: "exam" })),
      ...homework.map(h => ({ ...h, type: "homework" }))
    ];

    if (items.length === 0) {
      viewEl.innerHTML = '<div style="padding:1rem;text-align:center;">No exams or homework created yet.</div>';
      return;
    }

    let html = `
      <table style="width:100%;border-collapse:collapse;font-size:0.75rem;">
        <thead>
          <tr style="text-align:left;border-bottom:2px solid rgba(255,255,255,0.1);">
            <th style="padding:0.5rem;min-width:120px;">Student</th>
    `;

    items.forEach(item => {
      html += `
        <th style="padding:0.5rem;text-align:center;">
          ${item.title}<br>
          <span style="font-size:0.6rem;opacity:0.6;">${item.type}</span>
        </th>
      `;
    });

    html += `</tr></thead><tbody>`;

    students.forEach(student => {
      html += `
        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
          <td style="padding:0.5rem;font-weight:600;">${student.name}</td>
      `;

      items.forEach(item => {
        const grade = allGrades.find(g =>
          (
            normalize(g.student_name) === normalize(student.name) ||
            normalize(g.student_username) === normalize(student.username)
          ) &&
          g.item_type === item.type &&
          sameId(g.item_id, item.id)
        );

        const score = grade && grade.score !== undefined ? grade.score : "-";

        html += `<td style="padding:0.5rem;text-align:center;">${score}</td>`;
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

async function loadTeacherReports() {
  const viewEl = document.getElementById("reportsView");
  if (!viewEl) return;

  if (!selected) {
    viewEl.innerHTML = '<div style="padding:1rem;">Select a class first.</div>';
    return;
  }

  try {
    viewEl.innerHTML = "Loading reports...";

    const stats = await fetchJSON(`${API}/reports/attendance?class_id=${selected.class_id}`).catch(() => []);

    if (stats.length === 0) {
      viewEl.innerHTML = '<div style="padding:1rem;text-align:center;">No attendance data found for this class.</div>';
      return;
    }

    let html = `
      <table style="width:100%;border-collapse:collapse;font-size:0.8rem;">
        <thead>
          <tr style="text-align:left;border-bottom:1px solid rgba(255,255,255,0.1);">
            <th style="padding:0.5rem;">Student</th>
            <th style="padding:0.5rem;text-align:center;">Sessions</th>
            <th style="padding:0.5rem;text-align:center;">Present</th>
            <th style="padding:0.5rem;text-align:center;">Absent</th>
            <th style="padding:0.5rem;text-align:center;">Attendance %</th>
          </tr>
        </thead>
        <tbody>
    `;

    stats.forEach(s => {
      const color = s.percentage < 75 ? "var(--accent-secondary)" : "var(--accent-primary)";

      html += `
        <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
          <td style="padding:0.6rem;">${s.name}</td>
          <td style="padding:0.6rem;text-align:center;">${s.total}</td>
          <td style="padding:0.6rem;text-align:center;color:var(--accent-primary);">${s.present}</td>
          <td style="padding:0.6rem;text-align:center;color:var(--accent-secondary);">${s.absent}</td>
          <td style="padding:0.6rem;text-align:center;font-weight:700;color:${color};">${s.percentage}%</td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
    viewEl.innerHTML = html;
  } catch (err) {
    console.error("Failed to load reports:", err);
    viewEl.innerHTML = "Error loading reports.";
  }
}

function exportTableToCSV(tableSelector, filename) {
  const table = document.querySelector(tableSelector);

  if (!table) {
    alert("No data to export.");
    return;
  }

  const csv = [];
  const rows = table.querySelectorAll("tr");

  rows.forEach(row => {
    const cols = row.querySelectorAll("th, td");
    const data = [];

    cols.forEach(col => {
      data.push('"' + col.innerText.replace(/\n/g, " ").replace(/"/g, '""') + '"');
    });

    csv.push(data.join(","));
  });

  const blob = new Blob([csv.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = filename;
  a.click();

  URL.revokeObjectURL(url);
}

function exportGradebookToCSV() {
  if (!selected) return;

  exportTableToCSV(
    "#gradebookView table",
    `gradebook_${selected.class_name}_${selected.subject_name}.csv`
  );
}

function exportReportToCSV() {
  if (!selected) return;

  exportTableToCSV(
    "#reportsView table",
    `report_${selected.class_name}_${selected.subject_name}.csv`
  );
}

async function loadTeacherStats() {
  try {
    const user = getCurrentUser();
    if (!user) return;

    const [assignments, attendance, grades] = await Promise.all([
      fetchJSON(`${API}/assignments`).catch(() => []),
      fetchJSON(`${API}/attendance/records`).catch(() => []),
      fetchJSON(`${API}/grades`).catch(() => [])
    ]);

    const username = normalize(user.username);

    const myAssignments = assignments.filter(a =>
      normalize(a.teacher_username) === username
    );

    const myClassIds = new Set(myAssignments.map(a => String(a.class_id)));

    const mySessions = attendance.filter(s =>
      normalize(s.teacher_username) === username ||
      myClassIds.has(String(s.class_id))
    );

    let totalRecords = 0;
    let presentRecords = 0;

    mySessions.forEach(s => {
      (s.records || []).forEach(r => {
        totalRecords++;
        if (r.status === "Present") presentRecords++;
      });
    });

    const avgAttendance = totalRecords
      ? Math.round((presentRecords / totalRecords) * 100)
      : 0;

    const myGrades = grades.filter(g => myClassIds.has(String(g.class_id)));

    if (document.getElementById("statMyClasses")) {
      document.getElementById("statMyClasses").textContent = myAssignments.length;
    }

    if (document.getElementById("statMyAttendance")) {
      document.getElementById("statMyAttendance").textContent = `${avgAttendance}%`;
    }

    if (document.getElementById("statMyGraded")) {
      document.getElementById("statMyGraded").textContent = myGrades.length;
    }
  } catch (err) {
    console.error("Failed to load teacher stats:", err);
  }
}

function showTab(tabId, containerId) {
  const tabs = ["tabExam", "tabHomework", "tabGrading", "tabGradebook", "tabReports"];
  const containers = ["examContainer", "homeworkContainer", "gradingContainer", "gradebookContainer", "reportsContainer"];

  tabs.forEach(t => {
    document.getElementById(t)?.classList.remove("active-tab");
    document.getElementById(t)?.classList.remove("active");
  });

  containers.forEach(c => {
    const node = document.getElementById(c);
    if (node) node.style.display = "none";
  });

  document.getElementById(tabId)?.classList.add("active-tab");
  document.getElementById(tabId)?.classList.add("active");

  const target = document.getElementById(containerId);
  if (target) target.style.display = "block";

  showMsg("");

  if (tabId === "tabGrading") loadGradingItems();
  if (tabId === "tabGradebook") loadGradebook();
  if (tabId === "tabReports") loadTeacherReports();
  if (tabId === "tabExam" || tabId === "tabHomework") loadAcademicData();
}

function wireUI() {
  document.getElementById("navMyClasses")?.addEventListener("click", e => {
    e.preventDefault();
    document.getElementById("panelClasses")?.scrollIntoView({
      behavior: "smooth",
      block: "start"
    });
  });

  document.getElementById("navLiveSession")?.addEventListener("click", e => {
    e.preventDefault();

    if (selected) {
      document.getElementById("openBtn")?.click();
    } else {
      alert("Please select a class first.");
      document.getElementById("panelClasses")?.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
    }
  });

  document.getElementById("navAttendance")?.addEventListener("click", e => {
    e.preventDefault();
    showTab("tabReports", "reportsContainer");
  });

  document.getElementById("searchInput")?.addEventListener("input", applySearch);

  document.getElementById("clearBtn")?.addEventListener("click", () => {
    const input = document.getElementById("searchInput");
    if (input) input.value = "";
    applySearch();
  });

  document.getElementById("openBtn")?.addEventListener("click", () => {
    if (!selected) return;
    localStorage.setItem(ACTIVE_KEY, JSON.stringify(selected));
    window.location.href = "class.html";
  });

  document.getElementById("tabExam")?.addEventListener("click", () => showTab("tabExam", "examContainer"));
  document.getElementById("tabHomework")?.addEventListener("click", () => showTab("tabHomework", "homeworkContainer"));
  document.getElementById("tabGrading")?.addEventListener("click", () => showTab("tabGrading", "gradingContainer"));
  document.getElementById("tabGradebook")?.addEventListener("click", () => showTab("tabGradebook", "gradebookContainer"));
  document.getElementById("tabReports")?.addEventListener("click", () => showTab("tabReports", "reportsContainer"));

  document.getElementById("createExamBtn")?.addEventListener("click", createExam);
  document.getElementById("createHwBtn")?.addEventListener("click", createHomework);
  document.getElementById("gradeItemSelect")?.addEventListener("change", loadGradingList);
  document.getElementById("saveGradesBtn")?.addEventListener("click", saveGrades);
  document.getElementById("exportGradesBtn")?.addEventListener("click", exportGradebookToCSV);
  document.getElementById("exportReportsBtn")?.addEventListener("click", exportReportToCSV);

  ["logoutBtn", "headerLogoutBtn"].forEach(id => {
    document.getElementById(id)?.addEventListener("click", e => {
      e.preventDefault();
      logout();
    });
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  protectPage("teacher");

  wireUI();

  await Promise.all([
    loadTeacherStats(),
    loadTeacherAssignments()
  ]);
});