const runBtn = document.getElementById("runBtn");
const statusEl = document.getElementById("status");
const tableBox = document.getElementById("tableBox");
const framesEl = document.getElementById("frames");

function setStatus(msg) {
  statusEl.textContent = msg;
}

function parseCSV(text) {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return { headers: [], rows: [] };

  const headers = lines[0].split(",").map(h => h.trim());
  const rows = lines.slice(1).map(line => line.split(",").map(x => x.trim()));
  return { headers, rows };
}

function renderTable(headers, rows) {
  if (!headers.length) {
    tableBox.innerHTML = "No data yet.";
    return;
  }

  let html = `<table class="tbl"><thead><tr>`;
  for (const h of headers) html += `<th>${h}</th>`;
  html += `</tr></thead><tbody>`;

  for (const r of rows) {
    html += `<tr>`;
    for (let i = 0; i < headers.length; i++) {
      const val = r[i] ?? "";
      const key = headers[i].toLowerCase();

      if (key === "present") {
        const cls = (val === "YES") ? "yes" : "no";
        html += `<td class="${cls}">${val}</td>`;
      } else {
        html += `<td>${val}</td>`;
      }
    }
    html += `</tr>`;
  }

  html += `</tbody></table>`;
  tableBox.innerHTML = html;
}

async function loadAttendanceTable() {
  const res = await fetch("/api/master");
  if (!res.ok) {
    tableBox.innerHTML = "No attendance.csv yet. Click Run Attendance.";
    return;
  }
  const text = await res.text();
  const { headers, rows } = parseCSV(text);
  renderTable(headers, rows);
}

async function loadFrames() {
  framesEl.innerHTML = "";
  const res = await fetch("/api/debug_list");
  const data = await res.json();

  if (!data.ok || !data.files.length) {
    framesEl.innerHTML = "<div class='muted'>No debug frames yet.</div>";
    return;
  }

  for (const f of data.files) {
    const img = document.createElement("img");
    img.src = `/debug/${encodeURIComponent(f)}`;
    img.loading = "lazy";
    framesEl.appendChild(img);
  }
}

runBtn.addEventListener("click", async () => {
  setStatus("Running...");
  runBtn.disabled = true;

  const res = await fetch("/api/run", { method: "POST" });
  const data = await res.json();

  if (!data.ok) {
    setStatus("Failed");
    tableBox.innerHTML = `<pre>${(data.stderr || data.stdout || data.error || "Unknown error")}</pre>`;
  } else {
    setStatus(`Done in ${data.seconds}s`);
    await loadAttendanceTable();
    await loadFrames();
  }

  runBtn.disabled = false;
});

(async function init() {
  await loadAttendanceTable();
  await loadFrames();
})();
