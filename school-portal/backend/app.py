from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from pathlib import Path
from datetime import datetime
import os
import bcrypt
import secrets
import string
import firebase_admin
from firebase_admin import firestore
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent
ROOT = FRONTEND_DIR.parent

OUTPUT_ATT = ROOT / "output" / "attendance"
ATT_CSV = OUTPUT_ATT / "attendance.csv"
MASTER_CSV = OUTPUT_ATT / "master_attendance.csv"

load_dotenv(BASE_DIR / ".env")
load_dotenv()

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Firestore default credentials: works in Cloud Shell and Cloud Run
if not firebase_admin._apps:
    firebase_admin.initialize_app()

db = firestore.client()
print("[OK] Connected to Firestore")


def normalize_username(username):
    return (username or "").strip().lower()


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, password_hash):
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits + "!$@#"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def next_id(collection_name):
    docs = (
        db.collection(collection_name)
        .order_by("id", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )

    for doc in docs:
        data = doc.to_dict()
        return int(data.get("id", 0)) + 1

    return 1


def get_first(collection, field, value):
    docs = db.collection(collection).where(field, "==", value).limit(1).stream()
    for doc in docs:
        return doc, doc.to_dict()
    return None, None


def docs_to_list(collection):
    return [doc.to_dict() for doc in db.collection(collection).stream()]


def ensure_admin():
    _, admin = get_first("users", "username", "admin")

    if not admin:
        db.collection("users").add({
            "id": 1,
            "username": "admin",
            "role": "admin",
            "name": "Administrator",
            "password_hash": hash_password("admin123")
        })
        print("[INIT] Created default admin: admin / admin123")


ensure_admin()


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
def serve_static_files(filename):
    return send_from_directory(str(FRONTEND_DIR), filename)


@app.get("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "storage": "firestore"
    })


@app.post("/api/login")
def api_login():
    payload = request.get_json(force=True, silent=True) or {}

    username = normalize_username(payload.get("username"))
    password = payload.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    _, user = get_first("users", "username", username)

    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    password_hash = user.get("password_hash") or ""

    if not password_hash:
        return jsonify({"error": "Account has no password configured"}), 403

    if not check_password(password, password_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "name": user.get("name", user.get("username"))
    })


@app.get("/api/users")
def get_users():
    users = docs_to_list("users")
    for u in users:
        u.pop("password_hash", None)
    return jsonify(users)


@app.get("/api/teachers")
def get_teachers():
    teachers = []
    docs = db.collection("users").where("role", "==", "teacher").stream()

    for doc in docs:
        data = doc.to_dict()
        data.pop("password_hash", None)
        teachers.append(data)

    return jsonify(teachers)


@app.get("/api/students")
def get_students():
    students = []
    docs = db.collection("users").where("role", "==", "student").stream()

    for doc in docs:
        data = doc.to_dict()
        data.pop("password_hash", None)
        students.append(data)

    return jsonify(students)


def create_user(role):
    payload = request.get_json(force=True, silent=True) or {}

    username = normalize_username(payload.get("username"))
    name = (payload.get("name") or "").strip() or username

    if not username:
        return jsonify({"error": "Username is required"}), 400

    _, existing = get_first("users", "username", username)

    if existing:
        return jsonify({"error": "Username already exists"}), 400

    plain_password = generate_password()

    user = {
        "id": next_id("users"),
        "username": username,
        "role": role,
        "name": name,
        "password_hash": hash_password(plain_password)
    }

    db.collection("users").add(user)

    return jsonify({
        "id": user["id"],
        "username": username,
        "role": role,
        "name": name,
        "password": plain_password
    }), 201


@app.post("/api/admin/create_teacher")
def admin_create_teacher():
    return create_user("teacher")


@app.post("/api/admin/create_student")
def admin_create_student():
    return create_user("student")


@app.post("/api/admin/create_admin")
def admin_create_admin():
    return create_user("admin")


@app.get("/api/classes")
def get_classes():
    return jsonify(docs_to_list("classes"))


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

    if rows <= 0 or cols <= 0:
        return jsonify({"error": "Rows and columns must be positive"}), 400

    new_class = {
        "id": next_id("classes"),
        "name": name,
        "rows": rows,
        "cols": cols,
        "seating": {}
    }

    db.collection("classes").add(new_class)
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
    username = normalize_username(payload.get("username"))
    key = f"{row}_{col}"

    class_ref = None
    class_data = None

    docs = db.collection("classes").where("id", "==", class_id).limit(1).stream()

    for doc in docs:
        class_ref = doc.reference
        class_data = doc.to_dict()
        break

    if not class_ref:
        return jsonify({"error": "Class not found"}), 404

    seating = class_data.get("seating", {})

    if name:
        seating[key] = {
            "name": name,
            "username": username or normalize_username(name)
        }
    else:
        seating.pop(key, None)

    class_ref.update({"seating": seating})

    return jsonify({
        "success": True,
        "class_id": class_id,
        "seat": key,
        "name": name,
        "username": username
    })


