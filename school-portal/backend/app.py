from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
import json
import bcrypt
import secrets
import string
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import os
from dotenv import load_dotenv

load_dotenv()

# --------------------
# App setup
# --------------------
BASE_DIR = Path(__file__).parent
PARENT_DIR = BASE_DIR.parent

app = Flask(__name__, static_folder=str(PARENT_DIR), static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# MongoDB setup
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGO_URL") or "mongodb://localhost:27017/attendance_db"
mongo_db_name = os.getenv("MONGO_DB_NAME")

try:
    # Use certifi for cloud SSL if needed, otherwise standard
    import certifi
    ca = certifi.where()
    # Adding tls=True and tlsAllowInvalidCertificates=True as the "Global Fix"
    mongo_client = MongoClient(
        MONGO_URI, 
        serverSelectionTimeoutMS=10000, 
        tlsCAFile=ca,
        tls=True,
        tlsAllowInvalidCertificates=True
    )
except ImportError:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)

db = None
try:
    # If DB name isn't a separate variable, MongoClient can get it from the URI
    # or we default to 'attendance_db' if the URI is just the host
    active_db_name = mongo_db_name or mongo_client.get_default_database().name or "attendance_db"
    mongo_client.admin.command("ping")
    db = mongo_client[active_db_name]
    print(f"[OK] MongoDB connected to database: {active_db_name}")
except Exception as e:
    print("[ERROR] MongoDB connection failed:", e)
    # Default fallback for local testing
    db = mongo_client["attendance_db"]


# --------------------
# DB helpers – MongoDB only, no JSON fallback
# --------------------
def read_collection(collection_name: str, query: dict = None) -> list:
    """Read documents from MongoDB if available, otherwise from backend JSON files."""
    if db is not None:
        col = db[collection_name]
        return list(col.find(query or {}, {"_id": False}))

    raise RuntimeError("MongoDB not connected. Set MONGO_URI and ensure DB is reachable.")


def upsert_document(collection_name: str, doc: dict):
    """Insert a single document."""
    if db is not None:
        db[collection_name].insert_one({k: v for k, v in doc.items() if k != "_id"})
        return

    raise RuntimeError("MongoDB not connected. Set MONGO_URI and ensure DB is reachable.")


def replace_collection(collection_name: str, data: list):
    """Replace an entire collection with new data (delete all then insert)."""
    if db is not None:
        col = db[collection_name]
        col.delete_many({})
        if data:
            col.insert_many([{k: v for k, v in d.items() if k != "_id"} for d in data])
        return

    raise RuntimeError("MongoDB not connected. Set MONGO_URI and ensure DB is reachable.")


def next_id(items: list) -> int:
    return max((item.get("id", 0) for item in items), default=0) + 1


def generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits + "!$@#"
    return "".join(secrets.choice(alphabet) for _ in range(length))


# --------------------
# AUTH
# --------------------
@app.post("/api/login")
def api_login():
    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    password = payload.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    # Get all users and find case-insensitive match
    all_users = read_collection("users")
    user = next((u for u in all_users if u.get("username", "").lower() == username), None)

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    raw_pw_hash = user.get("password_hash") or ""
    if not raw_pw_hash:
        return jsonify({"error": "Account has no password configured. Contact admin."}), 403

    try:
        pw_hash_bytes = raw_pw_hash.encode("utf-8") if isinstance(raw_pw_hash, str) else raw_pw_hash
        match = bcrypt.checkpw(password.encode("utf-8"), pw_hash_bytes)
    except Exception as e:
        print(f"bcrypt error for {username}: {e}")
        return jsonify({"error": "Authentication error"}), 500

    if not match:
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "id": user.get("id"),
        "username": user["username"],
        "role": user["role"],
        "name": user.get("name", user["username"])
    })


# --------------------
# HEALTH CHECK & INIT
# --------------------
@app.get("/api/health")
def api_health():
    return jsonify({"status": "ok"})

