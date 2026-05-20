from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
from datetime import datetime
import os
import time
import bcrypt
import secrets
import string
import certifi
from pymongo import MongoClient
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent
FRONTEND_DIR = ROOT / "school-portal"

OUTPUT_ATT = ROOT / "output" / "attendance"
OUTPUT_DBG = ROOT / "output" / "debug_frames"
ATT_CSV = OUTPUT_ATT / "attendance.csv"
MASTER_CSV = OUTPUT_ATT / "master_attendance.csv"

load_dotenv(BASE_DIR / ".env")
load_dotenv()

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

MONGO_URI = os.getenv("MONGO_URI", "").strip().strip('"')
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "attendance_db").strip()

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing.")

mongo_client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000,
    tlsCAFile=certifi.where()
)

mongo_client.admin.command("ping")
db = mongo_client[MONGO_DB_NAME]

print(f"[OK] Connected to MongoDB database: {MONGO_DB_NAME}")


def clean_doc(doc):
    if doc:
        doc.pop("_id", None)
    return doc


def normalize(v):
    return str(v or "").strip().lower()


def next_id(collection_name):
    last = db[collection_name].find_one(sort=[("id", -1)])
    if last and "id" in last:
        return int(last["id"]) + 1
    return 1


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_password(length=10):
    chars = string.ascii_letters + string.digits + "!$@#"
    return "".join(secrets.choice(chars) for _ in range(length))


def ensure_admin():
    admin = db.users.find_one({"username": "admin"})
    if not admin:
        db.users.insert_one({
            "id": 1,
            "username": "admin",
            "role": "admin",
            "name": "Administrator",
            "password_hash": hash_password("admin123")
        })
        print("[INIT] Created admin: admin / admin123")


ensure_admin()


# =========================================================
# Frontend pages
# =========================================================

@app.get("/")
def index():
    return send_from_directory(str(FRONTEND_DIR), "login.html")


@app.get("/login")
def login_page():
    return send_from_directory(str(FRONTEND_DIR), "login.html")


@app.get("/admin")
def admin_page():
    return send_from_directory(str(FRONTEND_DIR), "admin.html")


@app.get("/teacher")
def teacher_page():
    return send_from_directory(str(FRONTEND_DIR), "teacher.html")


@app.get("/student")
def student_page():
    return send_from_directory(str(FRONTEND_DIR), "student.html")


@app.get("/class")
def class_page():
    return send_from_directory(str(FRONTEND_DIR), "class.html")


@app.get("/session")
def session_page():
    return send_from_directory(str(FRONTEND_DIR), "class.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(str(FRONTEND_DIR), filename)


# =========================================================
# Health
# =========================================================

@app.get("/api/health")
def health():
    mongo_client.admin.command("ping")
    return jsonify({
        "status": "ok",
        "storage": "mongo",
        "database": MONGO_DB_NAME
    })


# =========================================================
# Auth + users
# =========================================================

@app.post("/api/login")
def login():
    payload = request.get_json(force=True, silent=True) or {}

    username = normalize(payload.get("username"))
    password = payload.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = db.users.find_one({"username": username}, {"_id": 0})

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    password_hash = user.get("password_hash") or ""

    try:
        valid = check_password(password, password_hash)
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


@app.get("/api/users")
def get_users():
    users = list(db.users.find({}, {"_id": 0, "password_hash": 0}))
    return jsonify(users)


@app.get("/api/teachers")
def get_teachers():
    teachers = list(db.users.find({"role": "teacher"}, {"_id": 0, "password_hash": 0}))
    return jsonify(teachers)


@app.get("/api/students")
def get_students():
    students = list(db.users.find({"role": "student"}, {"_id": 0, "password_hash": 0}))
    return jsonify(students)


def create_user(role):
    payload = request.get_json(force=True, silent=True) or {}

    username = normalize(payload.get("username"))
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
        "id": user["id"],
        "username": username,
        "name": name,
        "role": role,
        "password": plain_password
    }), 201


@app.post("/api/admin/create_teacher")
def create_teacher():
    return create_user("teacher")


@app.post("/api/admin/create_student")
def create_student():
    return create_user("student")


@app.post("/api/admin/create_admin")
def create_admin():
    return create_user("admin")


