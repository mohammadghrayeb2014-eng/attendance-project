// ---- Camera controller (Phase 2.2) ----
const CAM_URL_KEY = "esp32_cam_url";
const CAM_MODE_KEY = "esp32_cam_mode";
const CAM_FPS_KEY = "esp32_cam_fps";
const ACTIVE_KEY = "active_assignment"; // Key shared with teacher.js

let camTimer = null;
let camConnected = false;
let lastFrameAt = 0;
let reconnectTimer = null;
let sessionState = "IDLE"; // IDLE, RUNNING, PAUSED, ENDED
let sessionTimer = null;
let sessionStartTime = 0;

function $(id) { return document.getElementById(id); }

const API = "/api"; // Define API base

async function loadSession() {
  const raw = localStorage.getItem(ACTIVE_KEY);
  if (!raw) {
    // Spec requirement: redirect back if missing
    window.location.href = "teacher.html";
    return;
  }

  const assignment = JSON.parse(raw);
  $("sessionTitle").textContent = `${assignment.class_name} — ${assignment.subject_name}`;
  $("sessionMeta").textContent = `Class ID: ${assignment.class_id} • Subject ID: ${assignment.subject_id}`;

  // Fetch latest seating data
  try {
    const res = await fetch(`${API}/classes`);
    const classes = await res.json();
    const currentClass = classes.find(c => c.id === assignment.class_id);
    const seating = currentClass ? (currentClass.seating || {}) : {};

    // Fallback to 4x6 if rows/cols missing from simple assignment object
    const r = assignment.rows || 4;
    const c = assignment.cols || 6;

    renderGrid(r, c, seating, assignment.class_id);
  } catch (e) {
    console.error("Failed to load seating:", e);
    renderGrid(assignment.rows || 4, assignment.cols || 6, {}, assignment.class_id);
  }

  updateSessionUI();
}

function renderGrid(rows, cols, seating, classId) {
  const grid = $("seatGrid");
  grid.innerHTML = "";

  // Grid Template: 1 column for row labels + 'cols' columns for seats
  // Widen first col to fit "Row A" or "A"
  grid.style.gridTemplateColumns = `60px repeat(${cols}, 1fr)`;

  // -- Header Row (empty corner + col numbers) --
  // Corner
  const corner = document.createElement("div");
  grid.appendChild(corner);

  // Column Numbers (1, 2, 3...)
  for (let c = 0; c < cols; c++) {
    const head = document.createElement("div");
    head.className = "grid-label";
    head.textContent = c + 1; // Reverted to simple numbers
    grid.appendChild(head);
  }

  // -- Rows --
  for (let r = 0; r < rows; r++) {
    const rowLabel = document.createElement("div");
    rowLabel.className = "grid-label row-header";
    rowLabel.textContent = String.fromCharCode(65 + r); // A, B, C...
    grid.appendChild(rowLabel);


    // Seats
    for (let c = 0; c < cols; c++) {
      const seat = document.createElement("div");
      seat.className = "seat";
      const key = `${r}_${c}`;
      const studentName = seating[key] || "Empty";
      const seatLabel = `${String.fromCharCode(65 + r)}${c + 1}`; // A1, B1, etc.

      // Highlight if occupied
      if (seating[key]) seat.classList.add("occupied");

      seat.innerHTML = `<strong>${seatLabel}</strong><small>${studentName}</small>`;

      // Click to edit -> Open Modal
      seat.onclick = () => {
        openSeatModal(seatLabel, studentName === "Empty" ? "" : studentName, async (newName) => {
          // Save to backend
          await saveSeat(classId, r, c, newName);

          // Update UI locally
          const finalName = newName.trim() || "Empty";
          seat.querySelector("small").textContent = finalName;
          if (finalName !== "Empty") seat.classList.add("occupied");
          else seat.classList.remove("occupied");
        });
      };

      grid.appendChild(seat);
    }
  }

  // Sync Attendance Recap table
  renderAttendance(seating);
}

