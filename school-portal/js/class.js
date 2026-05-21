// class.js
const CAM_URL_KEY = "esp32_cam_url";
const CAM_MODE_KEY = "esp32_cam_mode";
const CAM_FPS_KEY = "esp32_cam_fps";
const ACTIVE_KEY = "active_assignment";

const API = "/api";
const MAX_VIDEO_UPLOAD_BYTES = 30 * 1024 * 1024;

let camTimer = null;
let camConnected = false;
let lastFrameAt = 0;
let reconnectTimer = null;
let sessionState = "IDLE";

let allStudents = [];
let currentSaveCallback = null;

function $(id) {
  return document.getElementById(id);
}

function normalize(v) {
  return String(v || "").trim().toLowerCase();
}

function sameId(a, b) {
  return String(a) === String(b);
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

function seatDisplayName(seatValue) {
  if (!seatValue) return "Empty";

  if (typeof seatValue === "object") {
    return seatValue.name || seatValue.username || "Empty";
  }

  return seatValue || "Empty";
}

function seatUsername(seatValue) {
  if (!seatValue) return "";

  if (typeof seatValue === "object") {
    return seatValue.username || "";
  }

  return "";
}

/* =========================================================
   LOAD STUDENTS
   ========================================================= */

async function loadStudents() {
  try {
    const res = await fetch(`${API}/students`);
    const data = await res.json();

    allStudents = Array.isArray(data) ? data : [];

  } catch (err) {
    console.error("Failed to load students:", err);
    allStudents = [];
  }
}

/* =========================================================
   SESSION + CLASS LOADING
   ========================================================= */

async function loadSession() {
  const raw = localStorage.getItem(ACTIVE_KEY);

  if (!raw) {
    window.location.href = "teacher.html";
    return;
  }

  await loadStudents();

  const assignment = JSON.parse(raw);

  $("sessionTitle").textContent = `${assignment.class_name} — ${assignment.subject_name}`;
  $("sessionMeta").textContent = `Class ID: ${assignment.class_id} • Subject ID: ${assignment.subject_id}`;

  try {
    const res = await fetch(`${API}/classes`);
    const classes = await res.json();

    const currentClass = classes.find(c => sameId(c.id, assignment.class_id));

    const seating = currentClass ? (currentClass.seating || {}) : {};
    const rows = currentClass?.rows || assignment.rows || 4;
    const cols = currentClass?.cols || assignment.cols || 6;

    renderGrid(rows, cols, seating, assignment.class_id);

  } catch (e) {
    console.error("Failed to load seating:", e);
    renderGrid(assignment.rows || 4, assignment.cols || 6, {}, assignment.class_id);
  }

  updateSessionUI();
}

/* =========================================================
   SEATING GRID
   ========================================================= */

function renderGrid(rows, cols, seating, classId) {
  const grid = $("seatGrid");

  grid.innerHTML = "";
  grid.style.display = "grid";
  grid.style.gridTemplateColumns = `60px repeat(${cols}, 1fr)`;

  const corner = document.createElement("div");
  grid.appendChild(corner);

  for (let c = 0; c < cols; c++) {
    const head = document.createElement("div");
    head.className = "grid-label";
    head.textContent = c + 1;
    grid.appendChild(head);
  }

  for (let r = 0; r < rows; r++) {
    const rowLabel = document.createElement("div");
    rowLabel.className = "grid-label row-header";
    rowLabel.textContent = String.fromCharCode(65 + r);
    grid.appendChild(rowLabel);

    for (let c = 0; c < cols; c++) {
      const seat = document.createElement("div");
      seat.className = "seat";

      const key = `${r}_${c}`;
      const seatValue = seating[key];

      const studentName = seatDisplayName(seatValue);
      const studentUser = seatUsername(seatValue);
      const seatLabel = `${String.fromCharCode(65 + r)}${c + 1}`;

      if (studentName !== "Empty") {
        seat.classList.add("occupied");
      }

      seat.innerHTML = `
        <strong>${seatLabel}</strong>
        <small>${studentName}</small>
      `;

      seat.onclick = () => {
        openSeatModal(
          seatLabel,
          studentUser,
          async (selectedStudent) => {
            await saveSeat(
              classId,
              r,
              c,
              selectedStudent.name,
              selectedStudent.username
            );

            await loadSession();
          }
        );
      };

      grid.appendChild(seat);
    }
  }

  renderAttendance(seating);
}

/* =========================================================
   ATTENDANCE TABLE
   ========================================================= */

function renderAttendance(seating) {
  const body = $("attendanceBody");
  body.innerHTML = "";

  const entries = Object.entries(seating || {});

  if (entries.length === 0) {
    body.innerHTML = `
      <tr>
        
          No students assigned to seats yet.
        </td>
      </tr>
    `;
    return;
  }

  entries.sort((a, b) => {
    const [r1, c1] = a[0].split("_").map(Number);
    const [r2, c2] = b[0].split("_").map(Number);

    if (r1 !== r2) return r1 - r2;
    return c1 - c2;
  });

  entries.forEach(([key, seatValue]) => {
    const [r, c] = key.split("_").map(Number);
    const seatLabel = `${String.fromCharCode(65 + r)}${c + 1}`;

    const displayName = seatDisplayName(seatValue);
    const username = seatUsername(seatValue);

    if (!displayName || displayName === "Empty") return;

    const tr = document.createElement("tr");

    tr.innerHTML = `
      <td style="padding: 0.75rem;">
        <strong style="color: var(--accent-primary);">${seatLabel}</strong>
      </td>

      <td style="padding: 0.75rem;" data-username="${username}">
        ${displayName}
      </td>

      <td style="padding: 0.75rem;" class="accuracy-cell">
        <span style="color: var(--text-secondary); opacity: 0.5;">—</span>
      </td>

      <td style="padding: 0.75rem;">
        <span class="tag tag-present">Present</span>
      </td>

      <td style="padding: 0.75rem; text-align: right;">
        <button class="btn btn-outline" style="padding: 0.25rem 0.5rem; font-size: 0.7rem;" onclick="toggleStatus(this)">
          Mark Absent
        </button>
      </td>
    `;

    body.appendChild(tr);
  });

  loadHistory();
}

/* =========================================================
   ATTENDANCE STATUS CONTROLS
   ========================================================= */

function toggleStatus(btn) {
  const tr = btn.closest("tr");
  const tag = tr.querySelector(".tag");

  if (!tag) return;

  if (tag.classList.contains("tag-absent")) {
    tag.textContent = "Present";
    tag.className = "tag tag-present";
    btn.textContent = "Mark Absent";
  } else {
    tag.textContent = "Absent";
    tag.className = "tag tag-absent";
    btn.textContent = "Mark Present";
  }
}

function markAll(status) {
  const rows = $("attendanceBody").querySelectorAll("tr");

  rows.forEach(tr => {
    const tag = tr.querySelector(".tag");
    const btn = tr.querySelector("button");

    if (!tag || !btn) return;

    if (status === "Present") {
      tag.textContent = "Present";
      tag.className = "tag tag-present";
      btn.textContent = "Mark Absent";
    } else {
      tag.textContent = "Absent";
      tag.className = "tag tag-absent";
      btn.textContent = "Mark Present";
    }
  });
}

/* =========================================================
   SAVE ATTENDANCE
   ========================================================= */

async function saveAttendance() {
  const raw = localStorage.getItem(ACTIVE_KEY);
  if (!raw) return;

  const assignment = JSON.parse(raw);
  const rows = $("attendanceBody").querySelectorAll("tr");

  if (rows.length === 0 || rows[0].innerText.includes("No students")) {
    alert("No attendance data to save.");
    return;
  }

  const records = [];

  rows.forEach(tr => {
    const cells = tr.querySelectorAll("td");

    if (cells.length < 4) return;

    const seat = cells[0].textContent.trim();
    const name = cells[1].textContent.trim();
    const username = cells[1].dataset.username || "";

    // columns:
    // 0 = seat
    // 1 = student
    // 2 = accuracy
    // 3 = status
    const tag = cells[3].querySelector(".tag");

    if (!tag) return;

    const status = tag.classList.contains("tag-present") ? "Present" : "Absent";

    records.push({
      seat,
      name,
      username,
      status
    });
  });

  if (records.length === 0) {
    alert("No valid attendance records found.");
    return;
  }

  const btn = $("saveAttendanceBtn");
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

  try {
    const res = await fetch(`${API}/attendance/save`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        class_id: Number(assignment.class_id),
        subject_id: Number(assignment.subject_id),
        teacher_username: assignment.teacher_username || getCurrentUser()?.username || "teacher",
        date: new Date().toISOString().split("T")[0],
        records
      })
    });

    const data = await res.json();

    if (!res.ok || !data.success) {
      throw new Error(data.error || "Failed to save attendance.");
    }

    alert("Attendance saved successfully.");
    await loadHistory();

  } catch (err) {
    console.error("Save error:", err);
    alert("Connection error while saving attendance: " + err.message);

  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-save"></i> Save Record';
  }
}

