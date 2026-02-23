const API = "/api";

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

async function loadStudentData() {
    const user = getCurrentUser();
    if (!user) return;

    document.getElementById("userName").textContent = user.name || user.username;
    document.getElementById("userAvatar").textContent = (user.name || user.username)[0].toUpperCase();

    try {
        const [allGrades, exams, homework, attendance, subjects] = await Promise.all([
            fetchJSON(`${API}/grades`),
            fetchJSON(`${API}/exams`),
            fetchJSON(`${API}/homework`),
            fetchJSON(`${API}/attendance/records`),
            fetchJSON(`${API}/subjects`)
        ]);

        const subjectMap = new Map(subjects.map(s => [s.id, s.name]));
        const studentName = (user.name || "").toLowerCase();
        const studentUser = (user.username || "").toLowerCase();
        const myGrades = allGrades.filter(g =>
            (g.student_name || "").toLowerCase() === studentName ||
            (g.student_name || "").toLowerCase() === studentUser
        );
        const gradeListEl = document.getElementById("gradesList");
        gradeListEl.innerHTML = "";

        if (myGrades.length === 0) {
            gradeListEl.innerHTML = '<div class="text-center py-4">No grades recorded yet.</div>';
        } else {
            renderStudentPerformanceChart(myGrades, exams, homework);
            myGrades.forEach(g => {
                let item = null;
                if (g.item_type === 'exam') item = exams.find(e => e.id == g.item_id);
                else item = homework.find(h => h.id == g.item_id);

                const subName = item ? (subjectMap.get(item.subject_id) || "General") : "Unknown";
                const title = item ? item.title : "Deleted Item";

                const div = el("div", "item", "");
                div.style.padding = "1rem";
                div.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
                div.innerHTML = `
          <div class="flex justify-between items-center">
            <div>
              <div class="title" style="font-size: 0.9rem;">${title}</div>
              <div class="sub" style="font-size: 0.7rem; opacity: 0.6;">${subName} • ${g.item_type}</div>
            </div>
            <div class="grade-box text-center">
              <div style="font-size: 1.1rem; font-weight: 700; color: var(--accent-secondary);">${g.score}</div>
              <div style="font-size: 0.6rem; opacity: 0.5;">Score</div>
            </div>
          </div>
          ${g.comment ? `<div style="font-size: 0.75rem; margin-top: 0.5rem; color: var(--text-secondary); font-style: italic;">"${g.comment}"</div>` : ''}
        `;
                gradeListEl.appendChild(div);
            });
        }

        const attListEl = document.getElementById("attendanceList");
        attListEl.innerHTML = "";
        const recentAtt = attendance.slice().reverse();
        let count = 0;

        recentAtt.forEach(session => {
            const me = (session.records || []).find(r =>
                (r.name || "").toLowerCase() === studentName ||
                (r.name || "").toLowerCase() === studentUser
            );
            if (me && count < 10) {
                count++;
                const div = el("div", "item", "");
                div.style.padding = "0.75rem";
                div.style.display = "flex";
                div.style.justifyContent = "space-between";
                div.style.alignItems = "center";
                div.style.borderBottom = "1px solid rgba(255,255,255,0.05)";

                const date = new Date(session.timestamp).toLocaleDateString();
                const statusClass = me.status === 'Present' ? 'text-green-400' : 'text-red-400';

                div.innerHTML = `
          <div style="font-size: 0.85rem;">${date}</div>
          <div class="${statusClass}" style="font-size: 0.8rem; font-weight: 600;">${me.status}</div>
        `;
                attListEl.appendChild(div);
            }
        });

        if (count === 0) {
            attListEl.innerHTML = '<div class="text-center py-4">No attendance records.</div>';
        }

    } catch (err) {
        console.error("Failed to load student dashboard:", err);
    }
}

document.getElementById("logoutBtn")?.addEventListener("click", () => {
    logout();
});

(function init() {
    protectPage("student");
    loadStudentData();
})();

function renderStudentPerformanceChart(myGrades, exams, homework) {
    const ctx = document.getElementById('studentPerformanceChart').getContext('2d');

    // Sort and map grades for visualization
    const dataPoints = myGrades.map(g => {
        let item = null;
        if (g.item_type === 'exam') item = exams.find(e => e.id == g.item_id);
        else item = homework.find(h => h.id == g.item_id);
        return {
            title: item ? item.title : 'Assessment',
            score: parseFloat(g.score)
        };
    });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: dataPoints.map(d => d.title),
            datasets: [{
                label: 'Score',
                data: dataPoints.map(d => d.score),
                backgroundColor: 'rgba(37, 99, 235, 0.8)',
                hoverBackgroundColor: '#2563eb',
                borderRadius: 12,
                barThickness: 40
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1e293b',
                    padding: 12,
                    titleFont: { size: 14, weight: 'bold' },
                    bodyFont: { size: 13 },
                    cornerRadius: 8
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(0,0,0,0.05)', borderDash: [5, 5] },
                    ticks: { color: '#64748b', font: { weight: '600' } }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#64748b', font: { weight: '600' } }
                }
            }
        }
    });
}