@app.get("/api/subjects")
def get_subjects():
    return jsonify(docs_to_list("subjects"))


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

    db.collection("subjects").add(subject)
    return jsonify(subject), 201


@app.get("/api/assignments")
def get_assignments():
    return jsonify(docs_to_list("assignments"))


@app.post("/api/assignments")
def add_assignment():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize_username(payload.get("teacher_username"))

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class or subject"}), 400

    if not teacher_username or not class_id or not subject_id:
        return jsonify({"error": "Teacher, class, and subject are required"}), 400

    docs = (
        db.collection("users")
        .where("username", "==", teacher_username)
        .where("role", "==", "teacher")
        .limit(1)
        .stream()
    )

    teacher = None
    for doc in docs:
        teacher = doc.to_dict()
        break

    if not teacher:
        return jsonify({"error": "Teacher not found"}), 404

    _, class_doc = get_first("classes", "id", class_id)
    if not class_doc:
        return jsonify({"error": "Class not found"}), 404

    _, subject_doc = get_first("subjects", "id", subject_id)
    if not subject_doc:
        return jsonify({"error": "Subject not found"}), 404

    docs = (
        db.collection("assignments")
        .where("teacher_username", "==", teacher_username)
        .where("class_id", "==", class_id)
        .where("subject_id", "==", subject_id)
        .limit(1)
        .stream()
    )

    for doc in docs:
        return jsonify({"error": "Assignment already exists"}), 400

    assignment = {
        "id": next_id("assignments"),
        "teacher_username": teacher_username,
        "class_id": class_id,
        "subject_id": subject_id
    }

    db.collection("assignments").add(assignment)
    return jsonify(assignment), 201


@app.get("/api/exams")
def get_exams():
    query = db.collection("exams")

    if request.args.get("teacher_username"):
        query = query.where("teacher_username", "==", normalize_username(request.args.get("teacher_username")))

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    if request.args.get("subject_id"):
        query = query.where("subject_id", "==", int(request.args.get("subject_id")))

    return jsonify([doc.to_dict() for doc in query.stream()])


@app.post("/api/exams")
def create_exam():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize_username(payload.get("teacher_username"))

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

    db.collection("exams").add(exam)
    return jsonify(exam), 201


@app.get("/api/homework")
def get_homework():
    query = db.collection("homework")

    if request.args.get("teacher_username"):
        query = query.where("teacher_username", "==", normalize_username(request.args.get("teacher_username")))

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    if request.args.get("subject_id"):
        query = query.where("subject_id", "==", int(request.args.get("subject_id")))

    return jsonify([doc.to_dict() for doc in query.stream()])


@app.post("/api/homework")
def create_homework():
    payload = request.get_json(force=True, silent=True) or {}

    teacher_username = normalize_username(payload.get("teacher_username"))

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

    db.collection("homework").add(hw)
    return jsonify(hw), 201


@app.get("/api/grades")
def get_grades():
    query = db.collection("grades")

    if request.args.get("item_id"):
        query = query.where("item_id", "==", str(request.args.get("item_id")))

    if request.args.get("item_type"):
        query = query.where("item_type", "==", request.args.get("item_type"))

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    return jsonify([doc.to_dict() for doc in query.stream()])


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

    old_docs = (
        db.collection("grades")
        .where("item_id", "==", item_id)
        .where("item_type", "==", item_type)
        .where("class_id", "==", class_id)
        .stream()
    )

    for doc in old_docs:
        doc.reference.delete()

    saved = 0

    for entry in grades_data:
        student_name = (entry.get("student_name") or "").strip()
        score = entry.get("score")
        comment = entry.get("comment") or ""

        if student_name and score != "":
            db.collection("grades").add({
                "item_id": item_id,
                "item_type": item_type,
                "class_id": class_id,
                "student_name": student_name,
                "score": str(score),
                "comment": comment
            })
            saved += 1

    return jsonify({"success": True, "saved": saved})


@app.get("/api/attendance/records")
def get_attendance_records():
    return jsonify(docs_to_list("attendance"))


@app.get("/api/attendance/history")
def get_attendance_history():
    return jsonify(docs_to_list("attendance"))


