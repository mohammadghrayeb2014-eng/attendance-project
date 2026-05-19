from flask import Flask, render_template, jsonify, send_from_directory, request
from pathlib import Path
import subprocess
import sys
import time
import os
import bcrypt
import secrets
import string
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ATT = ROOT / "output" / "attendance"
OUTPUT_DBG = ROOT / "output" / "debug_frames"
ATT_CSV = OUTPUT_ATT / "attendance.csv"
MASTER_CSV = OUTPUT_ATT / "master_attendance.csv"

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

MONGO_URI = os.getenv("MONGO_URI", "").strip()
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "attendance_db").strip()

db = None
USE_MONGO = False

try:
    if not MONGO_URI:
        raise RuntimeError("MONGO_URI is missing")

    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        tlsCAFile=certifi.where()
    )
    client.admin.command("ping")
    db = client[MONGO_DB_NAME]
    USE_MONGO = True
    print(f"[OK] Connected to MongoDB database: {MONGO_DB_NAME}")

except Exception as e:
    print(f"[CRITICAL] MongoDB connection failed: {e}")
    print("[WARNING] User accounts will NOT persist unless MongoDB works.")


def next_id(collection_name):
    if not USE_MONGO:
        return 1

    docs = list(db[collection_name].find({}, {"_id": 0, "id": 1}))
    return max((d.get("id", 0) for d in docs), default=0) + 1


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits + "!$@#"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def ensure_admin():
    if not USE_MONGO:
        return

    admin = db.users.find_one({"username": "admin"})
    if not admin:
        db.users.insert_one({
            "id": 1,
            "username": "admin",
            "role": "admin",
            "name": "Administrator",
            "password_hash": hash_password("admin123")
        })
        print("[INIT] Created admin account: admin / admin123")


ensure_admin()


@app.before_request
def log_request():
    print(f"DEBUG RECV: {request.method} {request.path}")
    if request.path.endswith("/login"):
        print(f"DEBUG LOGIN BODY: {request.get_data(as_text=True)}")


# --------------------
# Pages
# --------------------
@app.get("/")
def home():
    return render_template("login.html")


@app.get("/login")
def login_page():
    return render_template("login.html")


@app.get("/session")
def session_page():
    return render_template("index.html")


@app.get("/admin")
def admin_page():
    return render_template("admin.html")


@app.get("/teacher")
def teacher_page():
    return render_template("teacher.html")


@app.get("/student")
def student_page():
    return render_template("student.html")


# --------------------
# Health
# --------------------
@app.get("/api/health")
def health():
    return jsonify({
        "ok": True,
        "storage": "mongo" if USE_MONGO else "not_connected",
        "database": MONGO_DB_NAME
    })


# --------------------
# Auth
# --------------------
@app.post("/api/login")
def api_login():
    if not USE_MONGO:
        return jsonify({"error": "Database is not connected"}), 500

    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = db.users.find_one({"username": username}, {"_id": 0})

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    pw_hash = user.get("password_hash") or ""
    if not pw_hash:
        return jsonify({"error": "Account has no password configured"}), 403

    try:
        valid = bcrypt.checkpw(password.encode("utf-8"), pw_hash.encode("utf-8"))
    except Exception:
        return jsonify({"error": "Authentication error"}), 500

    if not valid:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "name": user.get("name", user.get("username"))
    })


# --------------------
# Users
# --------------------
@app.get("/api/teachers")
def get_teachers():
    if not USE_MONGO:
        return jsonify([])

    teachers = list(db.users.find({"role": "teacher"}, {"_id": 0, "password_hash": 0}))
    return jsonify(teachers)


@app.get("/api/students")
def get_students():
    if not USE_MONGO:
        return jsonify([])

    students = list(db.users.find({"role": "student"}, {"_id": 0, "password_hash": 0}))
    return jsonify(students)


@app.post("/api/admin/create_teacher")
def create_teacher():
    return create_user("teacher")


@app.post("/api/admin/create_student")
def create_student():
    return create_user("student")


def create_user(role):
    if not USE_MONGO:
        return jsonify({"error": "Database is not connected"}), 500

    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    name = (payload.get("name") or "").strip() or username

    if not username:
        return jsonify({"error": "Username is required"}), 400

    if db.users.find_one({"username": username}):
        return jsonify({"error": "Username already exists"}), 400

    plain_password = generate_password()

    user = {
        "id": next_id("users"),
        "username": username,
        "role": role,
        "name": name,
        "password_hash": hash_password(plain_password)
    }

    db.users.insert_one(user)

    return jsonify({
        "username": username,
        "name": name,
        "role": role,
        "password": plain_password
    }), 201


# --------------------
# Attendance scripts
# --------------------
@app.get("/api/master")
def master_csv():
    if not MASTER_CSV.exists():
        return jsonify({
            "ok": False,
            "error": "master_attendance.csv not found. Run attendance first."
        }), 404

    return send_from_directory(OUTPUT_ATT, "master_attendance.csv", as_attachment=False)


@app.post("/api/run")
def run_attendance():
    script = ROOT / "scripts" / "run_attendance_arcface.py"

    if not script.exists():
        return jsonify({"ok": False, "error": f"Missing script: {script}"}), 400

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    dt = time.time() - t0

    return jsonify({
        "ok": result.returncode == 0,
        "seconds": round(dt, 2),
        "stdout": result.stdout,
        "stderr": result.stderr
    })


@app.post("/api/run_arcface_opencv")
def run_arcface_opencv():
    script = ROOT / "scripts" / "test_arcface_opencv.py"

    if not script.exists():
        return jsonify({"ok": False, "error": f"Missing script: {script}"}), 400

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    dt = time.time() - t0

    return jsonify({
        "ok": result.returncode == 0,
        "seconds": round(dt, 2),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "detector": "opencv"
    })


@app.post("/api/run_arcface_retinaface")
def run_arcface_retinaface():
    script = ROOT / "scripts" / "test_arcface_retinaface.py"

    if not script.exists():
        return jsonify({"ok": False, "error": f"Missing script: {script}"}), 400

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    dt = time.time() - t0

    return jsonify({
        "ok": result.returncode == 0,
        "seconds": round(dt, 2),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "detector": "retinaface"
    })


@app.get("/api/attendance")
def attendance_csv():
    if not ATT_CSV.exists():
        return jsonify({
            "ok": False,
            "error": "attendance.csv not found. Run attendance first."
        }), 404

    return send_from_directory(OUTPUT_ATT, "attendance.csv", as_attachment=False)


@app.get("/api/debug_list")
def debug_list():
    if not OUTPUT_DBG.exists():
        return jsonify({"ok": True, "files": []})

    files = sorted([p.name for p in OUTPUT_DBG.glob("*.jpg")])
    return jsonify({"ok": True, "files": files[:80]})


@app.get("/debug/<path:filename>")
def debug_file(filename):
    return send_from_directory(OUTPUT_DBG, filename)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)