// student.js
const API = "/api";

let studentChart = null;

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

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

function safeDate(value) {
  if (!value) return "No date";

  const d = new Date(value);

  if (Number.isNaN(d.getTime())) {
    return String(value).split(" ")[0];
  }

  return d.toLocaleDateString();
}

function setLoading() {
  const ids = ["gradesList", "attendanceList", "homeworkList", "agendaList"];

  ids.forEach(id => {
    const node = document.getElementById(id);

    if (node) {
      node.innerHTML = `
        <div class="text-center text-muted" style="padding: 2rem;">
          Loading...
        </div>
      `;
    }
  });
}

function showStudentError(message) {
  const ids = ["gradesList", "attendanceList", "homeworkList", "agendaList"];

  ids.forEach(id => {
    const node = document.getElementById(id);

    if (node) {
      node.innerHTML = `
        <div class="tag tag-absent" style="margin: 1rem;">
          Failed to load data: ${message}
        </div>
      `;
    }
  });
}

/* =========================================================
   Find which classes the student belongs to
   ========================================================= */

function getStudentClassIds(classes, studentName, studentUser) {
  const ids = new Set();

  classes.forEach(c => {
    const seating = c.seating || {};

    Object.values(seating).forEach(seat => {
      let seatName = "";
      let seatUsername = "";

      if (typeof seat === "object" && seat !== null) {
        seatName = normalize(seat.name);
        seatUsername = normalize(seat.username);
      } else {
        seatName = normalize(seat);
      }

      if (
        seatName === studentName ||
        seatName === studentUser ||
        seatUsername === studentUser
      ) {
        ids.add(String(c.id));
      }
    });
  });

  return ids;
}

/* =========================================================
   Main Load
   ========================================================= */

async function loadStudentData() {
  const user = getCurrentUser();

  if (!user) {
    window.location.href = "login.html";
    return;
  }

  const displayName = user.name || user.username || "Student";

  setText("userName", displayName);

  const avatar = document.getElementById("userAvatar");
  if (avatar) {
    avatar.textContent = displayName[0]?.toUpperCase() || "S";
  }

  setLoading();

  try {
    const [allGrades, exams, homework, attendance, subjects, classes] = await Promise.all([
      fetchJSON(`${API}/grades`).catch(() => []),
      fetchJSON(`${API}/exams`).catch(() => []),
      fetchJSON(`${API}/homework`).catch(() => []),
      fetchJSON(`${API}/attendance/records`).catch(() => []),
      fetchJSON(`${API}/subjects`).catch(() => []),
      fetchJSON(`${API}/classes`).catch(() => [])
    ]);

    const subjectMap = new Map(
      subjects.map(s => [String(s.id), s.name])
    );

    const studentName = normalize(user.name);
    const studentUser = normalize(user.username);

    const myClassIds = getStudentClassIds(classes, studentName, studentUser);

    const myGrades = allGrades.filter(g => {
      const gradeStudent = normalize(g.student_name);

      return gradeStudent === studentName || gradeStudent === studentUser;
    });

    const myHomework = homework.filter(hw =>
      myClassIds.has(String(hw.class_id))
    );

    const myExams = exams.filter(ex =>
      myClassIds.has(String(ex.class_id))
    );

    renderGrades(myGrades, exams, homework, subjectMap);
    renderAttendance(attendance, studentName, studentUser);
    renderHomework(myHomework, subjectMap);
    renderAgenda(myExams, myHomework, subjectMap);

  } catch (err) {
    console.error("Failed to load student dashboard:", err);
    showStudentError(err.message);
  }
}

/* =========================================================
   Grades
   ========================================================= */