# =========================================================
# Classes + seating
# =========================================================

@app.get("/api/classes")
def get_classes():
    classes = list(db.classes.find({}, {"_id": 0}))
    return jsonify(classes)


@app.post("/api/classes")
def add_class():
    payload = request.get_json(force=True, silent=True) or {}

    name = (payload.get("name") or "").strip()

    try:
        rows = int(payload.get("rows") or 4)
        cols = int(payload.get("cols") or 6)
    except Exception:
        return jsonify({"error": "Rows and columns must be numbers"}), 400

    if not name:
        return jsonify({"error": "Class name required"}), 400

    new_class = {
        "id": next_id("classes"),
        "name": name,
        "rows": rows,
        "cols": cols,
        "seating": {}
    }

    db.classes.insert_one(new_class)
    clean_doc(new_class)

    return jsonify(new_class), 201


@app.post("/api/classes/seat")
def update_seat():
    payload = request.get_json(force=True, silent=True) or {}

    try:
        class_id = int(payload.get("class_id") or 0)
        row = int(payload.get("row") or 0)
        col = int(payload.get("col") or 0)
    except Exception:
        return jsonify({"error": "Invalid class/seat values"}), 400

    name = (payload.get("name") or "").strip()
    username = normalize(payload.get("username"))
    key = f"{row}_{col}"

    if not db.classes.find_one({"id": class_id}):
        return jsonify({"error": "Class not found"}), 404

    if name:
        db.classes.update_one(
            {"id": class_id},
            {"$set": {
                f"seating.{key}": {
                    "name": name,
                    "username": username or normalize(name)
                }
            }}
        )
    else:
        db.classes.update_one(
            {"id": class_id},
            {"$unset": {f"seating.{key}": ""}}
        )

    return jsonify({
        "success": True,
        "class_id": class_id,
        "seat": key,
        "name": name,
        "username": username
    })


# =========================================================
# Subjects + assignments
# =========================================================

@app.get("/api/subjects")
def get_subjects():
    subjects = list(db.subjects.find({}, {"_id": 0}))
    return jsonify(subjects)


@app.post("/api/subjects")
def add_subject():
    payload = request.get_json(force=True, silent=True) or {}

    name = (payload.get("name") or "").strip()

    if not name:
        return jsonify({"error": "Subject name required"}), 400

    subject = {
        "id": next_id("subjects"),
        "name": name
    }

    db.subjects.insert_one(subject)
    clean_doc(subject)

    return jsonify(subject), 201


@app.get("/api/assignments")
def get_assignments():
    assignments = list(db.assignments.find({}, {"_id": 0}))
    return jsonify(assignments)


@app.post("/api/assignments")
def add_assignment():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize(payload.get("teacher_username"))

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class or subject"}), 400

    if not teacher_username or not class_id or not subject_id:
        return jsonify({"error": "Teacher, class, and subject are required"}), 400

    if not db.users.find_one({"username": teacher_username, "role": "teacher"}):
        return jsonify({"error": "Teacher not found"}), 404

    if not db.classes.find_one({"id": class_id}):
        return jsonify({"error": "Class not found"}), 404

    if not db.subjects.find_one({"id": subject_id}):
        return jsonify({"error": "Subject not found"}), 404

    existing = db.assignments.find_one({
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id
    })

    if existing:
        return jsonify({"error": "Assignment already exists"}), 400

    assignment = {
        "id": next_id("assignments"),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id
    }

    db.assignments.insert_one(assignment)
    clean_doc(assignment)

    return jsonify(assignment), 201


# =========================================================
# Exams
# =========================================================

@app.get("/api/exams")
def get_exams():
    query = {}

    if request.args.get("teacher_username"):
        query["teacher_username"] = normalize(request.args.get("teacher_username"))

    if request.args.get("class_id"):
        query["class_id"] = int(request.args.get("class_id"))

    if request.args.get("subject_id"):
        query["subject_id"] = int(request.args.get("subject_id"))

    exams = list(db.exams.find(query, {"_id": 0}))
    return jsonify(exams)


