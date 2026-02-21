const API_BASE = "/api";
const STORAGE_KEY = "user";

async function login(username, password) {
  username = (username || "").trim();
  password = password || "";

  if (!username || !password) {
    return { ok: false, error: "Username and password are required." };
  }

  try {
    const res = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      // IMPORTANT: do NOT store anything on failed login
      return { ok: false, error: data.error || "Invalid credentials." };
    }

    // Only store AFTER backend says OK
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));

    // Redirect based on role
    if (data.role === "admin") window.location.href = "admin.html";
    else if (data.role === "teacher") window.location.href = "teacher.html";
    else window.location.href = "student.html";
    return { ok: true };
  } catch (e) {
    return { ok: false, error: "Connection error. Please try again later." };
  }
}

function getCurrentUser() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function logout() {
  localStorage.removeItem(STORAGE_KEY);
  window.location.href = "login.html";
}

function protectPage(requiredRole) {
  const user = getCurrentUser();

  // not logged in => go login
  if (!user) {
    window.location.href = "login.html";
    return;
  }

  // role mismatch => go to correct portal
  if (requiredRole && user.role !== requiredRole) {
    if (user.role === "admin") window.location.href = "admin.html";
    else if (user.role === "teacher") window.location.href = "teacher.html";
    else window.location.href = "student.html";
    return;
  }
}