function renderGrades(myGrades, exams, homework, subjectMap) {
  const gradeListEl = document.getElementById("gradesList");
  if (!gradeListEl) return;

  gradeListEl.innerHTML = "";

  if (myGrades.length === 0) {
    gradeListEl.innerHTML = `
      <div class="text-center text-muted" style="padding: 2rem;">
        No grades recorded yet.
      </div>
    `;

    clearChart();
    return;
  }

  renderStudentPerformanceChart(myGrades, exams, homework);

  myGrades.forEach(g => {
    let item = null;

    if (g.item_type === "exam") {
      item = exams.find(e => sameId(e.id, g.item_id));
    } else {
      item = homework.find(h => sameId(h.id, g.item_id));
    }

    const subName = item
      ? (subjectMap.get(String(item.subject_id)) || "General")
      : "Unknown";

    const title = item ? item.title : "Deleted Item";

    const div = el("div", "item", "");
    div.style.padding = "1rem";
    div.style.borderBottom = "1px solid rgba(255,255,255,0.05)";

    div.innerHTML = `
      <div class="flex justify-between items-center">
        <div>
          <div class="title" style="font-size: 0.9rem;">${title}</div>
          <div class="sub" style="font-size: 0.7rem; opacity: 0.6;">
            ${subName} • ${g.item_type}
          </div>
        </div>

        <div class="grade-box text-center">
          <div style="font-size: 1.1rem; font-weight: 700; color: var(--accent-secondary);">
            ${g.score}
          </div>
          <div style="font-size: 0.6rem; opacity: 0.5;">Score</div>
        </div>
      </div>

      ${
        g.comment
          ? `<div style="font-size: 0.75rem; margin-top: 0.5rem; color: var(--text-secondary); font-style: italic;">"${g.comment}"</div>`
          : ""
      }
    `;

    gradeListEl.appendChild(div);
  });
}

/* =========================================================
   Attendance
   ========================================================= */

function renderAttendance(attendance, studentName, studentUser) {
  const attListEl = document.getElementById("attendanceList");
  if (!attListEl) return;

  attListEl.innerHTML = "";

  const recentAtt = attendance.slice().reverse();
  let count = 0;

  recentAtt.forEach(session => {
    const me = (session.records || []).find(r => {
      const recordName = normalize(r.name);
      const recordUser = normalize(r.username);

      return (
        recordName === studentName ||
        recordName === studentUser ||
        recordUser === studentUser
      );
    });

    if (!me || count >= 10) return;

    count++;

    const div = el("div", "item", "");
    div.style.padding = "0.75rem";
    div.style.display = "flex";
    div.style.justifyContent = "space-between";
    div.style.alignItems = "center";
    div.style.borderBottom = "1px solid rgba(255,255,255,0.05)";

    const date = session.date || session.timestamp || "";
    const isPresent = me.status === "Present";

    div.innerHTML = `
      <div style="font-size: 0.85rem;">${safeDate(date)}</div>
      <div class="${isPresent ? "tag tag-present" : "tag tag-absent"}"
        style="font-size: 0.8rem; font-weight: 600;">
        ${me.status}
      </div>
    `;

    attListEl.appendChild(div);
  });

  if (count === 0) {
    attListEl.innerHTML = `
      <div class="text-center text-muted" style="padding: 2rem;">
        No attendance records.
      </div>
    `;
  }
}

/* =========================================================
   Homework
   ========================================================= */

function renderHomework(myHomework, subjectMap) {
  const list = document.getElementById("homeworkList");
  if (!list) return;

  list.innerHTML = "";

  if (myHomework.length === 0) {
    list.innerHTML = `
      <div class="text-center text-muted" style="padding: 2rem;">
        No homework assigned yet.
      </div>
    `;
    return;
  }

  const sorted = myHomework.slice().sort((a, b) =>
    String(a.due_date || "").localeCompare(String(b.due_date || ""))
  );

  sorted.forEach(hw => {
    const subject = subjectMap.get(String(hw.subject_id)) || "General";

    const div = el("div", "item", "");
    div.style.padding = "1rem";
    div.style.borderBottom = "1px solid rgba(255,255,255,0.05)";

    div.innerHTML = `
      <div class="flex justify-between items-center">
        <div>
          <div class="title" style="font-size: 0.9rem;">${hw.title}</div>
          <div class="sub" style="font-size: 0.7rem; opacity: 0.6;">
            ${subject} • Due ${safeDate(hw.due_date)}
          </div>

          ${
            hw.description
              ? `<div style="font-size: 0.75rem; margin-top: 0.5rem; color: var(--text-secondary);">${hw.description}</div>`
              : ""
          }
        </div>

        <div class="tag tag-late" style="font-size: 0.75rem;">
          Homework
        </div>
      </div>
    `;

    list.appendChild(div);
  });
}

