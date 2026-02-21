from flask import Flask, render_template, jsonify, send_from_directory, request
from pathlib import Path
import subprocess
import sys
import time

# Root of your attendance_project (this file is in web/)
ROOT = Path(__file__).resolve().parents[1]

OUTPUT_ATT = ROOT / "output" / "attendance"
OUTPUT_DBG = ROOT / "output" / "debug_frames"
ATT_CSV = OUTPUT_ATT / "attendance.csv"
MASTER_CSV = OUTPUT_ATT / "master_attendance.csv"

app = Flask(__name__, template_folder="templates", static_folder="static")

@app.before_request
def log_request():
    print(f"DEBUG RECV: {request.method} {request.path}")
    if request.path.endswith("/login"):
        print(f"DEBUG LOGIN BODY: {request.get_data(as_text=True)}")


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

@app.get("/api/master")
def master_csv():
    if not MASTER_CSV.exists():
        return jsonify({"ok": False, "error": "master_attendance.csv not found. Run attendance first."}), 404
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
        text=True
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
    """Run ArcFace with OpenCV detector (fast)"""
    script = ROOT / "scripts" / "test_arcface_opencv.py"
    if not script.exists():
        return jsonify({"ok": False, "error": f"Missing script: {script}"}), 400

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True
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
    """Run ArcFace with RetinaFace detector (accurate but slower)"""
    script = ROOT / "scripts" / "test_arcface_retinaface.py"
    if not script.exists():
        return jsonify({"ok": False, "error": f"Missing script: {script}"}), 400

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True
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
        return jsonify({"ok": False, "error": "attendance.csv not found. Run attendance first."}), 404
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
    # open http://127.0.0.1:5501
    app.run(host="127.0.0.1", port=8000, debug=False)