function renderAttendance(seating) {
  const body = $("attendanceBody");
  body.innerHTML = "";

  const entries = Object.entries(seating);
  if (entries.length === 0) {
    body.innerHTML = '<tr><td colspan="4" style="padding: 2rem; text-align: center; color: var(--text-secondary);">No students assigned to seats yet.</td></tr>';
    return;
  }

  // Sort by seat label
  entries.sort((a, b) => {
    const [r1, c1] = a[0].split("_").map(Number);
    const [r2, c2] = b[0].split("_").map(Number);
    if (r1 !== r2) return r1 - r2;
    return c1 - c2;
  });

  entries.forEach(([key, name]) => {
    const [r, c] = key.split("_").map(Number);
    const seatLabel = `${String.fromCharCode(65 + r)}${c + 1}`;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td style="padding: 0.75rem;"><strong style="color: var(--accent-primary);">${seatLabel}</strong></td>
      <td style="padding: 0.75rem;">${name}</td>
      <td style="padding: 0.75rem;" class="accuracy-cell"><span style="color: var(--text-secondary); opacity: 0.5;">—</span></td>
      <td style="padding: 0.75rem;"><span class="tag tag-present">Present</span></td>
      <td style="padding: 0.75rem; text-align: right;">
        <button class="btn btn-outline" style="padding: 0.25rem 0.5rem; font-size: 0.7rem;" onclick="toggleStatus(this)">Mark Absent</button>
      </td>
    `;
    body.appendChild(tr);
  });

  if (typeof loadHistory === 'function') loadHistory();
}

function toggleStatus(btn) {
  const tr = btn.closest("tr");
  const tag = tr.querySelector(".tag");
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

async function saveAttendance() {
  const raw = localStorage.getItem(ACTIVE_KEY);
  if (!raw) return;
  const assignment = JSON.parse(raw);

  const statusBody = $("attendanceBody");
  const rows = statusBody.querySelectorAll("tr");
  if (rows.length === 0 || rows[0].innerText.includes("No students")) {
    alert("No attendance data to save.");
    return;
  }

  const records = [];
  rows.forEach(tr => {
    const cells = tr.querySelectorAll("td");
    const seat = cells[0].textContent.trim();
    const name = cells[1].textContent.trim();
    const tag = cells[2].querySelector(".tag");
    const status = tag.classList.contains("tag-present") ? "Present" : "Absent";
    records.push({ seat, name, status });
  });

  const btn = $("saveAttendanceBtn");
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';

  try {
    const res = await fetch(`${API}/attendance/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        class_id: assignment.class_id,
        subject_id: assignment.subject_id,
        teacher_username: assignment.teacher_username || "teacher1",
        date: new Date().toISOString().split('T')[0],
        records: records
      })
    });

    const data = await res.json();
    if (data.success) {
      alert("Attendance saved successfully!");
      if (typeof loadHistory === 'function') loadHistory();
    } else {
      alert("Error saving: " + (data.error || "Unknown error"));
    }
  } catch (err) {
    console.error("Save error:", err);
    alert("Connection error while saving attendance.");
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-save"></i> Save Record';
  }
}

async function loadHistory() {
  const raw = localStorage.getItem(ACTIVE_KEY);
  if (!raw) return;
  const assignment = JSON.parse(raw);

  const historyList = $("historyList");
  if (!historyList) return;

  try {
    const res = await fetch(`${API}/attendance/records`);
    const allRecords = await res.json();

    // Filter for THIS class
    const classRecords = allRecords.filter(r => r.class_id === assignment.class_id).reverse();

    if (classRecords.length === 0) {
      historyList.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-secondary); font-size: 0.8rem;">No past sessions found.</div>';
      return;
    }

    historyList.innerHTML = classRecords.map(rec => `
      <div style="padding: 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.8rem;">
        <div class="flex justify-between">
          <strong style="color: var(--accent-primary);">${rec.date}</strong>
          <span style="color: var(--text-secondary);">${rec.records.filter(s => s.status === "Present").length} / ${rec.records.length} Present</span>
        </div>
        <div style="font-size: 0.7rem; color: var(--text-secondary); margin-top: 0.25rem;">Saved at ${rec.timestamp}</div>
      </div>
    `).join("");

  } catch (err) {
    console.error("History error:", err);
    historyList.innerHTML = '<div style="color: #f87171; padding: 1rem;">Failed to load history.</div>';
  }
}