/* =========================================================
   Agenda
   ========================================================= */

function renderAgenda(myExams, myHomework, subjectMap) {
  const list = document.getElementById("agendaList");
  if (!list) return;

  list.innerHTML = "";

  const agenda = [
    ...myExams.map(ex => ({
      type: ex.kind || "exam",
      title: ex.title,
      date: ex.date,
      subject_id: ex.subject_id,
      badge: ex.kind || "Exam"
    })),

    ...myHomework.map(hw => ({
      type: "homework",
      title: hw.title,
      date: hw.due_date,
      subject_id: hw.subject_id,
      badge: "Homework"
    }))
  ];

  agenda.sort((a, b) =>
    String(a.date || "").localeCompare(String(b.date || ""))
  );

  if (agenda.length === 0) {
    list.innerHTML = `
      <div class="text-center text-muted" style="padding: 2rem;">
        No upcoming agenda items.
      </div>
    `;
    return;
  }

  agenda.forEach(item => {
    const subject = subjectMap.get(String(item.subject_id)) || "General";

    const div = el("div", "item", "");
    div.style.padding = "1rem";
    div.style.borderBottom = "1px solid rgba(255,255,255,0.05)";

    const badgeText = item.badge.charAt(0).toUpperCase() + item.badge.slice(1);

    div.innerHTML = `
      <div class="flex justify-between items-center">
        <div>
          <div class="title" style="font-size: 0.9rem;">${item.title}</div>
          <div class="sub" style="font-size: 0.7rem; opacity: 0.6;">
            ${subject} • ${safeDate(item.date)}
          </div>
        </div>

        <div class="${item.type === "homework" ? "tag tag-late" : "tag tag-present"}"
          style="font-size: 0.75rem;">
          ${badgeText}
        </div>
      </div>
    `;

    list.appendChild(div);
  });
}

/* =========================================================
   Chart
   ========================================================= */

function clearChart() {
  if (studentChart) {
    studentChart.destroy();
    studentChart = null;
  }
}

function renderStudentPerformanceChart(myGrades, exams, homework) {
  const canvas = document.getElementById("studentPerformanceChart");

  if (!canvas || typeof Chart === "undefined") return;

  const ctx = canvas.getContext("2d");

  const dataPoints = myGrades.map(g => {
    let item = null;

    if (g.item_type === "exam") {
      item = exams.find(e => sameId(e.id, g.item_id));
    } else {
      item = homework.find(h => sameId(h.id, g.item_id));
    }

    const rawScore = parseFloat(g.score);
    const score = Number.isFinite(rawScore) ? rawScore : 0;

    return {
      title: item ? item.title : "Assessment",
      score
    };
  });

  clearChart();

  studentChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: dataPoints.map(d => d.title),
      datasets: [
        {
          label: "Score",
          data: dataPoints.map(d => d.score),
          backgroundColor: "rgba(37, 99, 235, 0.8)",
          hoverBackgroundColor: "#2563eb",
          borderRadius: 12,
          barThickness: 40
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: "#1e293b",
          padding: 12,
          titleFont: {
            size: 14,
            weight: "bold"
          },
          bodyFont: {
            size: 13
          },
          cornerRadius: 8
        }
      },
      scales: {
        y: {
          min: 0,
          max: 100,
          grid: {
            color: "rgba(0,0,0,0.05)",
            borderDash: [5, 5]
          },
          ticks: {
            color: "#64748b",
            font: {
              weight: "600"
            }
          }
        },
        x: {
          grid: {
            display: false
          },
          ticks: {
            color: "#64748b",
            font: {
              weight: "600"
            }
          }
        }
      }
    }
  });
}

/* =========================================================
   Init
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
  protectPage("student");

  document.getElementById("logoutBtn")?.addEventListener("click", (e) => {
    e.preventDefault();
    logout();
  });

  loadStudentData();
});