@app.get("/api/init_admin")
def init_admin():
    try:
        pw_hash = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        db["users"].update_one(
            {"username": "admin"},
            {"$set": {
                "id": 1,
                "username": "admin",
                "role": "admin",
                "name": "Administrator",
                "password_hash": pw_hash
            }},
            upsert=True
        )
        return "✅ Admin account created/reset to admin123! Go back to login."
    except Exception as e:
        return f"❌ DATABASE ERROR: {str(e)}"


# --------------------
# ROOT – serve login page from school-portal/
# --------------------
@app.route("/")
def index():
    return send_from_directory(str(PARENT_DIR), "login.html")


# --------------------
# USERS
# --------------------
@app.get("/api/teachers")
def get_teachers():
    users = read_collection("users", {"role": "teacher"})
    return jsonify([
        {"id": u.get("id"), "username": u.get("username"), "name": u.get("name", u.get("username"))}
        for u in users
    ])


@app.get("/api/students")
def get_students():
    users = read_collection("users", {"role": "student"})
    return jsonify([
        {"id": u.get("id"), "username": u.get("username"), "name": u.get("name", u.get("username"))}
        for u in users
    ])


@app.post("/api/admin/create_teacher")
def admin_create_teacher():
    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    name = (payload.get("name") or "").strip() or username

    if not username:
        return jsonify({"error": "Username required"}), 400

    # Check for case-insensitive duplicate
    all_users = read_collection("users")
    if any(u.get("username", "").lower() == username for u in all_users):
        return jsonify({"error": "Username already exists"}), 400

    plain_password = generate_password()
    pw_hash = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    all_users = read_collection("users")
    new_user = {
        "id": next_id(all_users),
        "username": username,
        "role": "teacher",
        "name": name,
        "password_hash": pw_hash
    }
    upsert_document("users", new_user)
    return jsonify({"username": username, "name": name, "password": plain_password}), 201


@app.post("/api/admin/create_student")
def admin_create_student():
    payload = request.get_json(force=True, silent=True) or {}
    username = (payload.get("username") or "").strip().lower()
    name = (payload.get("name") or "").strip() or username

    if not username:
        return jsonify({"error": "Username required"}), 400

    # Check for case-insensitive duplicate
    all_users = read_collection("users")
    if any(u.get("username", "").lower() == username for u in all_users):
        return jsonify({"error": "Username already exists"}), 400

    plain_password = generate_password()
    pw_hash = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    all_users = read_collection("users")
    new_user = {
        "id": next_id(all_users),
        "username": username,
        "role": "student",
        "name": name,
        "password_hash": pw_hash
    }
    upsert_document("users", new_user)
    return jsonify({"username": username, "name": name, "password": plain_password}), 201


# --------------------
# CLASSES
# --------------------
@app.get("/api/classes")
def get_classes():
    return jsonify(read_collection("classes"))


@app.post("/api/classes")
def add_class():
    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    rows = int(payload.get("rows") or 4)
    cols = int(payload.get("cols") or 6)

    if not name:
        return jsonify({"error": "Class name required"}), 400

    items = read_collection("classes")
    new_item = {"id": next_id(items), "name": name, "rows": rows, "cols": cols}
    upsert_document("classes", new_item)
    return jsonify(new_item), 201


@app.post("/api/classes/seat")
def update_seat():
    payload = request.get_json(force=True, silent=True) or {}
    class_id = int(payload.get("class_id", 0))
    row = int(payload.get("row", 0))
    col = int(payload.get("col", 0))
    name = (payload.get("name") or "").strip()

    items = read_collection("classes")
    target = next((c for c in items if c["id"] == class_id), None)
    if not target:
        return jsonify({"error": "Class not found"}), 404

    if "seating" not in target:
        target["seating"] = {}

    key = f"{row}_{col}"
    if name:
        target["seating"][key] = name
    else:
        target["seating"].pop(key, None)

    replace_collection("classes", items)
    return jsonify({"success": True, "name": name})


# --------------------
# SUBJECTS
# --------------------
@app.get("/api/subjects")
def get_subjects():
    return jsonify(read_collection("subjects"))


