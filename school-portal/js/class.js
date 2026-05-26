// class.js
const CAM_URL_KEY = "esp32_cam_url";
const CAM_MODE_KEY = "esp32_cam_mode";
const CAM_FPS_KEY = "esp32_cam_fps";
const ACTIVE_KEY = "active_assignment";

const API = "/api";
const MAX_VIDEO_UPLOAD_BYTES = 30 * 1024 * 1024;
const STRICT_AI_ATTENDANCE = true;

let camTimer = null;
let camConnected = false;
let lastFrameAt = 0;
let reconnectTimer = null;
let sessionState = "IDLE";

let allStudents = [];
let currentSaveCallback = null;
let currentSeatRows = 0;
let currentSeatCols = 0;
let currentSeating = {};

function $(id) {
  return document.getElementById(id);
}

function normalize(v) {
  return String(v || "").trim().toLowerCase();
}

function sameId(a, b) {
  return String(a) === String(b);
}

function normalizePersonKey(value) {
  return normalize(value).replace(/[^a-z0-9]/g, "");
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
  currentSeatRows = rows;
  currentSeatCols = cols;
  currentSeating = seating || {};

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
      seat.dataset.seatLabel = seatLabel;

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
  const returnedNames = aiResults
    .map(r => String(r.name || r.username || "").trim())
    .filter(Boolean);
  const presentNames = aiResults
    .filter(r => r.present === "YES" || r.status === "Present")
    .map(r => String(r.name || r.username || "").trim())
    .filter(Boolean);

  let totalConfidence = 0;
  let matchedStudents = 0;
  let unmatchedStudents = 0;
  let reviewStudents = 0;

  rows.forEach(tr => {
    const cells = tr.querySelectorAll("td");

    if (cells.length < 4) return;

    const studentName = normalize(cells[1].textContent);
    const studentUsername = normalize(cells[1].dataset.username);

    const accuracyCell = tr.querySelector(".accuracy-cell");
    const statusTag = cells[3].querySelector(".tag");
    const actionBtn = tr.querySelector("button");

    if (!studentName || !accuracyCell || !statusTag) return;

    reviewStudents++;

    const studentKey = normalizePersonKey(cells[1].textContent);
    const usernameKey = normalizePersonKey(cells[1].dataset.username);

    const aiRecord = aiResults.find(r =>
      normalize(r.name) === studentName ||
      normalize(r.name) === studentUsername ||
      normalize(r.username) === studentUsername ||
      normalize(r.username) === studentName ||
      normalizePersonKey(r.name) === studentKey ||
      normalizePersonKey(r.name) === usernameKey ||
      normalizePersonKey(r.username) === usernameKey ||
      normalizePersonKey(r.username) === studentKey
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
          ${confidence.toFixed(1)}% Match
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
      unmatchedStudents++;

      const noMatchText = aiRecord ? "AI Says Absent" : "No AI Result";

      accuracyCell.innerHTML = `
        <span class="status status-danger" style="font-size: 0.7rem;">
          ${noMatchText}
        </span>
      `;

      statusTag.textContent = STRICT_AI_ATTENDANCE ? "Absent" : "Present";
      statusTag.className = STRICT_AI_ATTENDANCE ? "tag tag-absent" : "tag tag-present";

      if (actionBtn) {
        actionBtn.textContent = STRICT_AI_ATTENDANCE ? "Mark Present" : "Mark Absent";
      }
    }
  });

  const accBox = $("accuracyBox");

  if (matchedStudents > 0) {
    const avgConfidence = totalConfidence / matchedStudents;

    accBox.innerHTML = `
      <div class="accuracy-card">
        <div>
          <div class="accuracy-label">AI Attendance Review</div>
          <div style="font-size: 0.8rem; color: var(--text-secondary);">
            ${matchedStudents} face matches, ${unmatchedStudents} no match
          </div>
          <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.25rem;">
            AI present: ${escapeHtml(presentNames.join(", "))}
          </div>
        </div>
        <div class="accuracy-value">${avgConfidence.toFixed(1)}%</div>
      </div>
    `;
  } else {
    const presentText = presentNames.length
      ? `AI present: ${presentNames.join(", ")}`
      : "AI present: none";
    const checkedText = returnedNames.length
      ? `AI checked: ${returnedNames.slice(0, 6).join(", ")}${returnedNames.length > 6 ? "..." : ""}`
      : "AI returned no student rows";

    accBox.innerHTML = `
      <div class="tag tag-absent">
        0/${reviewStudents} seated students matched by AI
      </div>
      <div style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.35rem;">
        ${escapeHtml(presentText)}
      </div>
      <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.25rem;">
        ${escapeHtml(checkedText)}
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

function currentSeatedStudentNames() {
  return Array.from($("attendanceBody").querySelectorAll("tr"))
    .map(tr => {
      const cells = tr.querySelectorAll("td");
      return cells.length >= 2 ? cells[1].textContent.trim() : "";
    })
    .filter(Boolean);
}

function currentAssignmentMetadata() {
  let assignment = {};

  try {
    assignment = JSON.parse(localStorage.getItem(ACTIVE_KEY) || "{}");
  } catch {
    assignment = {};
  }

  return {
    teacher_username: assignment.teacher_username || getCurrentUser()?.username || "",
    class_id: assignment.class_id || "",
    subject_id: assignment.subject_id || "",
    class_name: assignment.class_name || "",
    subject_name: assignment.subject_name || ""
  };
}

function appendAssignmentMetadata(formData) {
  const metadata = currentAssignmentMetadata();

  Object.entries(metadata).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      formData.append(key, value);
    }
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setVideoProcessingProgress(message) {
  const text = String(message || "Processing video...");
  const shortText = text.length > 64 ? `${text.slice(0, 61)}...` : text;
  const aiBtn = $("runAiBtn");
  const hint = $("camHint");

  if (aiBtn) {
    aiBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${escapeHtml(shortText)}`;
  }

  if (hint) {
    hint.textContent = text;
  }
}