async function runVideoAttendance() {
  const btn = $("runAiBtn");
  const statusBody = $("attendanceBody");

  if (!confirm("Run AI Face Recognition on the latest classroom video? \nThis may take a few moments.")) return;

  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Initializing...';

  try {
    // 1. Trigger the background process
    const runRes = await fetch(`${API}/attendance/run`, { method: "POST" });
    const runData = await runRes.json();

    if (!runRes.ok || !runData.success) {
      throw new Error(runData.error || "Failed to start AI process");
    }

    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> AI Processing...';

    // 2. Poll for status
    const pollInterval = 3000; // 3 seconds
    let attempts = 0;
    const maxAttempts = 200; // 10 minutes total

    const pollStatus = async () => {
      const statusRes = await fetch(`${API}/attendance/status`);
      const statusData = await statusRes.json();

      if (statusData.status === "running") {
        attempts++;
        if (attempts > maxAttempts) {
          throw new Error("AI Processing timed out.");
        }
        setTimeout(pollStatus, pollInterval);
        return;
      }

      if (statusData.status === "error") {
        throw new Error(statusData.error || "AI Processing Failed");
      }

      if (statusData.status === "success") {
        handleAiSuccess(statusData.data);
      }
    };

    const handleAiSuccess = (aiResults) => {
      const rows = statusBody.querySelectorAll("tr");
      let totalConf = 0;
      let matchCount = 0;

      rows.forEach(tr => {
        const nameCell = tr.querySelectorAll("td")[1];
        if (!nameCell) return;
        const studentName = nameCell.textContent.trim();
        const aiRecord = aiResults.find(r => r.name === studentName);

        const accuracyCell = tr.querySelector(".accuracy-cell");
        const tag = tr.querySelector(".tag");
        const actionBtn = tr.querySelector("button");

        if (aiRecord && aiRecord.present === "YES") {
          const dist = parseFloat(aiRecord.avg_confidence || 0);
          let accuracy;
          if (dist > 2) {
            accuracy = Math.max(0, Math.min(100, 100 - dist));
          } else {
            accuracy = Math.max(0, Math.min(100, (1 - dist) * 100));
          }

          accuracyCell.innerHTML = `<span class="status status-ok" style="font-size: 0.7rem;">${Math.round(accuracy)}% Match</span>`;
          totalConf += accuracy;
          matchCount++;

          tag.textContent = "Present";
          tag.className = "tag tag-present";
          actionBtn.textContent = "Mark Absent";
        } else {
          accuracyCell.innerHTML = `<span class="status status-inactive" style="font-size: 0.7rem; opacity: 0.6;">No Match</span>`;
          tag.textContent = "Absent";
          tag.className = "tag tag-absent";
          actionBtn.textContent = "Mark Present";
        }
      });

      // Update Global Model Accuracy Box
      const accBox = $("accuracyBox");
      if (matchCount > 0) {
        const globalAcc = totalConf / matchCount;
        accBox.innerHTML = `
          <div class="accuracy-card">
            <div>
              <div class="accuracy-label">AI Model Performance</div>
              <div style="font-size: 0.8rem; color: var(--text-secondary);">Average recognition confidence for this session</div>
            </div>
            <div class="accuracy-value">${globalAcc.toFixed(1)}%</div>
          </div>
        `;
      } else {
        accBox.innerHTML = "";
      }

      alert("Attendance processed! Check the recap table below.");
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-robot"></i> Run AI Attendance';
    };

    // Start polling
    pollStatus();

  } catch (e) {
    console.error("AI Error:", e);
    alert("AI Error: " + e.message);
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-robot"></i> Run AI Attendance';
  }
}

// Modal Logic
let currentSaveCallback = null;

function openSeatModal(label, currentName, onSave) {
  const modal = $("seatModal");
  const labelSpan = $("modalSeatLabel");
  const input = $("modalStudentName");

  labelSpan.textContent = label;
  input.value = currentName;
  currentSaveCallback = onSave;

  modal.style.display = "flex";
  input.focus();
}

function closeSeatModal() {
  $("seatModal").style.display = "none";
  currentSaveCallback = null;
}