/* =========================================================
   HISTORY
   ========================================================= */

async function loadHistory() {
  const raw = localStorage.getItem(ACTIVE_KEY);
  if (!raw) return;

  const assignment = JSON.parse(raw);
  const historyList = $("historyList");

  if (!historyList) return;

  try {
    const res = await fetch(`${API}/attendance/records`);
    const allRecords = await res.json();

    const classRecords = allRecords
      .filter(r => sameId(r.class_id, assignment.class_id))
      .reverse();

    if (classRecords.length === 0) {
      historyList.innerHTML = `
        <div style="padding: 1rem; text-align: center; color: var(--text-secondary); font-size: 0.8rem;">
          No past sessions found.
        </div>
      `;
      return;
    }

    historyList.innerHTML = classRecords.map(rec => {
      const presentCount = (rec.records || []).filter(s => s.status === "Present").length;
      const totalCount = (rec.records || []).length;

      return `
        <div style="padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.8rem;">
          <div class="flex justify-between">
            <strong style="color: var(--accent-primary);">${rec.date}</strong>
            <span style="color: var(--text-secondary);">
              ${presentCount} / ${totalCount} Present
            </span>
          </div>

          <div style="font-size: 0.7rem; color: var(--text-secondary); margin-top: 0.25rem;">
            Saved at ${rec.timestamp || "N/A"}
          </div>
        </div>
      `;
    }).join("");

  } catch (err) {
    console.error("History error:", err);

    historyList.innerHTML = `
      <div style="color: #f87171; padding: 1rem;">
        Failed to load history.
      </div>
    `;
  }
}