@app.post("/api/subjects")
def add_subject():
    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Subject name required"}), 400

    items = read_collection("subjects")
    new_item = {"id": next_id(items), "name": name}
    upsert_document("subjects", new_item)
    return jsonify(new_item), 201


# --------------------
# ASSIGNMENTS
# --------------------
@app.get("/api/assignments")
def get_assignments():
    return jsonify(read_collection("assignments"))


@app.post("/api/assignments")
def add_assignment():
    payload = request.get_json(force=True, silent=True) or {}
    teacher_username = (payload.get("teacher_username") or "").strip()
    class_id = int(payload.get("class_id", 0))
    subject_id = int(payload.get("subject_id", 0))

    if not teacher_username:
        return jsonify({"error": "Teacher username required"}), 400

    existing = read_collection("assignments", {
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id
    })
    if existing:
        return jsonify({"error": "Assignment already exists"}), 400

    items = read_collection("assignments")
    new_item = {
        "id": next_id(items),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id
    }
    upsert_document("assignments", new_item)
    return jsonify(new_item), 201


# --------------------
# EXAMS
# --------------------
@app.get("/api/exams")
def api_get_exams():
    query = {}
    if request.args.get("teacher_username"):
        query["teacher_username"] = request.args["teacher_username"]
    if request.args.get("class_id"):
        query["class_id"] = int(request.args["class_id"])
    if request.args.get("subject_id"):
        query["subject_id"] = int(request.args["subject_id"])
    return jsonify(read_collection("exams", query))


@app.post("/api/exams")
def create_exam():
    payload = request.get_json(force=True, silent=True) or {}
    teacher_username = (payload.get("teacher_username") or "").strip()
    class_id = int(payload.get("class_id") or 0)
    subject_id = int(payload.get("subject_id") or 0)
    title = (payload.get("title") or "").strip()
    kind = (payload.get("kind") or "").strip()
    date = (payload.get("date") or "").strip()

    if not teacher_username or not title or not kind or not date:
        return jsonify({"error": "teacher_username, title, kind, date required"}), 400

    items = read_collection("exams")
    new_item = {
        "id": next_id(items),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id,
        "title": title,
        "kind": kind,
        "date": date
    }
    upsert_document("exams", new_item)
    return jsonify(new_item), 201


# --------------------
# HOMEWORK
# --------------------
@app.get("/api/homework")
def get_homework():
    query = {}
    if request.args.get("class_id"):
        query["class_id"] = int(request.args["class_id"])
    if request.args.get("subject_id"):
        query["subject_id"] = int(request.args["subject_id"])
    return jsonify(read_collection("homework", query))


@app.post("/api/homework")
def create_homework():
    payload = request.get_json(force=True, silent=True) or {}
    teacher_username = (payload.get("teacher_username") or "").strip()
    class_id = int(payload.get("class_id") or 0)
    subject_id = int(payload.get("subject_id") or 0)
    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    due_date = (payload.get("due_date") or "").strip()

    if not teacher_username or not title or not due_date:
        return jsonify({"error": "teacher_username, title, due_date required"}), 400

    items = read_collection("homework")
    new_item = {
        "id": next_id(items),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id,
        "title": title,
        "description": description,
        "due_date": due_date
    }
    upsert_document("homework", new_item)
    return jsonify(new_item), 201


# --------------------
# GRADES
# --------------------
@app.post("/api/grades")
def api_save_grades():
    payload = request.get_json(force=True, silent=True) or {}
    item_id = payload.get("item_id")
    item_type = payload.get("item_type")
    class_id = payload.get("class_id")
    grades_data = payload.get("grades", [])

    if not item_id or not item_type:
        return jsonify({"error": "item_id and item_type required"}), 400

    # Remove existing grades for this item then batch insert new ones
    db["grades"].delete_many({"item_id": item_id, "item_type": item_type})
    new_docs = [
        {
            "item_id": item_id,
            "item_type": item_type,
            "class_id": class_id,
            "student_name": entry.get("student_name"),
            "score": entry.get("score"),
            "comment": entry.get("comment")
        }
        for entry in grades_data
    ]
    if new_docs:
        db["grades"].insert_many(new_docs)
    return jsonify({"success": True})