// Wire up Modal Buttons (Run once)
(function wireModalParams() {
  // Check if buttons exist to avoid double-wiring if init runs multiple times
  if ($("modalSaveBtn").dataset.wired) return;

  $("modalSaveBtn").addEventListener("click", () => {
    if (currentSaveCallback) {
      const name = $("modalStudentName").value.trim();
      currentSaveCallback(name);
    }
    closeSeatModal();
  });

  $("modalCancelBtn").addEventListener("click", closeSeatModal);

  // Allow Enter key to save
  $("modalStudentName").addEventListener("keyup", (e) => {
    if (e.key === "Enter") {
      $("modalSaveBtn").click();
    }
  });

  $("modalSaveBtn").dataset.wired = "true";
})();

async function saveSeat(classId, row, col, name) {
  await fetch(`${API}/classes/seat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ class_id: classId, row, col, name })
  });
}

function updateSessionUI() {
  const badge = $("stateBadge");
  const startBtn = $("startBtn");
  const pauseBtn = $("pauseBtn");
  const endBtn = $("endBtn");

  badge.className = "status"; // reset
  startBtn.disabled = false;
  pauseBtn.disabled = true;
  endBtn.disabled = true;

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
    startBtn.disabled = false; // can resume
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

// --- Camera Logic ---

function setStatus(text, ok = null) {
  const s = $("camStatus");
  s.textContent = text;
  s.classList.remove("status-ok", "status-bad");
  if (ok === true) s.classList.add("status-ok");
  if (ok === false) s.classList.add("status-bad");
}

function showImg(show) {
  $("camImg").style.display = show ? "block" : "none";
  $("camPlaceholder").style.display = show ? "none" : "block";
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
  img.src = ""; // stop stream

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
      if (mode === "snapshot") u.pathname = "/capture";
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
    if (!isAuto) setStatus("Status: enter a camera URL first", false);
    return;
  }

  const url = normalizeUrl(rawUrl, mode);

  localStorage.setItem(CAM_URL_KEY, rawUrl);
  localStorage.setItem(CAM_MODE_KEY, mode);
  localStorage.setItem(CAM_FPS_KEY, String(fps));

  disconnectCamera();

  if (mode === "mjpeg") {
    $("camHint").textContent = "Hint: ESP32 often uses /stream (sometimes port :81).";
    connectMJPEG(url);
  } else {
    $("camHint").textContent = "Hint: Snapshot often uses /capture.";
    connectSnapshot(url, fps);
  }

  startAutoReconnect();
}

function restoreCamSettings() {
  const savedUrl = localStorage.getItem(CAM_URL_KEY) || "";
  const savedMode = localStorage.getItem(CAM_MODE_KEY) || "mjpeg";
  const savedFps = localStorage.getItem(CAM_FPS_KEY) || "5";

  $("camUrl").value = savedUrl;
  $("camMode").value = savedMode;
  $("camFps").value = savedFps;
}

function wireCameraUI() {
  restoreCamSettings();

  $("connectBtn").addEventListener("click", () => doConnect(false));
  $("disconnectBtn").addEventListener("click", disconnectCamera);

  $("camMode").addEventListener("change", () => {
    if ($("camUrl").value.trim()) doConnect(false);
  });
  $("camFps").addEventListener("change", () => {
    if ($("camMode").value === "snapshot" && $("camUrl").value.trim()) doConnect(false);
  });

  // Video Upload
  $("uploadTriggerBtn").addEventListener("click", () => $("videoUpload").click());
  $("videoUpload").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const btn = $("uploadTriggerBtn");
    const originalHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API}/attendance/upload`, {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (data.success) {
        alert("Video uploaded successfully: " + data.filename + "\nYou can now run AI Attendance.");
      } else {
        alert("Upload failed: " + (data.error || "Unknown error"));
      }
    } catch (err) {
      console.error("Upload error:", err);
      alert("Error uploading video.");
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalHtml;
      e.target.value = ""; // clear input
    }
  });
}

(function init() {
  loadSession();
  wireSessionUI();
  wireCameraUI();
  $("saveAttendanceBtn").addEventListener("click", saveAttendance);
})();