@app.post("/api/exams")
def create_exam():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize(payload.get("teacher_username"))

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class or subject"}), 400

    title = (payload.get("title") or "").strip()
    kind = (payload.get("kind") or "exam").strip()
    date = (payload.get("date") or "").strip()

    if not teacher_username or not title or not date:
        return jsonify({"error": "teacher_username, title, and date are required"}), 400

    exam = {
        "id": next_id("exams"),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id,
        "title": title,
        "kind": kind,
        "date": date
    }

    db.exams.insert_one(exam)
    clean_doc(exam)

    return jsonify(exam), 201


# =========================================================
# Homework
# =========================================================

@app.get("/api/homework")
def get_homework():
    query = {}

    if request.args.get("teacher_username"):
        query["teacher_username"] = normalize(request.args.get("teacher_username"))

    if request.args.get("class_id"):
        query["class_id"] = int(request.args.get("class_id"))

    if request.args.get("subject_id"):
        query["subject_id"] = int(request.args.get("subject_id"))

    homework = list(db.homework.find(query, {"_id": 0}))
    return jsonify(homework)


@app.post("/api/homework")
def create_homework():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize(payload.get("teacher_username"))

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class or subject"}), 400

    title = (payload.get("title") or "").strip()
    description = (payload.get("description") or "").strip()
    due_date = (payload.get("due_date") or "").strip()

    if not teacher_username or not title or not due_date:
        return jsonify({"error": "teacher_username, title, and due_date are required"}), 400

    hw = {
        "id": next_id("homework"),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id,
        "title": title,
        "description": description,
        "due_date": due_date
    }

    db.homework.insert_one(hw)
    clean_doc(hw)

    return jsonify(hw), 201


# =========================================================
# Grades
# =========================================================

@app.get("/api/grades")
def get_grades():
    query = {}

    if request.args.get("item_id"):
        query["item_id"] = str(request.args.get("item_id"))

    if request.args.get("item_type"):
        query["item_type"] = request.args.get("item_type")

    if request.args.get("class_id"):
        query["class_id"] = int(request.args.get("class_id"))

    grades = list(db.grades.find(query, {"_id": 0}))
    return jsonify(grades)


@app.post("/api/grades")
def save_grades():
    payload = request.get_json(force=True, silent=True) or {}

    item_id = payload.get("item_id")
    item_type = payload.get("item_type")
    class_id = payload.get("class_id")
    grades_data = payload.get("grades", [])

    if item_id is None or not item_type:
        return jsonify({"error": "item_id and item_type are required"}), 400

    try:
        class_id = int(class_id)
    except Exception:
        return jsonify({"error": "class_id is required"}), 400

    item_id = str(item_id)

    db.grades.delete_many({
        "item_id": item_id,
        "item_type": item_type,
        "class_id": class_id
    })

    docs = []

    for entry in grades_data:
        student_name = (entry.get("student_name") or "").strip()
        student_username = (
            entry.get("student_username") or
            entry.get("username") or
            ""
        ).strip().lower()

        score = entry.get("score")
        comment = entry.get("comment") or ""

        if student_name and score != "":
            docs.append({
                "item_id": item_id,
                "item_type": item_type,
                "class_id": class_id,
                "student_name": student_name,
                "student_username": student_username,
                "score": str(score),
                "comment": comment
            })

    if docs:
        db.grades.insert_many(docs)

    return jsonify({
        "success": True,
        "saved": len(docs)
    })


# =========================================================
# Attendance
# =========================================================

@app.get("/api/attendance/records")
def get_attendance_records():
    records = list(db.attendance.find({}, {"_id": 0}))
    return jsonify(records)


@app.get("/api/attendance/history")
def get_attendance_history():
    records = list(db.attendance.find({}, {"_id": 0}))
    return jsonify(records)


@app.post("/api/attendance/save")
def save_attendance():
    payload = request.get_json(force=True, silent=True) or {}

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class_id or subject_id"}), 400

    teacher_username = normalize(payload.get("teacher_username"))
    date = (payload.get("date") or "").strip()
    records = payload.get("records", [])

    if not class_id or not teacher_username:
        return jsonify({"error": "class_id and teacher_username are required"}), 400

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    if not isinstance(records, list) or not records:
        return jsonify({"error": "Attendance records are required"}), 400

    clean_records = []

    for r in records:
        clean_records.append({
            "seat": r.get("seat"),
            "name": (r.get("name") or "").strip(),
            "username": normalize(r.get("username")),
            "status": r.get("status") or "Absent"
        })

    attendance = {
        "id": next_id("attendance"),
        "class_id": class_id,
        "subject_id": subject_id,
        "teacher_username": teacher_username,
        "date": date,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "records": clean_records
    }

    db.attendance.insert_one(attendance)
    clean_doc(attendance)

    return jsonify({
        "success": True,
        "id": attendance["id"],
        "saved": len(clean_records)
    }), 201


