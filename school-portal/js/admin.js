const API = "/api";
const TEACHER_PRESENCE_DIRECT_UPLOAD_BYTES = 25 * 1024 * 1024;

/* =========================================================
   Utilities
   ========================================================= */

async function fetchJSON(url, options = {}) {
  const res = await fetch(url, options);
  const data = await readResponse(res);

  if (!res.ok) {
    const detail = data.details ? ` ${data.details}` : "";
    throw new Error(`${data.error || `Request failed (${res.status})`}${detail}`);
  }

  return data;
}

async function readResponse(res) {
  const text = await res.text();

  try {
    return text ? JSON.parse(text) : {};
  } catch {
    const plain = text
      .replace(/<[^>]*>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 240);

    return {
      error: plain || `Server returned ${res.status} ${res.statusText}`
    };
  }
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

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
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

    const teacherSelects = [
      document.getElementById("teacherSelect"),
      document.getElementById("presenceTeacherSelect")
    ].filter(Boolean);
    const classSelects = [
      document.getElementById("classSelect"),
      document.getElementById("presenceClassSelect")
    ].filter(Boolean);
    const assignmentSubjectSelect = document.getElementById("subjectSelect");
    const presenceSubjectSelect = document.getElementById("presenceSubjectSelect");
    const subjectSelects = [
      assignmentSubjectSelect,
      presenceSubjectSelect
    ].filter(Boolean);

    if (!teacherSelects.length && !classSelects.length && !subjectSelects.length) return;

    teacherSelects.forEach(sel => {
      sel.innerHTML = '<option value="">-- Choose Teacher --</option>';
    });
    classSelects.forEach(sel => {
      sel.innerHTML = '<option value="">-- Choose Class --</option>';
    });
    if (assignmentSubjectSelect) {
      assignmentSubjectSelect.innerHTML = '<option value="">-- Choose Subject --</option>';
    }

    if (presenceSubjectSelect) {
      presenceSubjectSelect.innerHTML = '<option value="">-- Optional Subject --</option>';
    }

    teachers.forEach(t => {
      teacherSelects.forEach(sel => {
        option(sel, t.username, `${t.name || t.username} (${t.username})`);
      });
    });

    classes.forEach(c => {
      classSelects.forEach(sel => {
        option(sel, c.id, `${c.name} [${c.rows}x${c.cols}]`);
      });
    });

    subjects.forEach(s => {
      subjectSelects.forEach(sel => {
        option(sel, s.id, s.name);
      });
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

function setTeacherPresenceMsg(text, isError = false) {
  const el = document.getElementById("teacherPresenceMsg");
  if (!el) return;

  el.className = isError ? "tag tag-absent" : "tag tag-present";
  el.textContent = text || "";
  el.style.display = text ? "inline-block" : "none";
}

function selectedPresenceValue(id) {
  return document.getElementById(id)?.value || "";
}

function teacherPresencePayload() {
  const teacherUsername = selectedPresenceValue("presenceTeacherSelect");
  const classId = selectedPresenceValue("presenceClassSelect");
  const subjectId = selectedPresenceValue("presenceSubjectSelect");

  if (!teacherUsername || !classId) {
    throw new Error("Choose a teacher and class before uploading.");
  }

  return {
    teacher_username: teacherUsername,
    class_id: classId,
    subject_id: subjectId || undefined
  };
}

function appendTeacherPresenceMetadata(formData, payload) {
  formData.append("teacher_username", payload.teacher_username);
  formData.append("class_id", payload.class_id);

  if (payload.subject_id) {
    formData.append("subject_id", payload.subject_id);
  }
}

async function uploadTeacherPresenceVideo(file) {
  if (!file) {
    throw new Error("Choose a video first.");
  }

  const payload = teacherPresencePayload();

  if (file.size > TEACHER_PRESENCE_DIRECT_UPLOAD_BYTES) {
    return uploadTeacherPresenceVideoViaGcs(file, payload);
  }

  return uploadTeacherPresenceVideoDirectly(file, payload);
}

async function uploadTeacherPresenceVideoDirectly(file, payload) {
  const formData = new FormData();
  formData.append("file", file);
  appendTeacherPresenceMetadata(formData, payload);

  return fetchJSON(`${API}/teacher-attendance/upload`, {
    method: "POST",
    body: formData
  });
}

async function uploadTeacherPresenceVideoViaGcs(file, payload) {
  setTeacherPresenceMsg("Preparing large video upload...");

  const ticket = await fetchJSON(`${API}/attendance/gcs-upload-url`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "application/octet-stream"
    })
  });

  setTeacherPresenceMsg("Uploading video to Cloud Storage...");

  let uploadRes;

  try {
    uploadRes = await fetch(ticket.upload_url, {
      method: "PUT",
      headers: {
        "Content-Type": file.type || "application/octet-stream"
      },
      body: file
    });
  } catch (err) {
    throw new Error(
      `Cloud Storage upload could not be reached. ${err.message}. ` +
      "Check the bucket CORS policy allows PUT from this site."
    );
  }

  if (!uploadRes.ok) {
    const uploadText = await uploadRes.text();
    throw new Error(
      `Cloud Storage upload failed (${uploadRes.status}). ` +
      uploadText.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 300)
    );
  }

  setTeacherPresenceMsg("Checking uploaded video for teacher near the board...");

  return fetchJSON(`${API}/teacher-attendance/process-gcs-video`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      object_name: ticket.object_name,
      ...payload
    })
  });
}