@app.get("/api/grades")
def api_get_grades():
    item_id = request.args.get("item_id")
    item_type = request.args.get("item_type")
    results = list(db["grades"].find(
        {"item_id": item_id, "item_type": item_type},
        {"_id": False}
    ))
    return jsonify(results)


# --------------------
# ATTENDANCE – AI bridge
# --------------------
import subprocess
import sys
import csv
import threading

ai_job = {"status": "idle", "data": None, "error": None, "stdout": None, "stderr": None}


def run_ai_script_task(script_path, project_root):
    global ai_job
    try:
        ai_job.update({"status": "running", "error": None, "data": None})
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        ai_job["stdout"] = result.stdout
        ai_job["stderr"] = result.stderr
        if result.returncode != 0:
            ai_job.update({"status": "error", "error": "Script execution failed"})
            return
        csv_path = project_root / "output" / "attendance" / "attendance.csv"
        if not csv_path.exists():
            ai_job.update({"status": "error", "error": "CSV results not found"})
            return
        with open(csv_path, mode="r", encoding="utf-8") as f:
            ai_job["data"] = list(csv.DictReader(f))
        ai_job["status"] = "success"
    except Exception as e:
        ai_job.update({"status": "error", "error": str(e)})


@app.post("/api/attendance/run")
def api_run_attendance():
    global ai_job
    if ai_job["status"] == "running":
        return jsonify({"error": "AI process is already running"}), 400

    PROJECT_ROOT = PARENT_DIR.parent
    script_path = PROJECT_ROOT / "scripts" / "run_attendance_arcface.py"
    if not script_path.exists():
        return jsonify({"error": f"Script not found: {script_path}"}), 500

    ai_job["status"] = "running"
    t = threading.Thread(target=run_ai_script_task, args=(script_path, PROJECT_ROOT), daemon=True)
    t.start()
    return jsonify({"success": True, "message": "AI process started"})


@app.get("/api/attendance/status")
def api_get_attendance_status():
    return jsonify(ai_job)


@app.post("/api/attendance/upload")
def api_upload_video():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No selected file"}), 400
    from werkzeug.utils import secure_filename
    PROJECT_ROOT = PARENT_DIR.parent
    video_dir = PROJECT_ROOT / "data" / "classroom_videos"
    video_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename)
    save_path = video_dir / filename
    file.save(str(save_path))
    return jsonify({"success": True, "filename": filename, "path": str(save_path)})


@app.get("/api/attendance/history")
def api_get_attendance_history():
    """Returns pivoted attendance history from MongoDB (name vs dates)."""
    sessions = read_collection("attendance")
    if not sessions:
        return jsonify([])

    # Pivot logic: name -> { date1: status, date2: status, ... }
    students_data = {}
    all_dates = set()

    for s in sessions:
        date = s.get("date", "Unknown").split()[0]
        all_dates.add(date)
        for r in s.get("records", []):
            name = r.get("name")
            if name not in students_data:
                students_data[name] = {"name": name}
            students_data[name][date] = "YES" if r.get("status") == "Present" else "NO"

    # Ensure all students have a value for all dates
    sorted_dates = sorted(list(all_dates))
    result = []
    for name in sorted(students_data.keys()):
        row = students_data[name]
        for d in sorted_dates:
            if d not in row:
                row[d] = "NO"
        result.append(row)

    return jsonify(result)