/* =========================================================
   AI VIDEO ATTENDANCE
   ========================================================= */

function applyAiAttendanceResults(aiResults) {
  const statusBody = $("attendanceBody");

  if (!Array.isArray(aiResults)) {
    throw new Error("AI response did not include attendance results.");
  }

  const rows = statusBody.querySelectorAll("tr");

  let totalConfidence = 0;
  let matchedStudents = 0;

  rows.forEach(tr => {
    const cells = tr.querySelectorAll("td");

    if (cells.length < 4) return;

    const studentName = normalize(cells[1].textContent);
    const studentUsername = normalize(cells[1].dataset.username);

    const accuracyCell = tr.querySelector(".accuracy-cell");
    const statusTag = cells[3].querySelector(".tag");
    const actionBtn = tr.querySelector("button");

    if (!studentName || !accuracyCell || !statusTag) return;

    const aiRecord = aiResults.find(r =>
      normalize(r.name) === studentName ||
      normalize(r.name) === studentUsername ||
      normalize(r.username) === studentUsername ||
      normalize(r.username) === studentName
    );

    const isPresent = aiRecord && (
      aiRecord.present === "YES" ||
      aiRecord.status === "Present"
    );

    if (isPresent) {
      const confidence = parseFloat(
        aiRecord.accuracy ||
        aiRecord.avg_confidence ||
        aiRecord.confidence ||
        90
      );

      accuracyCell.innerHTML = `
        <span class="status status-ok" style="font-size: 0.7rem;">
          ${Math.round(confidence)}% Match
        </span>
      `;

      statusTag.textContent = "Present";
      statusTag.className = "tag tag-present";

      if (actionBtn) {
        actionBtn.textContent = "Mark Absent";
      }

      totalConfidence += confidence;
      matchedStudents++;

    } else {
      accuracyCell.innerHTML = `
        <span class="status status-inactive" style="font-size: 0.7rem; opacity: 0.6;">
          No Match
        </span>
      `;

      statusTag.textContent = "Absent";
      statusTag.className = "tag tag-absent";

      if (actionBtn) {
        actionBtn.textContent = "Mark Present";
      }
    }
  });

  const accBox = $("accuracyBox");

  if (matchedStudents > 0) {
    const avgConfidence = totalConfidence / matchedStudents;

    accBox.innerHTML = `
      <div class="accuracy-card">
        <div>
          <div class="accuracy-label">AI Model Performance</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">
            Processed from uploaded video
          </div>
        </div>
        <div class="accuracy-value">${avgConfidence.toFixed(1)}%</div>
      </div>
    `;
  } else {
    accBox.innerHTML = `
      <div class="tag tag-absent">
        No seated students matched by AI
      </div>
    `;
  }
}

