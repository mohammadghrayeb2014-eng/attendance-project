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

function safeDate(session) {
  const raw = session.timestamp || session.date;

  if (!raw) return "Unknown date";

  const d = new Date(raw);

  if (Number.isNaN(d.getTime())) {
    return String(raw).split(" ")[0];
  }

  return d.toLocaleDateString();
}

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) node.textContent = text;
}

/* =========================================================
   Load Student Dashboard
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

  const gradeListEl = document.getElementById("gradesList");
  const attListEl = document.getElementById("attendanceList");

  if (gradeListEl) {
    gradeListEl.innerHTML = '<div class="text-center text-muted" style="padding: 2rem;">Loading grades...</div>';
  }

  if (attListEl) {
    attListEl.innerHTML = '<div class="text-center text-muted" style="padding: 2rem;">Loading attendance...</div>';
  }

  try {
    const [allGrades, exams, homework, attendance, subjects] = await Promise.all([
      fetchJSON(`${API}/grades`).catch(() => []),
      fetchJSON(`${API}/exams`).catch(() => []),
      fetchJSON(`${API}/homework`).catch(() => []),
      fetchJSON(`${API}/attendance/records`).catch(() => []),
      fetchJSON(`${API}/subjects`).catch(() => [])
    ]);

    const subjectMap = new Map(
      subjects.map(s => [String(s.id), s.name])
    );

    const studentName = normalize(user.name);
    const studentUser = normalize(user.username);

    const myGrades = allGrades.filter(g => {
      const gradeStudent = normalize(g.student_name);

      return gradeStudent === studentName || gradeStudent === studentUser;
    });

    renderGrades(myGrades, exams, homework, subjectMap);
    renderAttendance(attendance, studentName, studentUser);

  } catch (err) {
    console.error("Failed to load student dashboard:", err);

    if (gradeListEl) {
      gradeListEl.innerHTML = `
        <div class="tag tag-absent" style="margin: 1rem;">
          Failed to load student data: ${err.message}
        </div>
      `;
    }

    if (attListEl) {
      attListEl.innerHTML = `
        <div class="tag tag-absent" style="margin: 1rem;">
          Failed to load attendance records.
        </div>
      `;
    }
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

      return recordName === studentName || recordName === studentUser;
    });

    if (!me || count >= 10) return;

    count++;

    const div = el("div", "item", "");
    div.style.padding = "0.75rem";
    div.style.display = "flex";
    div.style.justifyContent = "space-between";
    div.style.alignItems = "center";
    div.style.borderBottom = "1px solid rgba(255,255,255,0.05)";

    const date = safeDate(session);
    const isPresent = me.status === "Present";

    div.innerHTML = `
      <div style="font-size: 0.85rem;">${date}</div>
      <div 
        class="${isPresent ? "tag tag-present" : "tag tag-absent"}" 
        style="font-size: 0.8rem; font-weight: 600;"
      >
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