@app.post("/api/attendance/save")
def api_save_attendance():
    from datetime import datetime
    payload = request.get_json(force=True, silent=True) or {}
    class_id = payload.get("class_id")
    subject_id = payload.get("subject_id")
    teacher_username = payload.get("teacher_username")
    date = payload.get("date")
    records = payload.get("records")

    if not all([class_id, subject_id, teacher_username, date, records]):
        return jsonify({"error": "Missing required fields"}), 400

    all_records = read_collection("attendance")
    new_record = {
        "id": next_id(all_records),
        "class_id": class_id,
        "subject_id": subject_id,
        "teacher_username": teacher_username,
        "date": date,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "records": records
    }
    upsert_document("attendance", new_record)
    return jsonify({"success": True, "id": new_record["id"]}), 201


@app.get("/api/attendance/records")
def api_get_records():
    return jsonify(read_collection("attendance"))


# --------------------
# REPORTS
# --------------------
@app.get("/api/reports/attendance")
def api_get_attendance_report():
    query = {}
    if request.args.get("class_id"):
        query["class_id"] = int(request.args["class_id"])
    sessions = read_collection("attendance", query)
    stats = {}
    for session in sessions:
        for record in session.get("records", []):
            name = record.get("name")
            status = record.get("status")
            if name not in stats:
                stats[name] = {"present": 0, "absent": 0, "total": 0}
            stats[name]["total"] += 1
            if status == "Present":
                stats[name]["present"] += 1
            else:
                stats[name]["absent"] += 1
    result = []
    for name, data in stats.items():
        pct = (data["present"] / data["total"] * 100) if data["total"] > 0 else 0
        result.append({"name": name, "present": data["present"],
                        "absent": data["absent"], "total": data["total"],
                        "percentage": round(pct, 1)})
    return jsonify(result)


@app.get("/api/reports/performance")
def api_get_performance_report():
    query = {}
    if request.args.get("class_id"):
        query["class_id"] = int(request.args["class_id"])
    grades = read_collection("grades", query)
    stats = {}
    for g in grades:
        name = g.get("student_name")
        score = g.get("score")
        if name and score is not None:
            stats.setdefault(name, [])
            try:
                stats[name].append(float(score))
            except (ValueError, TypeError):
                pass
    result = []
    for name, scores in stats.items():
        avg = sum(scores) / len(scores) if scores else 0
        result.append({"name": name, "average": round(avg, 1), "count": len(scores)})
    return jsonify(result)


# --------------------
# ANALYTICS
# --------------------
@app.get("/api/analytics/attendance_trend")
def api_attendance_trend():
    """Returns attendance percentage per day across the entire school."""
    sessions = read_collection("attendance")
    if not sessions:
        return jsonify([])

    # Group by date
    daily_stats = {}
    for s in sessions:
        date = s.get("date", "").split(" ")[0]
        if not date: continue
        
        records = s.get("records", [])
        total = len(records)
        present = sum(1 for r in records if r.get("status") == "Present")
        
        if date not in daily_stats:
            daily_stats[date] = {"total": 0, "present": 0}
        
        daily_stats[date]["total"] += total
        daily_stats[date]["present"] += present

    result = []
    for date in sorted(daily_stats.keys()):
        stats = daily_stats[date]
        pct = (stats["present"] / stats["total"] * 100) if stats["total"] > 0 else 0
        result.append({"date": date, "percentage": round(pct, 1)})
    
    return jsonify(result)


@app.get("/api/analytics/grade_distribution")
def api_grade_distribution():
    """Returns count of students per grade bracket."""
    grades = read_collection("grades")
    brackets = {"A (90-100)": 0, "B (80-89)": 0, "C (70-79)": 0, "D (60-69)": 0, "F (<60)": 0}
    
    for g in grades:
        try:
            score = float(g.get("score", 0))
            if score >= 90: brackets["A (90-100)"] += 1
            elif score >= 80: brackets["B (80-89)"] += 1
            elif score >= 70: brackets["C (70-79)"] += 1
            elif score >= 60: brackets["D (60-69)"] += 1
            else: brackets["F (<60)"] += 1
        except:
            continue
            
    return jsonify([{"label": k, "count": v} for k, v in brackets.items()])


# --------------------
# Run server
# --------------------
if __name__ == "__main__":
    # Use PORT environment variable for hosting platforms
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_DEBUG", "False").lower() == "true")