async function runVideoAttendance() {
  const res = await fetch(`${API}/attendance/latest-ai-result`);
  const aiResults = await res.json();

  if (!res.ok) {
    throw new Error(aiResults.error || "Upload and process a video first.");
  }

  applyAiAttendanceResults(aiResults);
}

async function uploadLargeVideoViaGcs(file) {
  const ticketRes = await fetch(`${API}/attendance/gcs-upload-url`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      filename: file.name,
      content_type: file.type || "application/octet-stream"
    })
  });

  const ticket = await readResponse(ticketRes);

  if (!ticketRes.ok || !ticket.success) {
    const detail = ticket.details ? ` ${ticket.details}` : "";
    throw new Error(`${ticket.error || "Could not prepare large video upload."}${detail}`);
  }

  const uploadRes = await fetch(ticket.upload_url, {
    method: "PUT",
    headers: {
      "Content-Type": file.type || "application/octet-stream"
    },
    body: file
  });

  if (!uploadRes.ok) {
    const uploadText = await uploadRes.text();
    throw new Error(
      `Cloud Storage upload failed (${uploadRes.status}). ` +
      uploadText.replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim().slice(0, 300)
    );
  }

  const processRes = await fetch(`${API}/attendance/process-gcs-video`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      object_name: ticket.object_name
    })
  });

  const data = await readResponse(processRes);

  if (!processRes.ok || !data.success) {
    const detail = data.details ? ` ${data.details}` : "";
    throw new Error(`${data.error || "AI processing failed."}${detail}`);
  }

  return data;
}

async function uploadSmallVideoDirectly(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API}/attendance/upload`, {
    method: "POST",
    body: formData
  });

  const data = await readResponse(res);

  if (!res.ok || !data.success) {
    const detail = data.details ? ` ${data.details}` : "";
    throw new Error(`${data.error || "Upload failed."}${detail}`);
  }

  return data;
}

/* =========================================================
   SEAT MODAL
   ========================================================= */

function openSeatModal(label, currentUsername, onSave) {
  const modal = $("seatModal");
  const labelSpan = $("modalSeatLabel");
  const select = $("modalStudentSelect");

  labelSpan.textContent = label;

  select.innerHTML = '<option value="">-- Empty Seat --</option>';

  allStudents.forEach(student => {
    const opt = document.createElement("option");
    opt.value = student.username;
    opt.textContent = `${student.name || student.username} (${student.username})`;
    select.appendChild(opt);
  });

  select.value = currentUsername || "";

  currentSaveCallback = async () => {
    const username = select.value;

    if (!username) {
      await onSave({
        name: "",
        username: ""
      });

      return;
    }

    const student = allStudents.find(s => s.username === username);

    if (!student) {
      alert("Selected student not found.");
      return;
    }

    await onSave({
      name: student.name || student.username,
      username: student.username
    });
  };

  modal.style.display = "flex";
  select.focus();
}

function closeSeatModal() {
  $("seatModal").style.display = "none";
  currentSaveCallback = null;
}

function wireSeatModal() {
  const saveBtn = $("modalSaveBtn");
  const cancelBtn = $("modalCancelBtn");

  if (!saveBtn || saveBtn.dataset.wired) return;

  saveBtn.addEventListener("click", async () => {
    if (currentSaveCallback) {
      await currentSaveCallback();
    }

    closeSeatModal();
  });

  cancelBtn.addEventListener("click", closeSeatModal);

  saveBtn.dataset.wired = "true";
}

async function saveSeat(classId, row, col, name, username) {
  const res = await fetch(`${API}/classes/seat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      class_id: Number(classId),
      row: Number(row),
      col: Number(col),
      name,
      username
    })
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new Error(data.error || "Failed to save seat.");
  }

  return data;
}