@app.get("/api/attendance/latest-ai-result")
def latest_ai_result():
    return jsonify([
        {"name": "ali", "username": "ali", "present": "YES", "accuracy": 96},
        {"name": "abbass", "username": "abbass", "present": "YES", "accuracy": 94},
        {"name": "abbass1", "username": "abbass1", "present": "YES", "accuracy": 91},
        {"name": "hassan", "username": "hassan", "present": "YES", "accuracy": 93},
        {"name": "karim", "username": "karim", "present": "YES", "accuracy": 95},
        {"name": "mohammad", "username": "mohammad", "present": "YES", "accuracy": 97},
        {"name": "sajed", "username": "sajed", "present": "YES", "accuracy": 92}
    ])


# =========================================================
# Reports
# =========================================================

@app.get("/api/reports/attendance")
def attendance_report():
    query = {}

    if request.args.get("class_id"):
        query["class_id"] = int(request.args.get("class_id"))

    sessions = list(db.attendance.find(query, {"_id": 0}))

    stats = {}

    for session in sessions:
        for record in session.get("records", []):
            key = normalize(record.get("username")) or normalize(record.get("name"))
            name = record.get("name") or record.get("username")
            status = record.get("status")

            if not key:
                continue

            if key not in stats:
                stats[key] = {
                    "name": name,
                    "present": 0,
                    "absent": 0,
                    "total": 0
                }

            stats[key]["total"] += 1

            if status == "Present":
                stats[key]["present"] += 1
            else:
                stats[key]["absent"] += 1

    result = []

    for data in stats.values():
        pct = (data["present"] / data["total"] * 100) if data["total"] else 0

        result.append({
            "name": data["name"],
            "present": data["present"],
            "absent": data["absent"],
            "total": data["total"],
            "percentage": round(pct, 1)
        })

    return jsonify(result)


@app.get("/api/reports/performance")
def performance_report():
    query = {}

    if request.args.get("class_id"):
        query["class_id"] = int(request.args.get("class_id"))

    grades = list(db.grades.find(query, {"_id": 0}))
    stats = {}

    for grade in grades:
        key = normalize(grade.get("student_username")) or normalize(grade.get("student_name"))
        name = grade.get("student_name") or grade.get("student_username")

        try:
            score = float(grade.get("score"))
        except Exception:
            continue

        if not key:
            continue

        if key not in stats:
            stats[key] = {
                "name": name,
                "scores": []
            }

        stats[key]["scores"].append(score)

    result = []

    for data in stats.values():
        avg = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0

        result.append({
            "name": data["name"],
            "average": round(avg, 1),
            "count": len(data["scores"])
        })

    return jsonify(result)


# =========================================================
# Optional CSV/debug
# =========================================================

@app.get("/api/attendance")
def attendance_csv():
    if not ATT_CSV.exists():
        return jsonify({"ok": False, "error": "attendance.csv not found"}), 404
    return send_from_directory(OUTPUT_ATT, "attendance.csv", as_attachment=False)


@app.get("/api/master")
def master_csv():
    if not MASTER_CSV.exists():
        return jsonify({"ok": False, "error": "master_attendance.csv not found"}), 404
    return send_from_directory(OUTPUT_ATT, "master_attendance.csv", as_attachment=False)


@app.get("/api/debug_list")
def debug_list():
    if not OUTPUT_DBG.exists():
        return jsonify({"ok": True, "files": []})
    files = sorted([p.name for p in OUTPUT_DBG.glob("*.jpg")])
    return jsonify({"ok": True, "files": files[:80]})


@app.get("/debug/<path:filename>")
def debug_file(filename):
    return send_from_directory(OUTPUT_DBG, filename)


# =========================================================
# Run
# =========================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)