async function handleTeacherPresenceUploadChange(event) {
  const input = event.target;
  const file = input.files?.[0];
  const uploadBtn = document.getElementById("uploadTeacherPresenceBtn");
  const originalButtonHtml = uploadBtn?.innerHTML || "";

  if (!file) return;

  try {
    if (uploadBtn) {
      uploadBtn.disabled = true;
      uploadBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Checking...';
    }

    setTeacherPresenceMsg("Checking video for teacher near the board...");
    const data = await uploadTeacherPresenceVideo(file);
    const result = data.teacher_presence || {};
    const confidence = Number(result.best_confidence || 0);
    const best = confidence ? `, best ${(confidence * 100).toFixed(0)}%` : "";
    const needed = Number(result.min_required_frames || 0);
    const requirement = needed ? `, need ${needed}` : "";
    const faceFrames = Number(result.face_teacher_frames || result.face_frames || 0);
    const rawPersonFrames = Number(result.raw_person_frames || 0);
    const detail = `, faces ${faceFrames}, raw people ${rawPersonFrames}`;

    setTeacherPresenceMsg(
      `Teacher ${result.status || "checked"}: ${result.teacher_frames || 0}/${result.frames_checked || 0} teacher frames${requirement}${best}${detail}.`,
      result.status === "Absent"
    );
    await loadTeacherPresenceRecords();
  } catch (err) {
    console.error("Teacher presence upload failed:", err);
    setTeacherPresenceMsg(err.message, true);
  } finally {
    if (uploadBtn) {
      uploadBtn.disabled = false;
      uploadBtn.innerHTML = originalButtonHtml;
    }

    input.value = "";
  }
}

async function loadTeacherPresenceRecords() {
  const viewEl = document.getElementById("teacherPresenceView");
  if (!viewEl) return;

  try {
    viewEl.innerHTML = "Loading teacher presence...";

    const [records, classes] = await Promise.all([
      fetchJSON(`${API}/teacher-attendance/records`).catch(() => []),
      fetchJSON(`${API}/classes`).catch(() => [])
    ]);
    const classById = new Map(classes.map(c => [str(c.id), c]));
    const sorted = [...records].sort((a, b) =>
      str(b.timestamp).localeCompare(str(a.timestamp))
    );

    if (!sorted.length) {
      viewEl.innerHTML = '<div class="tag tag-late">No teacher presence records yet.</div>';
      return;
    }

    const rows = sorted.slice(0, 30).map(record => {
      const status = record.status || (record.teacher_present ? "Present" : "Absent");
      const statusClass = status === "Present" ? "tag tag-present" : "tag tag-absent";
      const className = record.class_name || classById.get(str(record.class_id))?.name || `Class ${record.class_id || ""}`;
      const confidence = Number(record.best_confidence || 0);

      return `
        <tr style="border-bottom:1px solid rgba(0,0,0,0.05);">
          <td style="padding:0.75rem;">${escapeHtml(record.teacher_username)}</td>
          <td style="padding:0.75rem;">${escapeHtml(className)}</td>
          <td style="padding:0.75rem;">${escapeHtml(record.subject_name || "-")}</td>
          <td style="padding:0.75rem;">${escapeHtml(record.timestamp || record.date || "-")}</td>
          <td style="padding:0.75rem;text-align:center;">
            <span class="${statusClass}">${escapeHtml(status)}</span>
          </td>
          <td style="padding:0.75rem;text-align:center;">${record.teacher_frames || 0}/${record.frames_checked || 0}</td>
          <td style="padding:0.75rem;text-align:center;">${confidence ? `${(confidence * 100).toFixed(0)}%` : "-"}</td>
        </tr>
      `;
    }).join("");

    viewEl.innerHTML = `
      <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
        <thead>
          <tr style="text-align:left;border-bottom:1px solid var(--border-color);">
            <th style="padding:0.5rem;">Teacher Username</th>
            <th style="padding:0.5rem;">Class</th>
            <th style="padding:0.5rem;">Subject</th>
            <th style="padding:0.5rem;">Time</th>
            <th style="padding:0.5rem;text-align:center;">Status</th>
            <th style="padding:0.5rem;text-align:center;">Teacher Frames</th>
            <th style="padding:0.5rem;text-align:center;">Best</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  } catch (err) {
    console.error("Failed to load teacher presence:", err);
    viewEl.innerHTML = '<div class="tag tag-absent">Error loading teacher presence.</div>';
  }
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
  document.getElementById("refreshTeacherPresenceBtn")?.addEventListener("click", loadTeacherPresenceRecords);
  document.getElementById("teacherPresenceVideoUpload")?.addEventListener("change", handleTeacherPresenceUploadChange);
  document.getElementById("uploadTeacherPresenceBtn")?.addEventListener("click", () => {
    try {
      if (!selectedPresenceValue("presenceTeacherSelect") || !selectedPresenceValue("presenceClassSelect")) {
        throw new Error("Choose a teacher and class before uploading.");
      }

      setTeacherPresenceMsg("");
      document.getElementById("teacherPresenceVideoUpload")?.click();
    } catch (err) {
      setTeacherPresenceMsg(err.message, true);
    }
  });

  const navMap = {
    navDashboard: "all",
    navTeachers: "cardTeachers",
    navStudents: "cardStudents",
    navClasses: "cardClasses",
    navSubjects: "cardSubjects",
    navAssignments: "cardAssignments",
    navTeacherPresence: "teacherPresencePanel",
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
    loadDashboardStats(),
    loadTeacherPresenceRecords()
  ]);
});