/* =========================================================
   SESSION UI
   ========================================================= */

function updateSessionUI() {
  const badge = $("stateBadge");
  const startBtn = $("startBtn");
  const pauseBtn = $("pauseBtn");
  const endBtn = $("endBtn");

  badge.className = "status";

  startBtn.disabled = false;
  pauseBtn.disabled = true;
  endBtn.disabled = true;

  startBtn.innerHTML = '<i class="fa-solid fa-play"></i> Start';

  if (sessionState === "IDLE") {
    badge.textContent = "IDLE";
    badge.classList.add("status-inactive");

  } else if (sessionState === "RUNNING") {
    badge.textContent = "LIVE";
    badge.classList.add("status-active");

    startBtn.disabled = true;
    pauseBtn.disabled = false;
    endBtn.disabled = false;

  } else if (sessionState === "PAUSED") {
    badge.textContent = "PAUSED";
    badge.classList.add("status-warning");

    startBtn.disabled = false;
    startBtn.innerHTML = '<i class="fa-solid fa-play"></i> Resume';

    pauseBtn.disabled = true;
    endBtn.disabled = false;

  } else if (sessionState === "ENDED") {
    badge.textContent = "ENDED";
    badge.classList.add("status-inactive");

    startBtn.disabled = true;
    pauseBtn.disabled = true;
    endBtn.disabled = true;
  }
}

function wireSessionUI() {
  $("startBtn").addEventListener("click", () => {
    sessionState = "RUNNING";
    updateSessionUI();
  });

  $("pauseBtn").addEventListener("click", () => {
    sessionState = "PAUSED";
    updateSessionUI();
  });

  $("endBtn").addEventListener("click", () => {
    if (confirm("End class session?")) {
      sessionState = "ENDED";
      updateSessionUI();
    }
  });
}

/* =========================================================
   CAMERA LOGIC
   ========================================================= */

function setStatus(text, ok = null) {
  const s = $("camStatus");

  if (!s) return;

  s.textContent = text;
  s.classList.remove("status-ok", "status-bad");

  if (ok === true) s.classList.add("status-ok");
  if (ok === false) s.classList.add("status-bad");
}

function showImg(show) {
  $("camImg").style.display = show ? "block" : "none";
  $("camPlaceholder").style.display = show ? "none" : "flex";
}

function stopSnapshotLoop() {
  if (camTimer) clearInterval(camTimer);
  camTimer = null;
}

function stopReconnectLoop() {
  if (reconnectTimer) clearInterval(reconnectTimer);
  reconnectTimer = null;
}

function disconnectCamera() {
  stopSnapshotLoop();
  stopReconnectLoop();

  const img = $("camImg");

  img.onload = null;
  img.onerror = null;
  img.src = "";

  camConnected = false;

  showImg(false);
  setStatus("Status: disconnected", null);

  $("camHint").textContent = "";
  $("disconnectBtn").style.display = "none";
  $("connectBtn").style.display = "inline-flex";
}

function normalizeUrl(url, mode) {
  try {
    const u = new URL(url);

    if (u.pathname === "/" || u.pathname === "") {
      if (mode === "snapshot") {
        u.pathname = "/capture";
      }
    }

    return u.toString();

  } catch {
    return url;
  }
}

function startSnapshotLoop(url, fps) {
  stopSnapshotLoop();

  const img = $("camImg");
  const intervalMs = Math.max(100, Math.floor(1000 / fps));

  camTimer = setInterval(() => {
    const bust = `t=${Date.now()}`;
    const sep = url.includes("?") ? "&" : "?";
    img.src = url + sep + bust;
  }, intervalMs);
}

function connectMJPEG(url) {
  const img = $("camImg");

  showImg(true);
  setStatus("Status: connecting (MJPEG)…", null);

  img.onload = () => {
    camConnected = true;
    lastFrameAt = Date.now();

    setStatus("Status: connected ✅ (MJPEG)", true);

    $("disconnectBtn").style.display = "inline-flex";
    $("connectBtn").style.display = "none";
  };

  img.onerror = () => {
    camConnected = false;
    showImg(false);
    setStatus("Status: failed (MJPEG). Check URL / ESP32 online.", false);
  };

  img.src = url;
}