@app.post("/api/attendance/save")
def save_attendance():
    payload = request.get_json(force=True, silent=True) or {}

    try:
        class_id = int(payload.get("class_id") or 0)
        subject_id = int(payload.get("subject_id") or 0)
    except Exception:
        return jsonify({"error": "Invalid class_id or subject_id"}), 400

    teacher_username = normalize_username(payload.get("teacher_username"))
    date = (payload.get("date") or "").strip()
    records = payload.get("records", [])

    if not class_id or not subject_id or not teacher_username or not date:
        return jsonify({"error": "Missing required attendance fields"}), 400

    if not isinstance(records, list) or not records:
        return jsonify({"error": "Attendance records are required"}), 400

    record = {
        "id": next_id("attendance"),
        "class_id": class_id,
        "subject_id": subject_id,
        "teacher_username": teacher_username,
        "date": date,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "records": records
    }

    db.collection("attendance").add(record)
    return jsonify({"success": True, "id": record["id"]}), 201


@app.get("/api/attendance/latest-ai-result")
def latest_ai_result():
    return jsonify([
        {"name": "ali", "present": "YES", "accuracy": 96},
        {"name": "abbass", "present": "YES", "accuracy": 94},
        {"name": "abbass1", "present": "YES", "accuracy": 91},
        {"name": "hassan", "present": "YES", "accuracy": 93},
        {"name": "karim", "present": "YES", "accuracy": 95},
        {"name": "mohammad", "present": "YES", "accuracy": 97},
        {"name": "sajed", "present": "YES", "accuracy": 92}
    ])


@app.get("/api/reports/attendance")
def attendance_report():
    query = db.collection("attendance")

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    sessions = [doc.to_dict() for doc in query.stream()]
    stats = {}

    for session in sessions:
        for record in session.get("records", []):
            name = record.get("name")
            status = record.get("status")

            if not name:
                continue

            if name not in stats:
                stats[name] = {"present": 0, "absent": 0, "total": 0}

            stats[name]["total"] += 1

            if status == "Present":
                stats[name]["present"] += 1
            else:
                stats[name]["absent"] += 1

    result = []

    for name, data in stats.items():
        pct = (data["present"] / data["total"] * 100) if data["total"] else 0

        result.append({
            "name": name,
            "present": data["present"],
            "absent": data["absent"],
            "total": data["total"],
            "percentage": round(pct, 1)
        })

    return jsonify(result)


@app.get("/api/reports/performance")
def performance_report():
    query = db.collection("grades")

    if request.args.get("class_id"):
        query = query.where("class_id", "==", int(request.args.get("class_id")))

    grades = [doc.to_dict() for doc in query.stream()]
    stats = {}

    for grade in grades:
        name = grade.get("student_name")
        score = grade.get("score")

        if not name:
            continue

        try:
            score = float(score)
        except Exception:
            continue

        if name not in stats:
            stats[name] = []

        stats[name].append(score)

    return jsonify([
        {
            "name": name,
            "average": round(sum(scores) / len(scores), 1),
            "count": len(scores)
        }
        for name, scores in stats.items()
    ])


@app.get("/api/analytics/attendance_trend")
def attendance_trend():
    sessions = docs_to_list("attendance")
    daily = {}

    for session in sessions:
        date = str(session.get("date") or "").split(" ")[0]
        if not date:
            continue

        if date not in daily:
            daily[date] = {"total": 0, "present": 0}

        for record in session.get("records", []):
            daily[date]["total"] += 1
            if record.get("status") == "Present":
                daily[date]["present"] += 1

    result = []

    for date in sorted(daily.keys()):
        total = daily[date]["total"]
        present = daily[date]["present"]

        result.append({
            "date": date,
            "percentage": round((present / total * 100) if total else 0, 1)
        })

    return jsonify(result)


@app.get("/api/analytics/grade_distribution")
def grade_distribution():
    grades = docs_to_list("grades")

    brackets = {
        "A (90-100)": 0,
        "B (80-89)": 0,
        "C (70-79)": 0,
        "D (60-69)": 0,
        "F (<60)": 0
    }

    for grade in grades:
        try:
            score = float(grade.get("score", 0))
        except Exception:
            continue

        if score >= 90:
            brackets["A (90-100)"] += 1
        elif score >= 80:
            brackets["B (80-89)"] += 1
        elif score >= 70:
            brackets["C (70-79)"] += 1
        elif score >= 60:
            brackets["D (60-69)"] += 1
        else:
            brackets["F (<60)"] += 1

    return jsonify([
        {"label": label, "count": count}
        for label, count in brackets.items()
    ])


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


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