async function processGcsVideoWithProgress(objectName) {
  let res;

  try {
    res = await fetch(`${API}/attendance/process-gcs-video-stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        object_name: objectName,
        expected_names: currentSeatedStudentNames(),
        ...currentAssignmentMetadata()
      })
    });
  } catch (err) {
    throw new Error(`Could not start AI video processing. ${err.message}`);
  }

  if (!res.ok) {
    const data = await readResponse(res);
    const detail = data.details ? ` ${data.details}` : "";
    throw new Error(`${data.error || "Could not start AI video processing."}${detail}`);
  }

  if (!res.body) {
    throw new Error("This browser could not read the AI processing stream.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  const handleLine = (line) => {
    const clean = line.trim();

    if (!clean) return;

    let event;

    try {
      event = JSON.parse(clean);
    } catch {
      return;
    }

    if (event.type === "status") {
      setVideoProcessingProgress(event.message || "Processing video...");
    } else if (event.type === "error") {
      const detail = event.details ? ` ${event.details}` : "";
      throw new Error(`${event.error || "AI processing failed."}${detail}`);
    } else if (event.type === "complete") {
      finalData = event;
    }
  };

  while (true) {
    const { value, done } = await reader.read();

    if (value) {
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      lines.forEach(handleLine);
    }

    if (done) break;
  }

  if (buffer.trim()) {
    handleLine(buffer);
  }

  if (!finalData || !finalData.success) {
    throw new Error("AI processing finished without returning attendance results.");
  }

  return finalData;
}

async function uploadLargeVideoViaGcs(file) {
  let ticketRes;

  try {
    ticketRes = await fetch(`${API}/attendance/gcs-upload-url`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        filename: file.name,
        content_type: file.type || "application/octet-stream"
      })
    });
  } catch (err) {
    throw new Error(`Could not contact upload service. ${err.message}`);
  }

  const ticket = await readResponse(ticketRes);

  if (!ticketRes.ok || !ticket.success) {
    const detail = ticket.details ? ` ${ticket.details}` : "";
    throw new Error(`${ticket.error || "Could not prepare large video upload."}${detail}`);
  }

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

  return processGcsVideoWithProgress(ticket.object_name);
}

async function uploadSmallVideoDirectly(file) {
  const formData = new FormData();
  formData.append("file", file);
  appendAssignmentMetadata(formData);

  let res;

  try {
    res = await fetch(`${API}/attendance/upload`, {
      method: "POST",
      body: formData
    });
  } catch (err) {
    throw new Error(`Could not upload video to the server. ${err.message}`);
  }

  const data = await readResponse(res);

  if (!res.ok || !data.success) {
    const detail = data.details ? ` ${data.details}` : "";
    throw new Error(`${data.error || "Upload failed."}${detail}`);
  }

  return data;
}

function renderPhoneDetectionResult(data) {
  const target = $("phoneDetectionResult");

  if (!target) return;

  if (!data || !data.success) {
    target.innerHTML = `<span class="tag tag-absent">Phone detection failed</span>`;
    return;
  }

  clearPhoneSeatHighlights();

  const confidence = Number(data.best_confidence || 0);
  const confidenceText = confidence > 0 ? `${(confidence * 100).toFixed(1)}%` : "0%";
  const statusClass = data.phone_detected ? "tag tag-absent" : "tag tag-present";
  const statusText = data.phone_detected ? "Phone detected" : "No phone detected";
  const seatLabels = phoneDetectionSeatLabels(data);
  const detectionText = data.raw_total_phones && data.raw_total_phones !== data.total_phones
    ? `${data.total_phones || 0}/${data.raw_total_phones} stable`
    : `${data.total_phones || 0}`;
  const classesSeen = Array.isArray(data.classes_seen) ? data.classes_seen.slice(0, 4) : [];
  const classesText = classesSeen
    .map(item => `${item.class} ${(Number(item.best_confidence || 0) * 100).toFixed(0)}%`)
    .join(", ");
  const noLabelsText = !classesText && !data.phone_detected
    ? "Local model returned no phone labels"
    : "";
  const shapeText = !classesText && Array.isArray(data.response_shapes) && data.response_shapes.length
    ? `Response shape: ${JSON.stringify(data.response_shapes[0]).slice(0, 180)}`
    : "";
  const debugText = !classesText && Array.isArray(data.debug_samples) && data.debug_samples.length
    ? `Debug sample: ${JSON.stringify(data.debug_samples[0]).slice(0, 420)}`
    : "";

  highlightPhoneSeats(seatLabels);

  target.innerHTML = `
    <span class="${statusClass}">${statusText}</span>
    <span style="margin-left: 0.5rem;">
      seats: ${seatLabels.length},
      detections: ${detectionText},
      frames: ${data.phone_frames || 0}/${data.frames_checked || 0},
      best ${confidenceText}${data.tiles_enabled ? `, tiles ${escapeHtml(data.tile_grid || "on")}` : ""}
    </span>
    ${seatLabels.length ? `
      <span style="margin-left: 0.5rem;">
        seats: ${escapeHtml(seatLabels.join(", "))}
      </span>
    ` : ""}
    ${classesText ? `
      <div style="margin-top: 0.25rem;">
        Model saw: ${escapeHtml(classesText)}
      </div>
    ` : ""}
    ${noLabelsText ? `
      <div style="margin-top: 0.25rem;">
        ${escapeHtml(noLabelsText)}
      </div>
    ` : ""}
    ${shapeText ? `
      <div style="margin-top: 0.25rem; font-size: 0.75rem;">
        ${escapeHtml(shapeText)}
      </div>
    ` : ""}
    ${debugText ? `
      <div style="margin-top: 0.25rem; font-size: 0.75rem;">
        ${escapeHtml(debugText)}
      </div>
    ` : ""}
  `;
}

function detectionCenter(value, size) {
  const number = Number(value);

  if (!Number.isFinite(number)) return null;

  return Math.max(0, Math.min(1, number <= 1 ? number : number / Math.max(1, size)));
}

function phoneDetectionSeatLabels(data) {
  if (Array.isArray(data?.phone_seats) && data.phone_seats.length) {
    return data.phone_seats
      .slice(0, 1)
      .map(item => {
        const seatLabel = String(item.seat || "").trim();

        if (!seatLabel) return "";

        const match = seatLabel.match(/^([A-Z])(\d+)$/);
        let displayName = "Empty";

        if (match) {
          const row = match[1].charCodeAt(0) - 65;
          const col = Number(match[2]) - 1;
          displayName = seatDisplayName(currentSeating[`${row}_${col}`]);
        }

        return `${seatLabel}${displayName !== "Empty" ? ` ${displayName}` : ""}`;
      })
      .filter(Boolean);
  }

  if (!currentSeatRows || !currentSeatCols || !Array.isArray(data?.frames)) {
    return [];
  }

  const seats = new Map();

  data.frames.forEach(frame => {
    const frameWidth = Number(frame.frame_width || 0);
    const frameHeight = Number(frame.frame_height || 0);
    const frameNumber = Number(frame.frame || 0);

    (frame.detections || []).forEach(detection => {
      const centerX = detectionCenter(detection.x, frameWidth);
      const centerY = detectionCenter(detection.y, frameHeight);

      if (centerX === null || centerY === null) return;

      const col = Math.max(0, Math.min(currentSeatCols - 1, Math.floor(centerX * currentSeatCols)));
      const row = Math.max(0, Math.min(currentSeatRows - 1, Math.floor(centerY * currentSeatRows)));
      const seatLabel = `${String.fromCharCode(65 + row)}${col + 1}`;
      const seatKey = `${row}_${col}`;
      const seatValue = currentSeating[seatKey];
      const item = seats.get(seatLabel) || {
        label: seatLabel,
        display: `${seatLabel}${seatDisplayName(seatValue) !== "Empty" ? ` ${seatDisplayName(seatValue)}` : ""}`,
        frames: new Set(),
        best: 0
      };

      item.frames.add(frameNumber);
      item.best = Math.max(item.best, Number(detection.confidence || 0));
      seats.set(seatLabel, item);
    });
  });

  return Array.from(seats.values())
    .filter(item => item.frames.size >= 2 || item.best >= 0.85)
    .sort((a, b) => b.frames.size - a.frames.size || b.best - a.best)
    .slice(0, 4)
    .map(item => item.display);
}

function clearPhoneSeatHighlights() {
  document.querySelectorAll(".seat.phone-detected").forEach(seat => {
    seat.classList.remove("phone-detected");
    seat.style.boxShadow = "";
    seat.style.borderColor = "";
  });
}

function highlightPhoneSeats(labels) {
  clearPhoneSeatHighlights();

  labels.forEach(label => {
    const seatLabel = label.split(" ")[0];
    const seat = document.querySelector(`.seat[data-seat-label="${CSS.escape(seatLabel)}"]`);

    if (!seat) return;

    seat.classList.add("phone-detected");
    seat.style.borderColor = "#f87171";
    seat.style.boxShadow = "0 0 0 2px rgba(248, 113, 113, 0.35)";
  });
}

async function uploadPhoneDetectionVideo(file) {
  if (file.size > MAX_VIDEO_UPLOAD_BYTES) {
    throw new Error("Phone detection uploads are limited to 30 MB. Use a shorter clip.");
  }

  const formData = new FormData();
  formData.append("file", file);

  let res;

  try {
    res = await fetch(`${API}/phone-detection/upload`, {
      method: "POST",
      body: formData
    });
  } catch (err) {
    throw new Error(`Could not upload video for phone detection. ${err.message}`);
  }

  const data = await readResponse(res);

  if (!res.ok || !data.success) {
    const detail = data.details ? ` ${data.details}` : "";
    throw new Error(`${data.error || "Phone detection failed."}${detail}`);
  }

  return data;
}

function formatPhoneDetectionErrorMessage(message) {
  const normalized = String(message || "Phone detection failed.");

  if (/HTTP 502|502/.test(normalized)) {
    return "Phone detection is temporarily unavailable. Please wait a few minutes and try again.";
  }

  if (/timed out|network|fetch|Failed to fetch|gateway|service unavailable|503/i.test(normalized)) {
    return "Phone detection is temporarily unavailable. Please retry in a few minutes.";
  }

  return normalized;
}

function renderSleepDetectionResult(data) {
  const target = $("sleepDetectionResult") || $("phoneDetectionResult");

  if (!target) return;

  if (!data || !data.success) {
    target.innerHTML = `<span class="tag tag-absent">Sleep detection failed</span>`;
    return;
  }

  clearSleepSeatHighlights();

  const confidence = Number(data.best_confidence || 0);
  const confidenceText = confidence > 0 ? `${(confidence * 100).toFixed(1)}%` : "0%";
  const statusClass = data.sleep_detected ? "tag tag-absent" : "tag tag-present";
  const statusText = data.sleep_detected ? "Sleeping detected" : "No sleep detected";
  const seatLabels = sleepDetectionSeatLabels(data);
  const detectionText = data.raw_total_sleepers && data.raw_total_sleepers !== data.total_sleepers
    ? `${data.total_sleepers || 0}/${data.raw_total_sleepers} stable`
    : `${data.total_sleepers || 0}`;
  const classesSeen = Array.isArray(data.classes_seen) ? data.classes_seen.slice(0, 4) : [];
  const classesText = classesSeen
    .map(item => `${item.class} ${(Number(item.best_confidence || 0) * 100).toFixed(0)}%`)
    .join(", ");
  const noLabelsText = !classesText && !data.sleep_detected
    ? "Local model returned no sleep labels"
    : "";

  highlightSleepSeats(seatLabels);

  target.innerHTML = `
    <span class="${statusClass}">${statusText}</span>
    <span style="margin-left: 0.5rem;">
      seats: ${seatLabels.length},
      detections: ${detectionText},
      frames: ${data.sleep_frames || 0}/${data.frames_checked || 0},
      best ${confidenceText}${data.tiles_enabled ? `, tiles ${escapeHtml(data.tile_grid || "on")}` : ""}
    </span>
    ${seatLabels.length ? `
      <span style="margin-left: 0.5rem;">
        seats: ${escapeHtml(seatLabels.join(", "))}
      </span>
    ` : ""}
    ${classesText ? `
      <div style="margin-top: 0.25rem;">
        Model saw: ${escapeHtml(classesText)}
      </div>
    ` : ""}
    ${noLabelsText ? `
      <div style="margin-top: 0.25rem;">
        ${escapeHtml(noLabelsText)}
      </div>
    ` : ""}
  `;
}

function sleepDetectionSeatLabels(data) {
  if (Array.isArray(data?.sleep_seats) && data.sleep_seats.length) {
    return data.sleep_seats
      .slice(0, 8)
      .map(item => {
        const seatLabel = String(item.seat || "").trim();

        if (!seatLabel) return "";

        const match = seatLabel.match(/^([A-Z])(\d+)$/);
        let displayName = "Empty";

        if (match) {
          const row = match[1].charCodeAt(0) - 65;
          const col = Number(match[2]) - 1;
          displayName = seatDisplayName(currentSeating[`${row}_${col}`]);
        }

        return `${seatLabel}${displayName !== "Empty" ? ` ${displayName}` : ""}`;
      })
      .filter(Boolean);
  }

  if (!currentSeatRows || !currentSeatCols || !Array.isArray(data?.frames)) {
    return [];
  }

  const seats = new Map();

  data.frames.forEach(frame => {
    const frameWidth = Number(frame.frame_width || 0);
    const frameHeight = Number(frame.frame_height || 0);
    const frameNumber = Number(frame.frame || 0);

    (frame.detections || []).forEach(detection => {
      const centerX = detectionCenter(detection.x, frameWidth);
      const centerY = detectionCenter(detection.y, frameHeight);

      if (centerX === null || centerY === null) return;

      const col = Math.max(0, Math.min(currentSeatCols - 1, Math.floor(centerX * currentSeatCols)));
      const row = Math.max(0, Math.min(currentSeatRows - 1, Math.floor(centerY * currentSeatRows)));
      const seatLabel = `${String.fromCharCode(65 + row)}${col + 1}`;
      const seatKey = `${row}_${col}`;
      const seatValue = currentSeating[seatKey];
      const item = seats.get(seatLabel) || {
        label: seatLabel,
        display: `${seatLabel}${seatDisplayName(seatValue) !== "Empty" ? ` ${seatDisplayName(seatValue)}` : ""}`,
        frames: new Set(),
        best: 0
      };

      item.frames.add(frameNumber);
      item.best = Math.max(item.best, Number(detection.confidence || 0));
      seats.set(seatLabel, item);
    });
  });

  return Array.from(seats.values())
    .filter(item => item.frames.size >= 2 || item.best >= 0.90)
    .sort((a, b) => b.frames.size - a.frames.size || b.best - a.best)
    .slice(0, 8)
    .map(item => item.display);
}

function clearSleepSeatHighlights() {
  document.querySelectorAll(".seat.sleep-detected").forEach(seat => {
    seat.classList.remove("sleep-detected");
    seat.style.outline = "";
  });
}

function highlightSleepSeats(labels) {
  clearSleepSeatHighlights();

  labels.forEach(label => {
    const seatLabel = label.split(" ")[0];
    const seat = document.querySelector(`.seat[data-seat-label="${CSS.escape(seatLabel)}"]`);

    if (!seat) return;

    seat.classList.add("sleep-detected");
    seat.style.outline = "2px solid rgba(251, 191, 36, 0.9)";
    seat.style.outlineOffset = "2px";
  });
}

async function uploadSleepDetectionVideo(file) {
  if (file.size > MAX_VIDEO_UPLOAD_BYTES) {
    throw new Error("Sleep detection uploads are limited to 30 MB. Use a shorter clip.");
  }

  const formData = new FormData();
  formData.append("file", file);

  let res;

  try {
    res = await fetch(`${API}/sleep-detection/upload`, {
      method: "POST",
      body: formData
    });
  } catch (err) {
    throw new Error(`Could not upload video for sleep detection. ${err.message}`);
  }

  const data = await readResponse(res);

  if (!res.ok || !data.success) {
    const detail = data.details ? ` ${data.details}` : "";
    throw new Error(`${data.error || "Sleep detection failed."}${detail}`);
  }

  return data;
}

function formatSleepDetectionErrorMessage(message) {
  const normalized = String(message || "Sleep detection failed.");

  if (/model is not ready/i.test(normalized)) {
    return "Sleep detection model is not ready yet. Train models/sleep_yolo11.pt first.";
  }

  if (/HTTP 502|502/.test(normalized)) {
    return "Sleep detection is temporarily unavailable. Please wait a few minutes and try again.";
  }

  if (/timed out|network|fetch|Failed to fetch|gateway|service unavailable|503/i.test(normalized)) {
    return "Sleep detection is temporarily unavailable. Please retry in a few minutes.";
  }

  return normalized;
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
  $("phoneDetectBtn").addEventListener("click", () => $("phoneVideoUpload").click());

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
      const teacherStatus = data.teacher_presence?.status
        ? ` Teacher: ${data.teacher_presence.status}.`
        : "";
      alert(`Video processed successfully: ${data.filename}.${teacherStatus}`);

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

  $("phoneVideoUpload").addEventListener("change", async (e) => {
    const file = e.target.files[0];

    if (!file) return;

    const btn = $("phoneDetectBtn");
    const resultEl = $("phoneDetectionResult");
    const originalHtml = btn.innerHTML;

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Detecting Sleep...';

    if (resultEl) {
      resultEl.textContent = "Detecting sleep...";
    }

    try {
      const data = await uploadSleepDetectionVideo(file);
      renderSleepDetectionResult(data);
    } catch (err) {
      console.error("Sleep detection error:", err);

      if (resultEl) {
        const message = formatSleepDetectionErrorMessage(err.message || "Sleep detection failed.");
        resultEl.innerHTML = `
          <span class="tag tag-absent">Sleep detection failed</span>
          <span style="margin-left: 0.5rem;">${escapeHtml(message.slice(0, 260))}</span>
        `;
      }
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
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