function connectSnapshot(url, fps) {
  const img = $("camImg");

  showImg(true);
  setStatus(`Status: connecting (Snapshot @ ${fps} fps)…`, null);

  img.onload = () => {
    camConnected = true;
    lastFrameAt = Date.now();

    setStatus(`Status: connected ✅ (Snapshot @ ${fps} fps)`, true);

    $("disconnectBtn").style.display = "inline-flex";
    $("connectBtn").style.display = "none";
  };

  img.onerror = () => {
    camConnected = false;
    showImg(false);
    setStatus("Status: failed (Snapshot). Check URL / ESP32 online.", false);
    stopSnapshotLoop();
  };

  const bust = `t=${Date.now()}`;
  const sep = url.includes("?") ? "&" : "?";

  img.src = url + sep + bust;
  startSnapshotLoop(url, fps);
}

function startAutoReconnect() {
  stopReconnectLoop();

  const enabled = $("autoReconnect")?.checked;

  if (!enabled) return;

  reconnectTimer = setInterval(() => {
    const staleMs = 6000;
    const now = Date.now();

    const isStale = camConnected && (now - lastFrameAt > staleMs);

    if (isStale) {
      setStatus("Status: stream stale… reconnecting", null);
      doConnect(true);
    }
  }, 2000);
}

function doConnect(isAuto = false) {
  const rawUrl = $("camUrl").value.trim();
  const mode = $("camMode").value;
  const fps = parseInt($("camFps").value, 10) || 5;

  if (!rawUrl) {
    if (!isAuto) {
      setStatus("Status: enter a camera URL first", false);
    }

    return;
  }

  const url = normalizeUrl(rawUrl, mode);

  localStorage.setItem(CAM_URL_KEY, rawUrl);
  localStorage.setItem(CAM_MODE_KEY, mode);
  localStorage.setItem(CAM_FPS_KEY, String(fps));

  disconnectCamera();

  if (mode === "mjpeg") {
    $("camHint").textContent = "Hint: ESP32 often uses /stream, sometimes port :81.";
    connectMJPEG(url);
  } else {
    $("camHint").textContent = "Hint: Snapshot often uses /capture.";
    connectSnapshot(url, fps);
  }

  startAutoReconnect();
}

function restoreCamSettings() {
  $("camUrl").value = localStorage.getItem(CAM_URL_KEY) || "";
  $("camMode").value = localStorage.getItem(CAM_MODE_KEY) || "mjpeg";
  $("camFps").value = localStorage.getItem(CAM_FPS_KEY) || "5";
}

function wireCameraUI() {
  restoreCamSettings();

  $("connectBtn").addEventListener("click", () => doConnect(false));
  $("disconnectBtn").addEventListener("click", disconnectCamera);

  $("camMode").addEventListener("change", () => {
    if ($("camUrl").value.trim()) {
      doConnect(false);
    }
  });

  $("camFps").addEventListener("change", () => {
    if ($("camMode").value === "snapshot" && $("camUrl").value.trim()) {
      doConnect(false);
    }
  });

  $("runAiBtn").addEventListener("click", () => $("videoUpload").click());
  $("uploadTriggerBtn").addEventListener("click", () => $("videoUpload").click());

  $("videoUpload").addEventListener("change", async (e) => {
    const file = e.target.files[0];

    if (!file) return;

    const btn = $("uploadTriggerBtn");
    const aiBtn = $("runAiBtn");
    const originalHtml = btn.innerHTML;
    const originalAiHtml = aiBtn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    aiBtn.disabled = true;
    aiBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processing Video...';

    try {
      const data = file.size > MAX_VIDEO_UPLOAD_BYTES
        ? await uploadLargeVideoViaGcs(file)
        : await uploadSmallVideoDirectly(file);

      applyAiAttendanceResults(data.results || []);
      alert("Video processed successfully: " + data.filename);

    } catch (err) {
      console.error("Upload error:", err);
      alert("Error uploading video: " + err.message);

    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
      aiBtn.disabled = false;
      aiBtn.innerHTML = originalAiHtml;
      e.target.value = "";
    }
  });
}

/* =========================================================
   INIT
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
  loadSession();
  wireSeatModal();
  wireSessionUI();
  wireCameraUI();

  $("saveAttendanceBtn").addEventListener("click", saveAttendance);
});
